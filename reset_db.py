"""Reset de fábrica de la base de datos SQLite (modo producción / CI).

Borrando TODAS las tablas del esquema y volviéndolas a crear VACÍAS:
  - productos          -> 0 filas (sin catálogo de prueba)
  - ventas / items     -> 0 filas
  - arqueo / movimientos -> 0 filas
  - usuarios           -> 0 filas

Es DESTRUCTIVO. Antes de borrar:
  - pide confirmación (hay que escribir el nombre de la base), y
  - guarda un respaldo en la carpeta `backups` junto a la base.

La base queda sin usuarios: el siguiente arranque abre el asistente de
configuración inicial (código de alta firmado) o, solo en desarrollo, siembra un
admin si definís ADMIN_PASSWORD (ver app/seed.py).

Uso (desde la raíz del proyecto):
    ./app/.venv/Scripts/python.exe reset_db.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Importar modelos ANTES de drop/create para que queden registrados en metadata.
import app.models  # noqa: F401,E402
from app.database import _DB_PATH, Base, SessionLocal, engine  # noqa: E402
from app.services.backup import respaldar_si_corresponde  # noqa: E402


def _confirmar() -> bool:
    """Pide escribir el nombre de la base. Falla cerrado si no hay consola."""
    nombre = Path(_DB_PATH).name
    print(f"[reset] Se BORRARÁN TODOS LOS DATOS de: {_DB_PATH}")
    try:
        escrito = input(f"[reset] Para continuar escribí exactamente «{nombre}»: ")
    except EOFError:
        return False
    return escrito.strip() == nombre


def reset_database() -> None:
    """Elimina y recrea todas las tablas. Devuelve la BD a cero datos."""
    if not _confirmar():
        print("[reset] Cancelado: no se tocó nada.")
        return
    copia = respaldar_si_corresponde(forzar=True)
    if copia is None and Path(_DB_PATH).exists() and Path(_DB_PATH).stat().st_size:
        print("[reset] No se pudo crear el respaldo previo. Cancelado: no se tocó nada.")
        return
    if copia is not None:
        print(f"[reset] Respaldo previo guardado en: {copia}")
    # Lógica: drop_all + create_all es la forma más robusta y limpia de "vaciar":
    db = SessionLocal()
    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        # Reporte final
        from sqlalchemy import text

        with engine.connect() as conn:
            for (tabla,) in conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ):
                (total,) = conn.execute(text(f'SELECT COUNT(*) FROM "{tabla}"')).one()
                print(f"[reset] tabla {tabla:24s} -> {total} filas")
        print(
            "[reset] Base de datos reiniciada OK. Sin usuarios: el siguiente "
            "arranque pide el alta inicial."
        )
    finally:
        db.close()


if __name__ == "__main__":
    reset_database()
