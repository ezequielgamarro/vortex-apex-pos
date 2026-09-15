"""Router de Cuentas Corrientes (fiado a clientes).

Endpoints:
    GET  /clientes                 -> lista clientes (con saldo deuda).
    GET  /clientes/{id}            -> detalle + historial (movimientos).
    POST /clientes                 -> registrar un cliente nuevo.
    POST /clientes/{id}/abonos     -> registrar un abono (reduce deuda y el
                                       efectivo ingresa a la Caja abierta).
    GET  /movimientos              -> historial global de movimientos (opcional).

Reglas de negocio:
- Una venta a "cuenta corriente" (fiado) incrementa `saldo_deuda` del cliente
  y crea un MovimientoCuenta de tipo 'cargo'. (Ver routers/ventas.py.)
- Un abono reduce `saldo_deuda` y su importe físico ingresa a la Caja activa
  (ArqueoMovimiento de tipo 'ingreso'), sumando al efectivo real de la gaveta.
  Por eso, registrar abonos requiere que haya una caja abierta.
"""

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, UsuarioActual
from app.models import Arqueo, ArqueoMovimiento, Cliente, MovimientoCuenta, now_utc
from app.schemas.cuentas import (
    ClienteCreate,
    ClienteOut,
    DetalleClienteOut,
    AbonoCreate,
    MovimientoCuentaOut,
)

router = APIRouter(tags=["Cuentas Corrientes"])

# ==========================================================================
# CLIENTES
# ==========================================================================


@router.get(
    "/clientes",
    response_model=List[ClienteOut],
    summary="Listar clientes con su saldo",
)
def listar_clientes(
    solo_deudores: bool = False,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista los clientes (activos), con su saldo de deuda actual.

    `solo_deudores=true` filtra aquellos cuya deuda es > 0 (vista de cobranza).
    """
    try:
        query = db.query(Cliente).filter(Cliente.activo.is_(True))
        if solo_deudores:
            query = query.filter(Cliente.saldo_deuda > 0)
        return query.order_by(Cliente.nombre.asc()).all()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar clientes: {str(exc)}",
        )


@router.get(
    "/clientes/{cliente_id}",
    response_model=DetalleClienteOut,
    summary="Detalle de un cliente y su historial",
)
def obtener_cliente(
    cliente_id: int,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve un cliente con todos sus movimientos de cuenta corriente."""
    try:
        cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
        if cliente is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente no encontrado",
            )
        # Materializar movimientos en la sesión.
        _ = list(cliente.movimientos)  # noqa: F841
        return cliente
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar cliente: {str(exc)}",
        )


@router.post(
    "/clientes",
    response_model=ClienteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un cliente",
)
def crear_cliente(
    cliente: ClienteCreate,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Registra un cliente nuevo (saldo deuda inicial siempre 0)."""
    try:
        nombre = cliente.nombre.strip()
        if not nombre:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre del cliente es obligatorio.",
            )
        nuevo = Cliente(
            nombre=nombre,
            telefono=(cliente.telefono or "").strip() or None,
        )
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
        return nuevo
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear el cliente: {str(exc)}",
        )


# ==========================================================================
# ABONOS (pag o parcial/total de la deuda)
# ==========================================================================


def _obtener_caja_activa_o_400(db: Session) -> Arqueo:
    """Devuelve la caja abierta; si no existe lanza HTTP 400 (obligatoria)."""
    caja = db.query(Arqueo).filter(Arqueo.estado == "abierto").first()
    if caja is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No hay una caja abierta. Es obligatorio abrir la caja para "
                "registrar el abono (el dinero ingresa al turno activo)."
            ),
        )
    return caja


@router.post(
    "/clientes/{cliente_id}/abonos",
    response_model=ClienteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un abono de un cliente (ingresa efectivo a la caja)",
)
def registrar_abono(
    cliente_id: int,
    abono: AbonoCreate,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Registra un pago (abono) de un cliente sobre su cuenta corriente.

    La operación es atómica:
      1. Exige una caja abierta (el efectivo entra físicamente al turno).
      2. Reduce `saldo_deuda` del cliente.
      3. Registra un MovimientoCuenta tipo 'abono'.
      4. Registra un ArqueoMovimiento 'ingreso' en la caja activa,
         de modo que el dinero forme parte del efectivo real de la gaveta.

    Nunca se permite que el abono deje la deuda en negativo.
    """
    try:
        caja = _obtener_caja_activa_o_400(db)
        cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
        if cliente is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente no encontrado",
            )

        monto = Decimal(abono.monto)
        if monto <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El monto del abono debe ser mayor a cero.",
            )

        deuda_actual = Decimal(cliente.saldo_deuda or 0)
        # Permite "adelantos" (sobrante) marcando saldo 0 y sin negativos.
        cliente.saldo_deuda = max(deuda_actual - monto, Decimal("0"))

        concepto = (abono.concepto or "").strip() or "Abono a cuenta corriente"
        db.add(
            MovimientoCuenta(
                cliente_id=cliente.id,
                fecha=now_utc(),
                tipo="abono",
                monto=monto,
                concepto=concepto,
            )
        )
        db.add(
            ArqueoMovimiento(
                arqueo_id=caja.id,
                tipo="ingreso",
                monto=monto,
                concepto=f"Abono {cliente.nombre} ({concepto})",
                metodo_pago="efectivo",
            )
        )

        db.commit()
        db.refresh(cliente)
        return cliente
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar el abono: {str(exc)}",
        )


# ==========================================================================
# MOVIMIENTOS (auxiliar)
# ==========================================================================


@router.get(
    "/movimientos",
    response_model=List[MovimientoCuentaOut],
    summary="Historial de movimientos de cuenta corriente",
)
def historial_movimientos(
    cliente_id: Optional[int] = None,
    limite: int = 100,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Historial de cargos/abonos, opcionalmente filtrado por cliente."""
    try:
        limite = max(1, min(limite, 1000))
        query = db.query(MovimientoCuenta)
        if cliente_id:
            query = query.filter(MovimientoCuenta.cliente_id == cliente_id)
        return query.order_by(MovimientoCuenta.fecha.desc()).limit(limite).all()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar movimientos: {str(exc)}",
        )
