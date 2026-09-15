"""Reset de fábrica de la base de datos SQLite (modo producción / CI).

Borrando TODAS las tablas del esquema y volviéndolas a crear VACÍAS:
  - productos          -> 0 filas (sin catálogo de prueba)
  - ventas / items     -> 0 filas
  - arqueo / movimientos -> 0 filas
  - usuarios           -> 0 filas

EL ADMINISTRADOR SE SIEMBRA AUTOMÁTICAMENTE EN EL SIGUIENTE ARRANQUE del
backend vía el `lifespan` de la app (app/main.py -> app.seed). Por eso este
script NO deja el admin: lo crea el backend cuando detecte "base vacía", tal
como se pide para PC nuevas.

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
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402


def reset_database() -> None:
    """Elimina y recrea todas las tablas. Devuelve la BD a cero datos."""
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
            "[reset] Base de datos reiniciada OK. 'usuarios' se sembrará "
            f"automáticamente en el siguiente arranque (email="
            f"{(settings.ADMIN_EMAIL or 'admin@pos.local').strip().lower()})."
        )
    finally:
        db.close()


if __name__ == "__main__":
    reset_database()
