"""Módulo 6 — Modelo de Licencia SaaS (bloqueo remoto por falta de pago).

Decisión de arquitectura:
  Se modela como tabla con SINGLE ROW (patrón Settings/Singleton Row de
  Fowler, ya usado en `ConfiguracionNegocio`) mediante `cliente_id` único.
  La licencia vive en la MISMA SQLite local para que el bloqueo sea offline-first:
  si no hay internet, el sistema sigue validando contra la última fecha conocida.

  Modelo de amenaza (honestidad de ingeniería): al ser una app 100% local, el
  bloqueo es una barrera COMERCIAL, no de seguridad fuerte. Un usuario con
  acceso físico al disco puede editar la BD o el reloj. Las mitigaciones
  (fecha desde API externa + ultimo_ping) elevan el costo de trampa, no la
  imposibilitan. Esto se documenta explícitamente para no sobrevender.
"""
from __future__ import annotations

from tools_upgrade.patcher import apply

MODELOS = "app/models/__init__.py"

# Insertar el modelo Licencia antes de la seccion de categorias.
apply(
    MODELOS,
    (
        "# ============================ CATEGORÍAS ==================================",
        "# ============================== LICENCIA ==================================\n"
        "# SaaS single-row: la instalacion local tiene exactamente una licencia.\n"
        "# `cliente_id` identifica la instalacion ante el SuperAdmin (planilla CSV).\n"
        "\n"
        "\n"
        "class Licencia(Base):\n"
        '    """Licencia de uso de la instalacion (fila unica)."""\n'
        "\n"
        '    __tablename__ = "licencia"\n'
        "\n"
        "    id = Column(Integer, primary_key=True, default=1)  # singleton\n"
        '    cliente_id = Column(String(120), unique=True, nullable=False, default="demo")\n'
        "    # Fecha hasta la cual la licencia es valida (inclusive).\n"
        "    fecha_vencimiento = Column(DateTime, nullable=True)\n"
        "    # Dias de gracia tras el vencimiento antes de bloquear.\n"
        "    dias_gracia = Column(Integer, nullable=False, default=3)\n"
        "    # Ultima fecha conocida (fuente externa o local) al hacer ping.\n"
        "    # Anti-trampas: si no hay internet, se avanza el tiempo desde aqui.\n"
        "    ultimo_ping = Column(DateTime, nullable=True)\n"
        "    estado = Column(String(20), nullable=False, default=\"activa\")  # activa|suspendida\n"
        "    actualizado_en = Column(DateTime, nullable=True)\n"
        "\n"
        "    def __repr__(self) -> str:\n"
        '        return f"<Licencia {self.cliente_id} vence={self.fecha_vencimiento}>"\n'
        "\n"
        "\n"
        "# ============================ CATEGORÍAS ==================================",
    ),
)

# Exportar Licencia en __all__.
apply(
    MODELOS,
    (
        '    "MovimientoCuenta",\n'
        '    "ConfiguracionNegocio",\n'
        "]",
        '    "MovimientoCuenta",\n'
        '    "ConfiguracionNegocio",\n'
        '    "Licencia",\n'
        "]",
    ),
)

print("[models licencia] OK")
