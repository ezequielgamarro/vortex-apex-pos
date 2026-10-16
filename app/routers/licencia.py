"""Módulo 6 — Router de licencia (estado + huella + activación por código firmado).

Endpoints:
  GET  /licencia/estado   -> estado actual (público autenticado; lo consulta el
                             frontend para decidir si mostrar la pantalla de
                             bloqueo). Fuerza/persiste el ping de hora.
  GET  /licencia/huella   -> huella de ESTA máquina (para mostrarla al cliente y
                             que se la envíe al proveedor).
  POST /licencia/activar  -> activa/renueva con un CÓDIGO FIRMADO por el
                             proveedor. Verifica con la llave pública Ed25519.

MODELO DE SEGURIDAD (Etapa 2 — código firmado):
  Ya NO existe una "clave de activación" compartida ni el cliente elige su
  fecha. El proveedor firma un código ligado a la huella de esta máquina y a una
  fecha de vencimiento; el POS solo VERIFICA. Esto elimina el agujero previo
  (el cliente con la clave se auto-extendía). Ver `app/services/licencia_firma.py`.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, UsuarioActual
from app.models import Licencia, now_utc
from app.services.licencia_firma import (
    LlavePublicaNoDisponible,
    calcular_huella,
    verificar_codigo_para_maquina,
)
from app.services.licencia_service import evaluar

router = APIRouter(prefix="/licencia", tags=["Licencia"])


class LicenciaEstadoOut(BaseModel):
    cliente_id: str
    estado: str
    bloqueada: bool
    fecha_actual: datetime
    fuente_hora: str
    fecha_vencimiento: datetime | None
    dias_restantes: int | None
    mensaje: str
    # Datos de contacto para regularizar (los define el SuperAdmin/comercio).
    contacto: str = ""


class HuellaOut(BaseModel):
    """Huella de la máquina: la muestra el POS y el cliente la envía al proveedor."""

    cliente_id: str
    huella: str


class ActivarLicenciaIn(BaseModel):
    # Código firmado por el proveedor (formato VX1.<payload>.<firma>).
    codigo_firmado: str = Field(..., min_length=10)


def _cliente_id_actual(db: Session) -> str:
    """Devuelve el `cliente_id` de la licencia singleton (o 'demo')."""
    lic = db.query(Licencia).first()
    return lic.cliente_id if lic and lic.cliente_id else "demo"


def _estado_out(est, mensaje: str | None = None) -> LicenciaEstadoOut:
    """Serializa el estado de licencia al contrato HTTP (DRY)."""
    return LicenciaEstadoOut(
        cliente_id=est.cliente_id,
        estado=est.estado,
        bloqueada=est.bloqueada,
        fecha_actual=est.fecha_actual,
        fuente_hora=est.fuente_hora,
        fecha_vencimiento=est.fecha_vencimiento,
        dias_restantes=est.dias_restantes,
        mensaje=mensaje if mensaje is not None else est.mensaje,
        contacto=getattr(settings, "LICENCIA_CONTACTO", "") or "",
    )


@router.get("/estado", response_model=LicenciaEstadoOut, summary="Estado de la licencia")
def estado_licencia(
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve el estado de la licencia y refuerza el anti-trampas (ping)."""
    est = evaluar(db, persistir_ping=True)
    return _estado_out(est)


@router.get(
    "/huella",
    response_model=HuellaOut,
    summary="Huella de esta máquina (para solicitar activación)",
)
def huella_maquina(
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve la huella de ESTA máquina según el `cliente_id` de la licencia.

    El cliente la COPIA y se la envía al proveedor (WhatsApp) para que este
    firme una licencia a su medida. La huella no es secreta: sin la firma del
    proveedor no activa nada.
    """
    cid = _cliente_id_actual(db)
    return HuellaOut(cliente_id=cid, huella=calcular_huella(cid))


@router.post(
    "/activar",
    response_model=LicenciaEstadoOut,
    summary="Activar/renovar licencia con un código firmado",
)
def activar_licencia(
    data: ActivarLicenciaIn,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activa o renueva la licencia a partir de un CÓDIGO FIRMADO.

    Requiere ser admin. El código debe haber sido emitido por el proveedor
    (firma Ed25519 válida), ser para ESTA máquina (huella) y contener la fecha
    de vencimiento. NO se confía en datos que ingrese el usuario.

    Fail-secure: si falta la llave pública o el código no es válido, se rechaza.
    """
    if usuario.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador puede activar la licencia.",
        )

    cid = _cliente_id_actual(db)

    try:
        resultado = verificar_codigo_para_maquina(data.codigo_firmado, cid)
    except LlavePublicaNoDisponible:
        # Fail-secure: sin llave pública no se puede verificar nada.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Esta instalación no tiene la llave de verificación del "
                "proveedor. Contactá al soporte para completar la instalación."
            ),
        )

    if not resultado.valido:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Código de activación rechazado: {resultado.motivo}",
        )

    lic = db.query(Licencia).first()
    codigo = data.codigo_firmado.strip()

    # Pegar dos veces el mismo código no es un error: queda como está.
    if lic is not None and (lic.codigo_activacion or "").strip() == codigo:
        return _estado_out(
            evaluar(db, persistir_ping=True), mensaje="Esa licencia ya estaba activa."
        )

    # ANTI-REPETICIÓN: un código viejo no puede volver a aplicarse.
    if lic is not None:
        if resultado.serie is not None:
            if resultado.serie <= int(lic.ultimo_serial or 0):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Código de activación rechazado: es más viejo que la "
                        "licencia ya aplicada. Pedí uno nuevo."
                    ),
                )
        elif lic.codigo_activacion:
            # Código sin serie (formato original): al menos que no retroceda.
            vigente = datetime.combine(resultado.fecha_vencimiento, datetime.min.time())
            if lic.fecha_vencimiento is not None and vigente < lic.fecha_vencimiento:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Código de activación rechazado: vence antes que la "
                        "licencia actual."
                    ),
                )

    # Código válido: aplicar fecha/gracia FIRMADAS (no las que diga el usuario).
    if lic is None:
        lic = Licencia(id=1)
        db.add(lic)

    lic.cliente_id = cid
    # La fecha firmada es date; se guarda como datetime (medianoche) para
    # comparar contra `evaluar`, que trabaja con datetime.
    lic.fecha_vencimiento = datetime.combine(
        resultado.fecha_vencimiento, datetime.min.time()
    )
    lic.dias_gracia = int(resultado.dias_gracia or 0)
    # Se guarda el código firmado: desde ahora el vencimiento se verifica contra
    # la firma, no contra las columnas de arriba.
    lic.codigo_activacion = codigo
    if resultado.serie is not None:
        lic.ultimo_serial = resultado.serie
    lic.estado = "activa"
    lic.ultimo_ping = now_utc()
    lic.actualizado_en = now_utc()
    db.commit()
    db.refresh(lic)

    est = evaluar(db, persistir_ping=True)
    return _estado_out(est, mensaje="Licencia activada correctamente.")
