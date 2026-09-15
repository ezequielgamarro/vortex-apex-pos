"""Router de operaciones para Ventas: creación con descuento de stock e historial.

Persistencia local vía SQLAlchemy + SQLite con `db: Session = Depends(get_db)`.

MULTI-UNIDAD / VENTA POR PESO:
- Productos tipo 'unidad'/'porcion': se venden por `cantidad` (entera).
- Productos tipo 'peso': además aceptan venta por `importe` ($); la cantidad
  física exacta se deriva como `importe / precio_unitario` y se descuenta esa
  fracción del stock.

ATÓMICO: la venta se valida y persiste en una transacción única que se confirma
al final. Ante cualquier fallo (stock insuficiente, importe sin alcance del
stock disponible, producto inexistente) se revierte todo y nada se descuenta.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies import get_current_user, requiere_rol, UsuarioActual
from app.models import (
    Venta,
    VentaItem,
    Producto,
    Arqueo,
    ArqueoMovimiento,
    Cliente,
    MovimientoCuenta,
    now_utc,
)
from app.schemas.venta import (
    VentaCreate,
    VentaOut,
    VentaDetalleOut,
    VentaItemOut,
    VentaItemHistorialOut,
    VentaHistorialOut,
    AnulacionOut,
    AnularVentaIn,
)

router = APIRouter(prefix="/ventas", tags=["Ventas"])

# Precisión de la cantidad física que se descuenta de stock en ventas por peso
# (p. ej. 3 decimales de kg). Definida por convención del modelo Numeric(12,3).
_PESO_DECIMALES = 3


def _uuid4_short() -> str:
    """Genera un sufijo corto aleatorio para el folio de venta."""
    return uuid.uuid4().hex[:6].upper()


def _redondear_peso(cantidad: Decimal) -> Decimal:
    """Redondea una cantidad física al número de decimales soportado por stock."""
    q = cantidad.quantize(Decimal(1).scaleb(-_PESO_DECIMALES), rounding=ROUND_HALF_UP)
    return q


def _resolver_item(item, producto: Producto) -> dict:
    """Resuelve la cantidad física y el importe bruto de un ítem de venta.

    Retorna:
        cantidad: unidades físicas que se descontarán del stock.
        bruto:    importe bruto a cobrar por el ítem (antes del descuento).

    Lanza HTTPException si el request es inconsistente con el tipo de unidad.
    """
    precio_unitario = Decimal(producto.precio)  # precio oficial de la BD
    if precio_unitario <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El producto '{producto.nombre}' no tiene precio válido.",
        )

    if item.importe is not None:
        # ---- Venta por IMPORTE -------------------------------------------------
        tipo = producto.tipo_unidad or "unidad"
        if tipo != "peso":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"El producto '{producto.nombre}' se vende por {tipo}; "
                    "no admite el campo 'importe'. Envía 'cantidad'."
                ),
            )
        importe = Decimal(item.importe)
        # Fracción de stock equivalente al importe solicitado.
        cantidad = _redondear_peso(importe / precio_unitario)
        if cantidad <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Importe demasiado bajo para '{producto.nombre}'.",
            )
        # El bruto a cobrar es el importe acordado por el cliente (exacto).
        return {"cantidad": cantidad, "bruto": importe}

    # ---- Venta por CANTIDAD física ---------------------------------------------
    tipo = producto.tipo_unidad or "unidad"
    cantidad = Decimal(item.cantidad)
    if tipo != "peso":
        # Para 'unidad'/'porcion' se exige cantidad entera positiva.
        if cantidad != cantidad.to_integral_value():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"El producto '{producto.nombre}' se vende por {tipo} y "
                    "la cantidad debe ser un entero."
                ),
            )
    return {"cantidad": cantidad, "bruto": cantidad * precio_unitario}


@router.post(
    "",
    response_model=VentaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una venta (descuenta stock; soporta venta por peso/importe)",
)
def registrar_venta(
    venta: VentaCreate,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crea una venta, valida y descuenta el stock de cada producto vendido.

    - Si un ítem trae `importe`, se valida que el producto sea de tipo 'peso',
      se deriva la cantidad física y se descuenta la fracción equivalente.
    - La operación es atómica (un solo commit / rollback general).
    """
    try:
        # 0) Caja obligatoria: una venta no puede procesarse sin una caja abierta
        #    en el turno actual (evita descuentos de stock/discrepancias de dinero
        #    fuera de un arqueo vigente).
        caja_abierta = db.query(Arqueo).filter(Arqueo.estado == "abierto").first()
        if caja_abierta is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No hay una caja abierta. Es obligatorio abrir la caja "
                    "antes de registrar cobros."
                ),
            )

        # 1b) Resolver cliente para CC (fiado) si corresponde.
        cliente_destino = (venta.cliente or "").strip() or "Mostrador"
        cliente_fk = None
        if venta.metodo_pago == "cuenta_corriente":
            cliente_fk = (
                db.query(Cliente).filter(Cliente.id == venta.cliente_id).first()
            )
            if cliente_fk is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cliente no encontrado para la cuenta corriente.",
                )
            cliente_destino = cliente_fk.nombre

        # 1a) Validar y resolver TODOS los ítems antes de tocar la BD.
        cantidades_db: dict[UUID, Decimal] = {}  # cantidad física a descontar
        brutos_db: dict[UUID, Decimal] = {}  # importe bruto del ítem
        total_venta = Decimal("0")

        for item in venta.items:
            producto = (
                db.query(Producto).filter(Producto.id == item.producto_id).first()
            )
            if producto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Producto {item.producto_id} no encontrado",
                )
            if producto.activo is False:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El producto '{producto.nombre}' no está activo",
                )

            resuelto = _resolver_item(item, producto)
            cantidad = resuelto["cantidad"]
            bruto = resuelto["bruto"]

            # En venta por importe, el importe puede exceder el valor en stock:
            # equivaldría a pedir más mercancía de la disponible.
            if producto.stock < cantidad:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Stock insuficiente para '{producto.nombre}' "
                        f"(disponible: {producto.stock}, requerido: {cantidad})."
                    ),
                )

            descuento_item = Decimal(item.descuento or 0)
            subtotal = bruto - descuento_item
            if subtotal < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Descuento inválido para el producto '{producto.nombre}'.",
                )

            cantidades_db[item.producto_id] = cantidad
            brutos_db[item.producto_id] = bruto
            total_venta += subtotal

        # 2) Folio único (timestamp + sufijo aleatorio)
        folio = f"V-{datetime.now().strftime('%Y%m%d%H%M%S')}-{_uuid4_short()}"

        # 3) Cabecera de venta (flush para obtener el id sin commitear).
        venta_nueva = Venta(
            folio=folio,
            total=total_venta,
            metodo_pago=venta.metodo_pago,
            cliente=cliente_destino,
            paga_con=venta.paga_con,
            vuelto=venta.vuelto,
        )
        db.add(venta_nueva)
        db.flush()

        # 4) Ítems + descuento de stock dentro de la misma transacción.
        for item in venta.items:
            db.add(
                VentaItem(
                    venta_id=venta_nueva.id,
                    producto_id=item.producto_id,
                    cantidad=cantidades_db[item.producto_id],
                    precio_unitario=brutos_db[item.producto_id]
                    / cantidades_db[item.producto_id],
                    descuento=Decimal(item.descuento or 0),
                )
            )
            producto = (
                db.query(Producto).filter(Producto.id == item.producto_id).first()
            )
            producto.stock = Decimal(producto.stock) - cantidades_db[item.producto_id]
            producto.actualizado_en = now_utc()

        # 4b) Cuenta corriente: el total pasa a ser DEUDA del cliente (fiado).
        #     No ingresa dinero físico a la gaveta; se registra como cargo.
        if venta.metodo_pago == "cuenta_corriente" and cliente_fk is not None:
            cliente_fk.saldo_deuda = Decimal(cliente_fk.saldo_deuda or 0) + total_venta
            db.add(
                MovimientoCuenta(
                    cliente_id=cliente_fk.id,
                    tipo="cargo",
                    monto=total_venta,
                    venta_id=venta_nueva.id,
                    concepto=f"Venta a crédito {folio}",
                )
            )

        # 5) Confirmar todo en un único commit (transacción atómica).
        db.commit()
        db.refresh(venta_nueva)
        return venta_nueva

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar la venta: {str(exc)}",
        )


