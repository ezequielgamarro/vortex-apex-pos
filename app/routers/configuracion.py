"""Router de la configuración global del negocio.

Expone el *singleton* de configuración del comercio (ver
`models.ConfiguracionNegocio`). El nombre configurado aquí se imprime como
encabezado en los tickets de venta y de cierre de caja.

Reglas de negocio:
- Lectura (`GET`): cualquier usuario autenticado (cajero o admin), porque el
  POS lo necesita para imprimir tickets.
- Escritura (`PUT`): SOLO rol admin — es una decisión de configuración que
  afecta a toda la instalación del comercio.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, requiere_rol, UsuarioActual
from app.models import ConfiguracionNegocio
from app.schemas.configuracion import ConfiguracionOut, ConfiguracionUpdate

router = APIRouter(prefix="/configuracion", tags=["Configuración"])


def _obtener_o_crear(db: Session) -> ConfiguracionNegocio:
    """Devuelve la fila singleton (id=1), creándola vacía si no existe.

    Garantiza idempotencia: nunca hay más de una fila de configuración.
    """
    cfg = db.get(ConfiguracionNegocio, 1)
    if cfg is None:
        cfg = ConfiguracionNegocio(id=1, nombre="")
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get(
    "",
    response_model=ConfiguracionOut,
    summary="Obtener la configuración del negocio",
)
def obtener_configuracion(
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve la configuración actual (nombre del negocio)."""
    try:
        return _obtener_o_crear(db)
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al leer la configuración: {str(exc)}",
        )


@router.put(
    "",
    response_model=ConfiguracionOut,
    summary="Actualizar la configuración del negocio (solo admin)",
)
def actualizar_configuracion(
    datos: ConfiguracionUpdate,
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
    db: Session = Depends(get_db),
):
    """Persiste el nombre del negocio. Solo el administrador puede cambiarlo."""
    try:
        cfg = _obtener_o_crear(db)
        cfg.nombre = datos.nombre
        cfg.actualizado_en = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        db.refresh(cfg)
        return cfg
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar la configuración: {str(exc)}",
        )
