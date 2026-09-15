"""Restablece el usuario administrador por defecto (herramienta de soporte).

Útil cuando NO se conoce la contraseña del administrador —por ejemplo, si la
aplicación se sembró con una contraseña aleatoria en un primer arranque— o
cuando se quiere volver a las credenciales por defecto documentadas:

    email       : admin@pos.local
    contraseña  : admin123

Dónde vive la base:
  La aplicación decide la ubicación de `pos_local.db` con el mismo orden de
  precedencia de `app.database`:
    1. $env:USER_DATA_DIR  (Electron la setea como `app.getPath('userData')`).
    2. Junto al ejecutable si está compilado (sys.frozen).
    3. Directorio actual (desarrollo).

Uso (desde la raíz del proyecto, con el venv activado):
    .\app\.venv\Scripts\python.exe reset_admin.py
    # personalizando credenciales:
    $env:ADMIN_EMAIL="admin@pos.local"; $env:ADMIN_PASSWORD="admin123"; .\app\.venv\Scripts\python.exe reset_admin.py
    .\app\.venv\Scripts\python.exe reset_admin.py "otro@correo.com" "passwordNueva"
"""
import sys

from pathlib import Path

# Aseguramos que el paquete `app` sea importable desde la raíz del proyecto.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.database import SessionLocal, _DB_PATH  # noqa: E402
from app.dependencies import hash_password  # noqa: E402
from app.models import Usuario  # noqa: E402


def main() -> int:
    # Valores pedidos o los de entorno/settings, con fallback documentado.
    email = (sys.argv[1] if len(sys.argv) > 1 else (settings.ADMIN_EMAIL or "admin@pos.local")).strip().lower()
    password = sys.argv[2] if len(sys.argv) > 2 else (settings.ADMIN_PASSWORD or "admin123")

    db = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(Usuario.email == email).first()
        if usuario is None:
            print(f"[reset_admin] NO existe un usuario con email {email}")
            print("             Creándolo como admin activo...")
            usuario = Usuario(
                email=email,
                nombre_completo=settings.ADMIN_NOMBRE_COMPLETO or "Administrador",
                password_hash=hash_password(password),
                rol="admin",
                activo=True,
            )
            db.add(usuario)
        else:
            print(f"[reset_admin] Usuario encontrado: {usuario.email} (rol actual={usuario.rol})")
            usuario.password_hash = hash_password(password)
            usuario.rol = "admin"
            usuario.activo = True
        db.commit()
        db.refresh(usuario)
        print(f"[reset_admin] OK ->  email: {usuario.email} | rol: {usuario.rol} | activo: True")
        print(f"[reset_admin] contraseña asignada (no se muestra por seguridad).")
        print(f"[reset_admin] base usada: {_DB_PATH}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
