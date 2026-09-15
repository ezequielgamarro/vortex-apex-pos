"""Módulo 1/2 — Schemas de Producto: campos multi-rubro y vencimiento.

Se agregan de forma opcional (nullable) para no romper el contrato actual ni
el POS (que ignora los campos que no usa).
"""
from tools_upgrade.patcher import apply

CRE = "app/schemas/producto.py"

# ProductoBase: +talle, +color, +fecha_vencimiento.
apply(
    CRE,
    (
        '    categoria: Optional[str] = Field(\n'
        '        None, max_length=100, description="Categoría del producto"\n'
        "    )\n"
        '    tipo_unidad: str = Field(',
        '    categoria: Optional[str] = Field(\n'
        '        None, max_length=100, description="Categoría del producto"\n'
        "    )\n"
        "    # Campos multi-rubro (opcionales; el POS los ignora si no aplican).\n"
        "    talle: Optional[str] = Field(\n"
        '        None, max_length=40, description="Talle (indumentaria)"\n'
        "    )\n"
        "    color: Optional[str] = Field(\n"
        '        None, max_length=40, description="Color (indumentaria)"\n'
        "    )\n"
        "    fecha_vencimiento: Optional[datetime] = Field(\n"
        '        None, description="Fecha de vencimiento (perecibles)"\n'
        "    )\n"
        '    tipo_unidad: str = Field(',
    ),
)

# ProductoUpdate: +los mismos campos opcionales.
apply(
    CRE,
    (
        '    categoria: Optional[str] = Field(None, max_length=100)\n'
        '    tipo_unidad: Optional[str] = Field(',
        '    categoria: Optional[str] = Field(None, max_length=100)\n'
        "    talle: Optional[str] = Field(None, max_length=40)\n"
        "    color: Optional[str] = Field(None, max_length=40)\n"
        "    fecha_vencimiento: Optional[datetime] = Field(None)\n"
        '    tipo_unidad: Optional[str] = Field(',
    ),
)

print("[schemas producto] OK")
