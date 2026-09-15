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
  * La contraseña se lee de entorno/settings (`ADMIN_PASSWORD`).
    - Si se configura `ADMIN_PASSWORD`, se usa esa.
    - Si NO se configura, se usa la credencial por defecto documentada
      `admin@pos.local` / `admin123` (FALLBACK_*). Esto garantiza que el
      dueño siempre pueda entrar de forma predecible en una instalación
      nueva. Un responsable puede sobreescribir esta por defecto definiendo
      `ADMIN_PASSWORD` en el entorno antes del primer arranque.
    Solo se almacena el hash (nunca el valor en plano). Se recomienda cambiar
    la contraseña por defecto en entornos reales que lo requieran.
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
FALLBACK_PASSWORD = "admin123"


def _email_default() -> str:
    return (settings.ADMIN_EMAIL or FALLBACK_EMAIL).strip().lower()


def _nombre_default() -> str:
    return (settings.ADMIN_NOMBRE_COMPLETO or FALLBACK_NOMBRE).strip()


def _password_default() -> str:
    """Contraseña a usar si no se configura ADMIN_PASSWORD.
    Prioridad:
      1. Valor explícito en settings.ADMIN_PASSWORD (recomendado en prod).
      2. Fallback documentado FALLBACK_PASSWORD ("admin123").
    """
    plano = (settings.ADMIN_PASSWORD or "").strip()
    return plano or FALLBACK_PASSWORD


def crear_admin_si_hace_falta(db: Session) -> tuple[bool, str | None]:
    """Siembra el admin por defecto SOLO si la tabla de usuarios está vacía.

    Returns:
        (creado: bool, password_plano: Optional[str])
        - password_plano siempre es None: la contraseña se define por
          ADMIN_PASSWORD o el fallback documentado (admin123) y nunca se
          expone en plano desde aquí.
    """
    total_usuarios = db.query(func.count(Usuario.id)).scalar() or 0
    if total_usuarios:
        # No es una base "virgen": no pisamos lo que haya.
        return False, None

    email = _email_default()
    nombre = _nombre_default()
    password_hash = hash_password(_password_default())
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
        "-> id=%s email=%s rol=%s (password: fallback ADMIN_PASSWORD o 'admin123')",
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