@router.get("", response_model=List[VentaOut], summary="Consultar historial de ventas")
def historial_ventas(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    cliente: Optional[str] = None,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve el historial de ventas, opcionalmente filtrado por fechas o cliente."""
    try:
        query = db.query(Venta)
        if fecha_desde:
            _desde = datetime.combine(fecha_desde, datetime.min.time())
            query = query.filter(Venta.fecha >= _desde)
        if fecha_hasta:
            _hasta = datetime.combine(fecha_hasta, datetime.max.time())
            query = query.filter(Venta.fecha <= _hasta)
        if cliente:
            query = query.filter(Venta.cliente.ilike(f"%{cliente}%"))
        return query.order_by(Venta.fecha.desc()).all()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar historial de ventas: {str(exc)}",
        )


@router.post(
    "/{venta_id}/anular",
    response_model=AnulacionOut,
    summary="Anular una venta y revertir stock/saldo/caja (solo admin)",
)
def anular_venta(
    venta_id: UUID,
    data: AnularVentaIn,
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
    db: Session = Depends(get_db),
):
    """Anula una venta ACTIVA del turno abierto, revirtiendo todos sus efectos.

    Efectos revertidos (en una única transacción atómica):
      1. Stock: se devuelve la cantidad física exacta de cada ítem.
      2. Cuenta corriente: si fue fiado, se descuenta el cargo del saldo y se
         registra un movimiento compensatorio 'abono' (auditoría).
      3. Caja: la venta sale de los totales por filtro de estado ('anulada'),
         de modo que la gaveta esperada queda consistente sin movimientos extra.

    Reglas:
      - Solo admin (requiere_rol).
      - No se permite anular una venta ya anulada (409).
      - No se permite anular una venta de un turno CERRADO (409): descuadraría
        un arqueo conciliado. Usar ajuste manual de caja en ese caso.
    """
    try:
        venta = db.query(Venta).filter(Venta.id == venta_id).first()
        if venta is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Venta no encontrada",
            )
        if (venta.estado or "activa") == "anulada":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Esta venta ya fue anulada.",
            )

        from app.models import Usuario
        from app.dependencies import verificar_password
        admin_usuario = db.query(Usuario).filter(Usuario.id == usuario.id).first()
        if not admin_usuario or not verificar_password(data.password, admin_usuario.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Contraseña incorrecta.",
            )

        # La venta debe pertenecer al turno ABIERTO para poder anularse.
        caja_abierta = db.query(Arqueo).filter(Arqueo.estado == "abierto").first()
        if caja_abierta is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "No hay una caja abierta. Solo pueden anularse ventas del "
                    "turno en curso."
                ),
            )
        if venta.fecha < caja_abierta.fecha_apertura:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Esta venta pertenece a un turno anterior ya cerrado. Para "
                    "corregirla, registra un ajuste manual en la caja actual."
                ),
            )

        # 1) Revertir stock ítem por ítem.
        stock_total = 0
        for it in venta.items:
            producto = db.query(Producto).filter(Producto.id == it.producto_id).first()
            if producto is None:
                continue
            producto.stock = Decimal(producto.stock or 0) + Decimal(it.cantidad)
            producto.actualizado_en = now_utc()
            stock_total += 1

        # 2) Revertir saldo de cuenta corriente (si fue fiado).
        saldo_cc_ajustado = None
        if venta.metodo_pago == "cuenta_corriente":
            mov = (
                db.query(MovimientoCuenta)
                .filter(
                    MovimientoCuenta.venta_id == venta.id,
                    MovimientoCuenta.tipo == "cargo",
                )
                .first()
            )
            if mov is not None:
                cliente = (
                    db.query(Cliente).filter(Cliente.id == mov.cliente_id).first()
                )
                if cliente is not None:
                    cliente.saldo_deuda = Decimal(cliente.saldo_deuda or 0) - Decimal(
                        mov.monto
                    )
                    if cliente.saldo_deuda < 0:
                        cliente.saldo_deuda = Decimal("0")
                    saldo_cc_ajustado = cliente.saldo_deuda
                    # Movimiento compensatorio (auditoría; no se borra el cargo).
                    db.add(
                        MovimientoCuenta(
                            cliente_id=cliente.id,
                            tipo="abono",
                            monto=Decimal(mov.monto),
                            venta_id=venta.id,
                            concepto=f"Anulación de venta {venta.folio}",
                        )
                    )

        # 3) Marcar la venta como anulada (soft-delete + auditoría).
        venta.estado = "anulada"
        venta.anulada_en = now_utc()
        venta.anulada_por = usuario.email or usuario.nombre
        venta.motivo_anulacion = data.motivo

        db.commit()
        db.refresh(venta)

        return AnulacionOut(
            venta_id=venta.id,
            folio=venta.folio,
            estado=venta.estado,
            total_revertido=Decimal(venta.total),
            stock_devuelto=stock_total,
            saldo_cc_ajustado=saldo_cc_ajustado,
            mensaje=(
                f"Venta {venta.folio} anulada. Stock y cuenta corriente revertidos."
            ),
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al anular la venta: {str(exc)}",
        )


def _serializar_historial(venta: Venta) -> VentaHistorialOut:
    """Envuelve una venta con sus ítems enriquecidos en formato historial."""
    items = [
        VentaItemHistorialOut(
            id=it.id,
            producto_id=it.producto_id,
            nombre_producto=it.producto.nombre,
            cantidad=Decimal(it.cantidad),
            precio_unitario=Decimal(it.precio_unitario),
            descuento=Decimal(it.descuento or 0),
            subtotal=(
                Decimal(it.cantidad) * Decimal(it.precio_unitario)
                - Decimal(it.descuento or 0)
            ),
        )
        for it in venta.items
    ]
    return VentaHistorialOut(
        id=venta.id,
        folio=venta.folio,
        fecha=venta.fecha,
        total=Decimal(venta.total),
        metodo_pago=venta.metodo_pago,
        cliente=venta.cliente,
        creado_en=venta.creado_en,
        items=items,
    )


@router.get(
    "/historial-detallado",
    response_model=List[VentaHistorialOut],
    summary="Historial de ventas con detalle de productos por ticket",
)
def historial_detallado(
    limite: int = 200,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve las ventas ordenadas de más reciente a más antigua, cada una
    con la lista de productos vendidos (nombre e importes). Útil para el módulo
    de Historial de Ventas agrupado por fecha."""
    try:
        limite = max(1, min(limite, 1000))
        # Eager-load por lotes (selectinload) para evitar el N+1 al materializar
        # cada ítem y su producto: se ejecutan 2-3 consultas en total en lugar de
        # una por ítem (~2500) — medido 1.2s -> decenas de ms.
        ventas = (
            db.query(Venta)
            .options(selectinload(Venta.items).selectinload(VentaItem.producto))
            .order_by(Venta.fecha.desc())
            .limit(limite)
            .all()
        )
        return [_serializar_historial(v) for v in ventas]
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar historial detallado: {str(exc)}",
        )


