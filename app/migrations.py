"""Migraciones ligeras y seguras para bases SQLite ya existentes.

SQLAlchemy `Base.metadata.create_all` crea las TABLAS nuevas (p. ej.
`categorias`, `clientes`, `movimientos_cuenta`, que se registran en los
modelos) aunque la base ya exista. PERO **no agrega columnas nuevas a tablas
ya creadas**. Para no destruir datos en instalaciones existentes, aquí se
agregan las columnas faltantes de forma idempotente usando `PRAGMA table_info`
+ `ALTER TABLE ... ADD COLUMN`.

Principios:
  - Sólo agrega; nunca borra ni altera tipos de columnas existentes.
  - Idempotente: si la columna ya existe no hace nada.
  - No falla el arranque: ante cualquier error inesperado lo registra y sigue.
"""

import logging

from sqlalchemy import text

logger = logging.getLogger("uvicorn.error")


def _columnas(db, tabla: str) -> set[str]:
    """Devuelve el conjunto de nombres de columnas de una tabla SQLite."""
    filas = db.execute(text(f'PRAGMA table_info("{tabla}")')).fetchall()
    return {fila[1] for fila in filas}


def _agregar_columna(db, tabla: str, nombre: str, ddl: str) -> None:
    """Agrega una columna a una tabla existente de forma condicional."""
    if nombre not in _columnas(db, tabla):
        db.execute(text(f'ALTER TABLE "{tabla}" ADD COLUMN "{nombre}" {ddl}'))
        logger.info("[migracion] Columna agregada: %s.%s", tabla, nombre)


def run_light_migrations(db) -> None:
    """Aplica migraciones ligeras sobre la conexión/autorización actual.

    Se llama luego de `Base.metadata.create_all` (que ya habrá creado las
    tablas nuevas). Aquí nos ocupamos exclusivamente de columnas nuevas.
    """
    try:
        tablas = {
            r[0]
            for r in db.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            ).fetchall()
        }

        # --- productos -----------------------------------------------
        if "productos" in tablas:
            # Costo unitario de compra (base para el autocalculo de precio de
            # venta = costo + (costo * margen / 100)) del formulario de producto.
            _agregar_columna(db, "productos", "costo", "NUMERIC DEFAULT 0")
            # Porcentaje de ganancia objetivo (referencia para auto-cálculo).
            _agregar_columna(
                db, "productos", "porcentaje_ganancia", "NUMERIC DEFAULT 0"
            )
            # --- Upgrade v2: multi-rubro y vencimientos ---
            _agregar_columna(db, "productos", "marca", "VARCHAR(80)")
            _agregar_columna(db, "productos", "talle", "VARCHAR(40)")
            _agregar_columna(db, "productos", "color", "VARCHAR(40)")
            _agregar_columna(db, "productos", "fecha_vencimiento", "DATETIME")
            # --- Upgrade v3: variantes de impresión (librería/servicio) ---
            _agregar_columna(db, "productos", "tipo_papel", "VARCHAR(40)")
            _agregar_columna(db, "productos", "color_bn", "VARCHAR(20)")

        # --- clientes (columnas de respaldo si la tabla se creó antigua) ---
        if "clientes" in tablas:
            _agregar_columna(db, "clientes", "telefono", "VARCHAR(60)")
            _agregar_columna(db, "clientes", "activo", "BOOLEAN DEFAULT 1")

        # --- ventas: estado de anulacion + auditoria (upgrade v2) ---
        if "ventas" in tablas:
            _agregar_columna(db, "ventas", "estado", "VARCHAR(20) DEFAULT 'activa'")
            _agregar_columna(db, "ventas", "anulada_en", "DATETIME")
            _agregar_columna(db, "ventas", "anulada_por", "VARCHAR(255)")

        # --- usuarios: rubro multi-rubro (upgrade v2) ---
        if "usuarios" in tablas:
            _agregar_columna(db, "usuarios", "rubro", "VARCHAR(40) DEFAULT 'general'")

        db.commit()
        logger.info("[migracion] Verificación/ajuste ligero de esquema completado.")
    except Exception as exc:  # pragma: no cover
        db.rollback()
        logger.warning("[migracion] No se pudo completar el ajuste ligero: %s", exc)
