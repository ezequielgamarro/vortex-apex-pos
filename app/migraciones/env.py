"""Entorno de Alembic del POS.

Usa el MISMO motor SQLite de la aplicación (`app.database.engine`), así que la
ruta de la base la decide `app.config` y no se duplica en ningún .ini.
No es un paquete de Python (sin __init__.py): Alembic lo carga como archivo.
"""

from alembic import context

from app.database import Base, engine
import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite no soporta casi ningún ALTER: las migraciones futuras que
            # cambien columnas se aplican reconstruyendo la tabla.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
