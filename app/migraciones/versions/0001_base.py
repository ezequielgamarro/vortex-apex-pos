"""Esquema base (v1.4.0).

Punto de partida: las tablas de esta versión las crea `Base.metadata.create_all`
y `app.migrations.run_light_migrations` (columnas agregadas a mano en versiones
anteriores). Esta revisión no cambia nada; solo marca ese esquema como la base
desde la que se aplican las migraciones futuras (0002, 0003, ...).

Revision ID: 0001
Revises:
"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
