"""Módulo 1/2/5/6 — Migraciones aditivas para bases SQLite existentes.

El `create_all` de SQLAlchemy crea TABLAS nuevas pero NO agrega COLUMNAS a
tablas ya creadas. Para no destruir datos en instalaciones en produccion, se
extiende `run_light_migrations` con las columnas nuevas del upgrade v2:

  productos : talle, color, fecha_vencimiento
  ventas    : estado, anulada_en, anulada_por
  usuarios  : rubro
  licencia  : (tabla nueva -> la crea create_all; aqui solo backfill de fila)
"""
from tools_upgrade.patcher import apply

MIG = "app/migrations.py"

# 1) Nuevas columnas de productos (dentro del bloque `if "productos" in tablas`).
apply(
    MIG,
    (
        "            _agregar_columna(\n"
        '                db, "productos", "porcentaje_ganancia", "NUMERIC DEFAULT 0"\n'
        "            )",
        "            _agregar_columna(\n"
        '                db, "productos", "porcentaje_ganancia", "NUMERIC DEFAULT 0"\n'
        "            )\n"
        "            # --- Upgrade v2: multi-rubro y vencimientos ---\n"
        '            _agregar_columna(db, "productos", "talle", "VARCHAR(40)")\n'
        '            _agregar_columna(db, "productos", "color", "VARCHAR(40)")\n'
        '            _agregar_columna(db, "productos", "fecha_vencimiento", "DATETIME")',
    ),
)

# 2) Nuevas columnas de ventas (estado de anulacion) + rubro en usuarios.
apply(
    MIG,
    (
        '        # --- clientes (columnas de respaldo si la tabla se creó antigua) ---\n'
        '        if "clientes" in tablas:\n'
        '            _agregar_columna(db, "clientes", "telefono", "VARCHAR(60)")\n'
        '            _agregar_columna(db, "clientes", "activo", "BOOLEAN DEFAULT 1")',
        '        # --- clientes (columnas de respaldo si la tabla se creó antigua) ---\n'
        '        if "clientes" in tablas:\n'
        '            _agregar_columna(db, "clientes", "telefono", "VARCHAR(60)")\n'
        '            _agregar_columna(db, "clientes", "activo", "BOOLEAN DEFAULT 1")\n'
        "\n"
        "        # --- ventas: estado de anulacion + auditoria (upgrade v2) ---\n"
        '        if "ventas" in tablas:\n'
        "            _agregar_columna(\n"
        '                db, "ventas", "estado", "VARCHAR(20) DEFAULT \'activa\'"\n'
        "            )\n"
        '            _agregar_columna(db, "ventas", "anulada_en", "DATETIME")\n'
        '            _agregar_columna(db, "ventas", "anulada_por", "VARCHAR(255)")\n'
        "\n"
        "        # --- usuarios: rubro multi-rubro (upgrade v2) ---\n"
        '        if "usuarios" in tablas:\n'
        "            _agregar_columna(\n"
        '                db, "usuarios", "rubro", "VARCHAR(40) DEFAULT \'general\'"\n'
        "            )",
    ),
)

print("[migrations] OK")
