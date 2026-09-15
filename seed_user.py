"""Seed de un usuario administrador de prueba en pos_local.db.

Inserta (o reinicia si ya existe) un usuario local de acceso con:
  email   : admin@pos.local
  password: admin123        (se almacena sólo el hash bcrypt)
  rol     : admin

Uso (desde la raíz del proyecto, donde vive pos_local.db):
    python seed_user.py
    # o, con el venv activado:
    ./app/.venv/Scripts/python.exe seed_user.py

Persistencia: usa SessionLocal/Base de app.database (SQLite local). Es
idempotente: si el email ya existe, actualiza su password_hash y rol.
"""
import sys
from pathlib import Path

# Asegura que el paquete `app` sea importable desde la raíz del proyecto.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.dependencies import hash_password  # noqa: E402
from app.models import Usuario  # noqa: E402

EMAIL = "admin@pos.local"
PASSWORD = "admin123"
NOMBRE = "Administrador"
ROL = "admin"


def main() -> None:
    # Garantiza que exista la tabla `usuarios` (idempotente).
    Base.metadata.create_all(bind=engine)

    hashed = hash_password(PASSWORD)
    db = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(Usuario.email == EMAIL).first()
        if usuario is None:
            usuario = Usuario(
                email=EMAIL,
                nombre_completo=NOMBRE,
                password_hash=hashed,
                rol=ROL,
                activo=True,
            )
            db.add(usuario)
            db.commit()
            db.refresh(usuario)
            print(
                f"[seed] Usuario creado OK  -> {usuario.email} "
                f"(id={usuario.id}, rol={usuario.rol})"
            )
        else:
            usuario.password_hash = hashed
            usuario.rol = ROL
            usuario.activo = True
            usuario.nombre_completo = usuario.nombre_completo or NOMBRE
            db.commit()
            db.refresh(usuario)
            print(
                f"[seed] Usuario ya existía -> password/rol actualizados "
                f"(id={usuario.id}, rol={usuario.rol})"
            )
        print(f"[seed] Credenciales: {EMAIL} / {PASSWORD} (rol={ROL})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
