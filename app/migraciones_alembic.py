"""Aplica las migraciones de Alembic al arrancar.

Orden de arranque (ver `app.main`): `create_all` + `run_light_migrations` dejan
el esquema de la versión actual; luego se llama a `aplicar_migraciones()`:

  - Base sin tabla `alembic_version` (nueva o de una versión anterior): se marca
    en la revisión base (`stamp`) y se aplica lo que venga después.
  - Base ya marcada: `upgrade head` aplica las migraciones pendientes.

Antes de cada arranque `app.services.backup` ya copió la base, así que una
migración que falle se puede deshacer restaurando ese respaldo.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.database import engine

logger = logging.getLogger("uvicorn.error")

REVISION_BASE = "0001"


def _config() -> Config:
    # Empaquetado con PyInstaller los archivos van a sys._MEIPASS/app/migraciones.
    raiz = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    cfg = Config()
    cfg.set_main_option("script_location", str(raiz / "app" / "migraciones"))
    return cfg


def aplicar_migraciones() -> None:
    cfg = _config()
    if "alembic_version" not in inspect(engine).get_table_names():
        command.stamp(cfg, REVISION_BASE)
        logger.info("[alembic] Base marcada en la revisión %s.", REVISION_BASE)
    command.upgrade(cfg, "head")
    logger.info("[alembic] Migraciones al día.")
