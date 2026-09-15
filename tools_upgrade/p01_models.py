"""Módulo 1/2/5/6 — Cimientos de esquema: modelos ORM.

Cambios:
  * Producto: +talle, +color, +fecha_vencimiento (multi-rubro y vencimientos).
  * Venta: +estado, +anulada_en, +anulada_por (anulación segura).
  * Usuario: +rubro (superadmin multi-rubro).
"""
from tools_upgrade.patcher import apply

MODELOS = "app/models/__init__.py"

# --- Producto: columnas multi-rubro (talle/color) y vencimiento ---
apply(
    MODELOS,
    (
        '    tipo_unidad = Column(String(15), nullable=False, default="unidad")\n'
        "    activo = Column(Boolean, nullable=False, default=True)",
        '    tipo_unidad = Column(String(15), nullable=False, default="unidad")\n'
        "    # --- Campos multi-rubro (indumentaria / libreria) ---\n"
        "    # `talle` y `color`: propios del rubro 'indumentaria'. Nullable porque\n"
        "    # los demas rubros no los usan (sin sobreingenieria tipo tabla EAV).\n"
        "    talle = Column(String(40), nullable=True)\n"
        "    color = Column(String(40), nullable=True)\n"
        "    # `fecha_vencimiento`: control de perecibles (panaderia/alimentos).\n"
        "    # Nullable: solo aplica a rubros con vencimiento.\n"
        "    fecha_vencimiento = Column(DateTime, nullable=True)\n"
        "    activo = Column(Boolean, nullable=False, default=True)",
    ),
)

# --- Venta: estado de anulacion + auditoria ---
apply(
    MODELOS,
    (
        '    cliente = Column(String(200), nullable=False, default="Mostrador")\n'
        "    creado_en = Column(DateTime, nullable=False, default=now_utc)",
        '    cliente = Column(String(200), nullable=False, default="Mostrador")\n'
        "    # Estado del ticket: 'activa' (default) | 'anulada'. Una venta anulada\n"
        "    # se EXCLUYE de los totales de caja/reportes y su stock ya fue devuelto.\n"
        '    estado = Column(String(20), nullable=False, default="activa")\n'
        "    # Auditoria de la anulacion (trazabilidad: quien y cuando).\n"
        "    anulada_en = Column(DateTime, nullable=True)\n"
        "    anulada_por = Column(String(255), nullable=True)\n"
        "    creado_en = Column(DateTime, nullable=False, default=now_utc)",
    ),
)

# --- Usuario: rubro multi-rubro ---
apply(
    MODELOS,
    (
        '    rol = Column(String(20), nullable=False, default="cajero")  # admin | cajero',
        '    rol = Column(String(20), nullable=False, default="cajero")  # admin | cajero\n'
        "    # Rubro del negocio (arquitectura multi-rubro). Determina que campos y\n"
        "    # controles muestra la UI de inventario/POS para este usuario.\n"
        "    # 'general' | 'panaderia_alimentos' | 'indumentaria' | 'ferreteria'\n"
        "    # | 'libreria'. Los usuarios creados por un admin HEREDAN su rubro.\n"
        '    rubro = Column(String(40), nullable=False, default="general")',
    ),
)

print("[models] OK")
