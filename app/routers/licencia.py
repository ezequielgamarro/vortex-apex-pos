"""Módulo 6 — Router de licencia (estado + activación/sincronización).

Endpoints:
  GET  /licencia/estado   -> estado actual (público autenticado; lo consulta
                             el frontend para decidir si mostrar la pantalla de
                             bloqueo). Fuerza/persiste el ping de hora.
  POST /licencia/activar  -> carga/renueva la licencia con un `cliente_id` y
                             `fecha_vencimiento` (lo ejecuta el instalador o un
                             admin con la clave del SuperAdmin).
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, UsuarioActual
from app.models import Licencia, now_utc
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


class ActivarLicenciaIn(BaseModel):
    cliente_id: str = Field(..., min_length=1, max_length=120)
    fecha_vencimiento: datetime = Field(
        ..., description="Nueva fecha de vencimiento (ISO 8601)"
    )
    dias_gracia: int = Field(3, ge=0, le=60)
    # Clave de activación (token compartido con el SuperAdmin). Evita que un
    # usuario cualquiera extienda su propia licencia sin permiso.
    clave_activacion: str


@router.get("/estado", response_model=LicenciaEstadoOut, summary="Estado de la licencia")
def estado_licencia(
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve el estado de la licencia y refuerza el anti-trampas (ping)."""
    est = evaluar(db, persistir_ping=True)
    return LicenciaEstadoOut(
        cliente_id=est.cliente_id,
        estado=est.estado,
        bloqueada=est.bloqueada,
        fecha_actual=est.fecha_actual,
        fuente_hora=est.fuente_hora,
        fecha_vencimiento=est.fecha_vencimiento,
        dias_restantes=est.dias_restantes,
        mensaje=est.mensaje,
        contacto=getattr(settings, "LICENCIA_CONTACTO", "") or "",
    )


@router.post(
    "/activar",
    response_model=LicenciaEstadoOut,
    summary="Activar/renovar licencia (admin + clave de activación)",
)
def activar_licencia(
    data: ActivarLicenciaIn,
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Carga o renueva la licencia. Requiere clave de activación válida."""
    if usuario.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador puede activar la licencia.",
        )

    esperada = getattr(settings, "CLAVE_ACTIVACION", "") or "ACTIVACION-DEMO"
    if data.clave_activacion != esperada:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clave de activación inválida.",
        )

    lic = db.query(Licencia).first()
    if lic is None:
        lic = Licencia(id=1)
        db.add(lic)

    lic.cliente_id = data.cliente_id
    lic.fecha_vencimiento = data.fecha_vencimiento.replace(tzinfo=None)
    lic.dias_gracia = data.dias_gracia
    lic.estado = "activa"
    lic.ultimo_ping = now_utc()
    lic.actualizado_en = now_utc()
    db.commit()
    db.refresh(lic)

    est = evaluar(db, persistir_ping=True)
    return LicenciaEstadoOut(
        cliente_id=est.cliente_id,
        estado=est.estado,
        bloqueada=est.bloqueada,
        fecha_actual=est.fecha_actual,
        fuente_hora=est.fuente_hora,
        fecha_vencimiento=est.fecha_vencimiento,
        dias_restantes=est.dias_restantes,
        mensaje="Licencia activada correctamente.",
        contacto=getattr(settings, "LICENCIA_CONTACTO", "") or "",
    )
