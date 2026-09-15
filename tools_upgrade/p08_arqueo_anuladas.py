"""Módulo 3 — Excluir ventas anuladas de los totales de caja/reportes.

La anulación es un soft-delete: la venta permanece en la BD con estado
'anulada'. Todos los cálculos de dinero (arqueo) deben filtrarlas.
"""
from tools_upgrade.patcher import apply

A = "app/routers/arqueo.py"

# Ancla en _calcular_totales: agregar el filtro de estado tras la apertura.
apply(
    A,
    (
        "    # Filtro inicial del turno (desde su apertura).\n"
        "    condiciones_ventas = [Venta.fecha >= caja.fecha_apertura]",
        "    # Filtro inicial del turno (desde su apertura) EXCLUYENDO anuladas:\n"
        "    # las ventas anuladas son soft-delete y no representan dinero real.\n"
        "    condiciones_ventas = [\n"
        "        Venta.fecha >= caja.fecha_apertura,\n"
        '        Venta.estado != "anulada",\n'
        "    ]",
    ),
)
print("[arqueo excluir anuladas] OK")