@router.get("/{venta_id}", response_model=VentaOut, summary="Obtener una venta")
def obtener_venta(
    venta_id: UUID,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve el detalle de una venta puntual por su ID."""
    try:
        venta = db.query(Venta).filter(Venta.id == venta_id).first()
        if venta is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Venta no encontrada",
            )
        return venta
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener la venta: {str(exc)}",
        )


@router.get(
    "/{venta_id}/detalle",
    response_model=VentaDetalleOut,
    summary="Obtener venta con sus ítems",
)
def obtener_detalle_venta(
    venta_id: UUID,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve una venta puntual con el detalle de todos sus ítems (productos)."""
    try:
        venta = db.query(Venta).filter(Venta.id == venta_id).first()
        if venta is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Venta no encontrada",
            )
        items = [
            VentaItemOut(
                id=it.id,
                producto_id=it.producto_id,
                cantidad=Decimal(it.cantidad),
                precio_unitario=Decimal(it.precio_unitario),
                descuento=Decimal(it.descuento),
            )
            for it in venta.items
        ]
        return VentaDetalleOut(
            id=venta.id,
            folio=venta.folio,
            fecha=venta.fecha,
            total=Decimal(venta.total),
            metodo_pago=venta.metodo_pago,
            cliente=venta.cliente,
            creado_en=venta.creado_en,
            items=items,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener el detalle de la venta: {str(exc)}",
        )
