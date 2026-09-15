"""Router de Arqueo de Caja.

Persistencia local vía SQLAlchemy + SQLite con `db: Session = Depends(get_db)`.

Endpoints:
    POST /abrir       -> Abre la caja registrando el monto inicial en efectivo.
    POST /movimiento  -> Registra entradas/salidas manuales de dinero de la caja activa.
    POST /cerrar      -> Calcula el total esperado (monto inicial + ventas en efectivo
                         + ingresos - egresos) y lo compara con el monto final del usuario.
    GET  /activo      -> Consulta la caja actualmente abierta.
    GET  /resumen     -> Devuelve el resumen de la caja activa (movimientos y ventas).
    GET  /historial   -> Historial de arqueos ya cerrados.
    GET  /{arqueo_id}/resumen -> Detalle exhaustivo de un arqueo por su ID (cerrado o activo).

El helper `_calcular_totales` evalúa la *ventana temporal* del arqueo para que
los totales de una caja histórica jamás absorban ventas de turnos posteriores.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, UsuarioActual
from app.models import Arqueo, ArqueoMovimiento, Venta, now_utc
from app.schemas.arqueo import (
    ArqueoApertura,
    IngresoEgresoCreate,
    ArqueoCierre,
    MovimientoOut,
    ArqueoOut,
    CierreOut,
)

router = APIRouter(prefix="/arqueo", tags=["Arqueo de Caja"])

METODOS_EFECTIVO = {"efectivo"}


# ------------------------------------------------------------------
# Helpers internos
# ------------------------------------------------------------------
def _obtener_caja_activa(db: Session) -> Arqueo:
    """Obtiene la caja abierta vigente. Lanza 409 si no hay ninguna."""
    caja = db.query(Arqueo).filter(Arqueo.estado == "abierto").first()
    if caja is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay una caja abierta. Abre la caja primero.",
        )
    return caja


def _calcular_totales(db: Session, caja: Arqueo) -> dict:
    """Calcula los totales económicos de un arqueo (turno de caja).

    Evalúa la VENTANA TEMPORAL del arqueo —no "todas las ventas del presente"—
    para ser 100% retrocompatible con la caja activa y, a la vez, correcto para
    cajas ya cerradas:

      - Límite inferior: `fecha >= fecha_apertura` (ventas posteriores a la
        apertura que pertenecen al turno).
      - Límite superior: si `caja.fecha_cierre` existe (turno cerrado), la
        consulta se acota a `fecha <= fecha_cierre`. Así un historial cerrado
        jamás absorbe ventas de turnos posteriores. Si la caja sigue abierta
        (`fecha_cierre is None`), NO se aplica límite superior — conservando el
        comportamiento original de la caja en vivo.

    Retorna el desglose: ventas en efectivo (las que "viven" en la gaveta),
    ventas por otros medios (tarjeta/transferencia/mixto), fiado a cuenta
    corriente y los movimientos manuales (ingresos/egresos) del turno.
    """
    # Filtro inicial del turno (desde su apertura) EXCLUYENDO anuladas:
    # las ventas anuladas son soft-delete y no representan dinero real.
    condiciones_ventas = [
        Venta.fecha >= caja.fecha_apertura,
        Venta.estado != "anulada",
    ]

    # Si la caja está cerrada, acotar la ventana por el cierre: las ventas
    # registradas DESPUÉS de su fecha_cierre pertenecen a turnos siguientes.
    if caja.fecha_cierre is not None:
        condiciones_ventas.append(Venta.fecha <= caja.fecha_cierre)

    ventas = db.query(Venta).filter(*condiciones_ventas).all()

    ventas_efectivo = Decimal("0")
    ventas_tarjeta = Decimal("0")
    ventas_transferencia = Decimal("0")
    ventas_mixto = Decimal("0")
    # Fiado a cuenta corriente: importe registrado pero NO físico en gaveta.
    ventas_credito = Decimal("0")

    for v in ventas:
        monto = Decimal(v.total)
        if v.metodo_pago == "efectivo":
            ventas_efectivo += monto
        elif v.metodo_pago == "tarjeta":
            ventas_tarjeta += monto
        elif v.metodo_pago == "transferencia":
            ventas_transferencia += monto
        elif v.metodo_pago == "mixto":
            ventas_mixto += monto
        elif v.metodo_pago == "cuenta_corriente":
            ventas_credito += monto

    # "Otros medios": todo lo que NO son ventas al contado (y tampoco fiado).
    otros_medios = ventas_tarjeta + ventas_transferencia + ventas_mixto

    # Movimientos manuales del arqueo
    total_ingresos = sum(
        (Decimal(m.monto) for m in caja.movimientos if m.tipo == "ingreso"),
        Decimal("0"),
    )
    total_egresos = sum(
        (Decimal(m.monto) for m in caja.movimientos if m.tipo == "egreso"),
        Decimal("0"),
    )

    return {
        "ventas_efectivo": ventas_efectivo,
        "ventas_tarjeta": ventas_tarjeta,
        "ventas_transferencia": ventas_transferencia,
        "ventas_mixto": ventas_mixto,
        "ventas_credito": ventas_credito,
        "otros_medios": otros_medios,
        "ingresos_manuales": total_ingresos,
        "egresos_manuales": total_egresos,
    }


# ------------------------------------------------------------------
# POST /arqueo/abrir
# ------------------------------------------------------------------
@router.post(
    "/abrir",
    response_model=ArqueoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Abrir caja",
)
def abrir_caja(
    apertura: ArqueoApertura,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Abre la caja registradora con el monto inicial en efectivo.

    Rechaza la operación si ya existe una caja abierta.
    """
    try:
        ya_abierta = db.query(Arqueo).filter(Arqueo.estado == "abierto").first()
        if ya_abierta is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una caja abierta. Ciérrala antes de abrir una nueva.",
            )

        nueva = Arqueo(
            monto_inicial=apertura.monto_inicial,
            estado="abierto",
            observaciones_apertura=apertura.observaciones,
        )
        db.add(nueva)
        db.commit()
        db.refresh(nueva)
        return nueva
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al abrir caja: {str(exc)}",
        )


