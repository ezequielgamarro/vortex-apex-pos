"""Backup automático de la base SQLite (copia rotada junto a la base).

Antes de aplicar migraciones, si el último respaldo tiene más de `HORAS_MIN`
horas, se copia la base a `<carpeta de datos>/backups/pos_local-AAAAMMDD-HHMMSS.db`
y se conservan solo las últimas `CONSERVAR` copias.

Usa la API de backup de SQLite (`Connection.backup`): produce una copia
consistente aunque la base esté en uso o en modo WAL, a diferencia de copiar el
archivo a mano (que perdería lo que aún está en el `-wal`).

LÍMITE HONESTO: la copia vive en la misma PC. Protege de un error del programa,
una migración fallida o un borrado accidental de datos, pero NO de la pérdida o
rotura del disco: para eso el comercio debe copiar la carpeta `backups` a un
pendrive o a la nube.
"""

import logging
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from app.database import _DB_PATH

logger = logging.getLogger("uvicorn.error")

HORAS_MIN = 20
CONSERVAR = 7
_PATRON = re.compile(r"^pos_local-\d{8}-\d{6}\.db$")


def _dir_backups(ruta_db: Path) -> Path:
    return ruta_db.parent / "backups"


def respaldar_si_corresponde(
    ruta_db: str | Path = _DB_PATH,
    horas_min: float = HORAS_MIN,
    conservar: int = CONSERVAR,
    forzar: bool = False,
) -> Path | None:
    """Crea un respaldo si hace falta. Devuelve su ruta, o None si no se hizo.

    Nunca lanza: un fallo de backup no debe impedir que el POS arranque; se
    registra y se sigue.
    """
    try:
        origen = Path(ruta_db)
        if not origen.exists() or origen.stat().st_size == 0:
            return None  # instalación nueva: no hay nada que respaldar

        destino_dir = _dir_backups(origen)
        destino_dir.mkdir(parents=True, exist_ok=True)
        previos = sorted(p for p in destino_dir.iterdir() if _PATRON.match(p.name))

        if not forzar and previos:
            antig_h = (time.time() - previos[-1].stat().st_mtime) / 3600
            if antig_h < horas_min:
                return None

        destino = destino_dir / f"pos_local-{datetime.now():%Y%m%d-%H%M%S}.db"
        src = sqlite3.connect(str(origen))
        try:
            dst = sqlite3.connect(str(destino))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()

        # Rotación: solo archivos con el nombre exacto de nuestros respaldos.
        todos = sorted(p for p in destino_dir.iterdir() if _PATRON.match(p.name))
        for viejo in todos[:-conservar] if conservar > 0 else []:
            try:
                viejo.unlink(missing_ok=True)
            except OSError as exc:
                # El respaldo nuevo ya existe: un archivo viejo en uso no lo anula.
                logger.warning("[backup] No se pudo borrar %s: %s", viejo.name, exc)

        logger.info("[backup] Respaldo creado: %s", destino)
        return destino
    except Exception as exc:  # noqa: BLE001
        logger.warning("[backup] No se pudo crear el respaldo: %s", exc)
        return None
