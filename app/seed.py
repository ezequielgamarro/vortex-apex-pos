"""Administración automática de la base de datos para arranque en producción.

Responsabilidades:
  1. `crear_admin_si_hace_falta()`: se invoca en el `lifespan` de la aplicación
     tras `Base.metadata.create_all(...)`. Si la tabla `usuarios` está VACÍA
     (base recién creada o reseteada para producción), crea de forma automática
     el usuario administrador por defecto, de modo que en una PC nueva el
     responsable pueda iniciar sesión de inmediato sin registro manual.

Reglas de idempotencia y seguridad:
  * SÓLO siembra el admin cuando NO existe NINGÚN usuario en la tabla.
    Así nunca pisa una base que ya tiene administradores gestionados a mano,
    ni "reinicia" contraseñas en cada arranque.
  * La contraseña se lee de entorno/settings (`ADMIN_PASSWORD`) y es OPCIONAL:
    - Si se configura `ADMIN_PASSWORD` (desarrollo/automatización), se crea ese
      administrador.
    - Si NO se configura, NO se crea ninguna cuenta. Ya no existe una
      credencial por defecto igual en todas las instalaciones: el primer
      administrador de un cliente se da de alta con el asistente de primer
      arranque, que exige un código firmado por el proveedor
      (ver `app/routers/setup.py`).
    Solo se almacena el hash (nunca el valor en plano).
"""

import logging
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import hash_password
from app.models import Usuario

logger = logging.getLogger("uvicorn.error")
# Valores por defecto (una instalación puede personalizarlos vía entorno):
FALLBACK_EMAIL = "admin@pos.local"
FALLBACK_NOMBRE = "Administrador"


def _email_default() -> str:
    return (settings.ADMIN_EMAIL or FALLBACK_EMAIL).strip().lower()


def _nombre_default() -> str:
    return (settings.ADMIN_NOMBRE_COMPLETO or FALLBACK_NOMBRE).strip()


def crear_admin_si_hace_falta(db: Session) -> tuple[bool, str | None]:
    """Siembra un admin SOLO si la base está vacía Y hay ADMIN_PASSWORD definida.

    Returns:
        (creado: bool, password_plano: Optional[str])
        - password_plano siempre es None: la contraseña viene de
          ADMIN_PASSWORD y nunca se expone en plano desde aquí.
    """
    total_usuarios = db.query(func.count(Usuario.id)).scalar() or 0
    if total_usuarios:
        # No es una base "virgen": no pisamos lo que haya.
        return False, None

    plano = (settings.ADMIN_PASSWORD or "").strip()
    if not plano:
        # Instalación nueva sin semilla: queda esperando el asistente de alta.
        logger.info(
            "[seed] Base vacía y sin ADMIN_PASSWORD: no se crea ningún usuario. "
            "Falta el alta inicial (asistente de primer arranque)."
        )
        return False, None

    email = _email_default()
    nombre = _nombre_default()
    password_hash = hash_password(plano)
    admin = Usuario(
        email=email,
        nombre_completo=nombre,
        password_hash=password_hash,
        rol="admin",
        activo=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    logger.info(
        "[seed] Base de datos vacía. Usuario administrador creado "
        "-> id=%s email=%s rol=%s (contraseña tomada de ADMIN_PASSWORD)",
        admin.id,
        admin.email,
        admin.rol,
    )
    return True, None


def verificar_estado(db: Session) -> None:
    """Helper de diagnóstico para desarrollo / reset (no requerido por prod)."""
    logger.info(
        "[seed] Usuarios en BD: %d",
        db.query(func.count(Usuario.id)).scalar() or 0,
    )