# ------------------------------------------------------------------
# POST /arqueo/movimiento
# ------------------------------------------------------------------
@router.post(
    "/movimiento",
    response_model=MovimientoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar ingreso/egreso manual de dinero",
)
def registrar_movimiento(
    movimiento: IngresoEgresoCreate,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Registra una entrada (ingreso) o salida (egreso) manual en la caja activa."""
    try:
        caja = _obtener_caja_activa(db)
        nuevo = ArqueoMovimiento(
            arqueo_id=caja.id,
            tipo=movimiento.tipo,
            monto=movimiento.monto,
            concepto=movimiento.concepto,
            metodo_pago=movimiento.metodo_pago,
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
            detail=f"Error al registrar movimiento: {str(exc)}",
        )


# ------------------------------------------------------------------
# POST /arqueo/cerrar
# ------------------------------------------------------------------
@router.post(
    "/cerrar",
    response_model=CierreOut,
    summary="Cerrar caja",
)
def cerrar_caja(
    cierre: ArqueoCierre,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cierra la caja activa y calcula el total esperado.

    Fórmula del total esperado:
        monto_inicial + ventas_efectivo + ingresos_manuales - egresos_manuales

    Compara el total esperado con el `monto_final` ingresado por el usuario
    y guarda la diferencia (sobrante/socotro).
    """
    try:
        caja = _obtener_caja_activa(db)

        monto_inicial = Decimal(caja.monto_inicial or 0)
        totales = _calcular_totales(db, caja)

        total_esperado = (
            monto_inicial
            + totales["ventas_efectivo"]
            + totales["ingresos_manuales"]
            - totales["egresos_manuales"]
        )
        if total_esperado < 0:
            total_esperado = Decimal("0")

        monto_final = cierre.monto_final
        diferencia = monto_final - total_esperado
        fecha_cierre = now_utc()

        # Cerrar y persistir
        caja.estado = "cerrado"
        caja.fecha_cierre = fecha_cierre
        caja.monto_esperado = total_esperado
        caja.monto_real = monto_final
        caja.diferencia = diferencia
        caja.observaciones_cierre = cierre.observaciones
        db.commit()

        return CierreOut(
            arqueo_id=caja.id,
            fecha_apertura=caja.fecha_apertura,
            fecha_cierre=caja.fecha_cierre,
            monto_inicial=monto_inicial,
            ventas_efectivo=totales["ventas_efectivo"],
            ventas_tarjeta=totales["ventas_tarjeta"],
            ventas_transferencia=totales["ventas_transferencia"],
            ventas_mixto=totales["ventas_mixto"],
            ventas_credito=totales["ventas_credito"],
            otros_medios=totales["otros_medios"],
            ingresos_manuales=totales["ingresos_manuales"],
            egresos_manuales=totales["egresos_manuales"],
            total_esperado=total_esperado,
            monto_final=monto_final,
            diferencia=diferencia,
            observaciones=cierre.observaciones,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al cerrar caja: {str(exc)}",
        )


# ------------------------------------------------------------------
# Utilidades de consulta
# ------------------------------------------------------------------
@router.get(
    "/activo",
    response_model=Optional[ArqueoOut],
    summary="Consultar caja activa",
)
def caja_activa(
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve la caja actualmente abierta, o null si no hay ninguna."""
    try:
        return db.query(Arqueo).filter(Arqueo.estado == "abierto").first()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar caja activa: {str(exc)}",
        )


def _serializar_resumen(caja: Arqueo, totales: dict) -> dict:
    """Arma el dict de resumen financiero de un arqueo a partir de sus totales.

    Devuelve la estructura compartida por `GET /resumen` (caja activa) y
    `GET /{arqueo_id}/resumen` (caja activa o histórica por ID), evitando que
    ambas rutas dupliquen el armado y deriven en contratos inconsistentes.
    """
    monto_inicial = Decimal(caja.monto_inicial or 0)
    total_esperado = (
        monto_inicial
        + totales["ventas_efectivo"]
        + totales["ingresos_manuales"]
        - totales["egresos_manuales"]
    )
    if total_esperado < 0:
        total_esperado = Decimal("0")

    return {
        "caja": {
            "id": caja.id,
            "fecha_apertura": caja.fecha_apertura,
            "fecha_cierre": caja.fecha_cierre,
            "monto_inicial": monto_inicial,
            "monto_esperado": (
                Decimal(caja.monto_esperado)
                if caja.monto_esperado is not None
                else total_esperado
            ),
            "monto_real": (
                Decimal(caja.monto_real) if caja.monto_real is not None else None
            ),
            "monto_final": (
                Decimal(caja.monto_real) if caja.monto_real is not None else None
            ),
            "diferencia": (
                Decimal(caja.diferencia) if caja.diferencia is not None else None
            ),
            "estado": caja.estado,
            "observaciones_apertura": caja.observaciones_apertura,
            "observaciones_cierre": caja.observaciones_cierre,
        },
        "monto_inicial": monto_inicial,
        "ventas_efectivo": totales["ventas_efectivo"],
        "ventas_tarjeta": totales["ventas_tarjeta"],
        "ventas_transferencia": totales["ventas_transferencia"],
        "ventas_mixto": totales["ventas_mixto"],
        "ventas_credito": totales["ventas_credito"],
        "otros_medios": totales["otros_medios"],
        "ingresos_manuales": totales["ingresos_manuales"],
        "egresos_manuales": totales["egresos_manuales"],
        "total_esperado": total_esperado,
        "movimientos": [
            {
                "id": m.id,
                "tipo": m.tipo,
                "monto": Decimal(m.monto),
                "concepto": m.concepto,
                "metodo_pago": m.metodo_pago,
                "fecha": m.fecha,
            }
            for m in caja.movimientos
        ],
    }


@router.get(
    "/resumen",
    summary="Resumen de la caja activa",
)
def resumen_caja(
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve un resumen financiero de la caja abierta:
    movimientos y desglose de las ventas del turno.
    """
    try:
        caja = _obtener_caja_activa(db)
        totales = _calcular_totales(db, caja)
        return _serializar_resumen(caja, totales)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar resumen: {str(exc)}",
        )


@router.get(
    "/{arqueo_id}/resumen",
    summary="Resumen detallado de un arqueo por su ID",
)
def resumen_arqueo_por_id(
    arqueo_id: UUID,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve el detalle exhaustivo de un arqueo (turno de caja) por su ID.

    A diferencia de `GET /resumen` (que sólo atiende la caja ACTIVA), esta ruta
    permite consultar cualquier turno —concreto o histórico— mediante el helper
    refactorizado `_calcular_totales`, que acota la ventana temporal por su
    `fecha_apertura`/`fecha_cierre`. Es la pieza que alimenta el ticket de
    cierre imprimible del Historial de Cajas.

    Devuelve 404 si el arqueo no existe.
    """
    try:
        caja = db.query(Arqueo).filter(Arqueo.id == arqueo_id).first()
        if caja is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Arqueo no encontrado.",
            )

        totales = _calcular_totales(db, caja)
        return _serializar_resumen(caja, totales)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar el resumen del arqueo: {str(exc)}",
        )


@router.get(
    "/historial",
    response_model=List[ArqueoOut],
    summary="Historial de arqueos cerrados",
)
def historial_arqueos(
    limite: int = 50,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve los arqueos ya cerrados, ordenados del más reciente al más antiguo."""
    try:
        limite = max(1, min(limite, 200))
        return (
            db.query(Arqueo)
            .filter(Arqueo.estado == "cerrado")
            .order_by(Arqueo.fecha_cierre.desc())
            .limit(limite)
            .all()
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar historial: {str(exc)}",
        )
