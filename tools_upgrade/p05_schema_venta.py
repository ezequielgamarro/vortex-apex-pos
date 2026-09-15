"""Módulo 3 — Schemas de Venta: estado de anulacion.

  * VentaOut: +estado.
  * Nuevo esquema AnulacionOut para la respuesta del endpoint de anulacion.
"""
from tools_upgrade.patcher import apply

SCH = "app/schemas/venta.py"

# VentaOut: agregar el campo estado.
apply(
    SCH,
    (
        "class VentaOut(BaseModel):\n"
        '    """Esquema de respuesta de una venta registrada."""\n'
        "\n"
        "    id: UUID\n"
        "    folio: str\n"
        "    fecha: datetime\n"
        "    total: Decimal\n"
        "    metodo_pago: str\n"
        "    cliente: str\n"
        "    creado_en: datetime\n",
        "class VentaOut(BaseModel):\n"
        '    """Esquema de respuesta de una venta registrada."""\n'
        "\n"
        "    id: UUID\n"
        "    folio: str\n"
        "    fecha: datetime\n"
        "    total: Decimal\n"
        "    metodo_pago: str\n"
        "    cliente: str\n"
        '    estado: str = "activa"\n'
        "    anulada_en: Optional[datetime] = None\n"
        "    anulada_por: Optional[str] = None\n"
        "    creado_en: datetime\n",
    ),
)

# Nuevo esquema de respuesta de anulacion (al final del archivo).
SCH_FIN = (
    "class VentaHistorialOut(VentaOut):\n"
    '    """Cabecera de venta con sus ítems enriquecidos para el reporte por fechas."""\n'
    "\n"
    "    items: List[VentaItemHistorialOut] = Field(default_factory=list)\n"
    "\n"
    "    model_config = ConfigDict(from_attributes=True)"
)
apply(
    SCH,
    (
        SCH_FIN,
        SCH_FIN
        + "\n"
        "\n"
        "\n"
        "class AnulacionOut(BaseModel):\n"
        '    """Respuesta de la anulación de una venta.\n'
        "\n"
        "    Incluye los folios y montos afectados (venta y, si aplica, el abono\n"
        "    revertido de la cuenta corriente) para trazabilidad del cajero.\n"
        '    """\n'
        "\n"
        "    venta_id: UUID\n"
        "    folio: str\n"
        "    estado: str\n"
        "    total_revertido: Decimal\n"
        "    stock_devuelto: int\n"
        "    saldo_cc_ajustado: Optional[Decimal] = None\n"
        "    mensaje: str",
    ),
)

print("[schemas venta] OK")
