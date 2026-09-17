"""Configurador de instalación: asigna el `cliente_id` real a una instalación.

USO (al instalar el POS en la PC de un cliente):
    python configurar_cliente.py <cliente_id>

    Ejemplo:
        python configurar_cliente.py libreria-pedro

POR QUÉ:
  De fábrica, toda instalación arranca con `cliente_id = "demo"`. Ese valor
  alimenta el cálculo de la HUELLA de máquina (ver `app/services/licencia_firma`).
  Si dos instalaciones comparten "demo", sus huellas podrían coincidir y una
  licencia podría usarse en el equipo equivocado.

  Al fijar un `cliente_id` ÚNICO por comercio (p.ej. "libreria-pedro"), cada
  instalación obtiene una huella distinta y las licencias quedan atadas a su
  equipo correcto.

RECOMENDACIÓN: usá un identificador estable y sin espacios (minúsculas, guiones).
El MISMO `cliente_id` debe registrarse en la planilla del proveedor para saber,
cuando el cliente mande su huella, a quién pertenece.

SEGURIDAD:
  Este script NO maneja llaves ni firmas. Solo escribe el `cliente_id` en la
  base local. Es seguro dejarlo en la instalación del cliente.
"""

from __future__ import annotations

import re
import sys

from app.database import SessionLocal
from app.models import Licencia, now_utc
from app.services.licencia_firma import calcular_huella

# Caracteres permitidos: minúsculas, dígitos y guion. Se normaliza a ASCII.
_PATRON_VALIDO = re.compile(r"^[a-z0-9][a-z0-9-]{1,118}[a-z0-9]$")


def _normalizar(crudo: str) -> str:
    """Convierte el texto a un `cliente_id` válido (minúsculas, sin espacios)."""
    limpio = crudo.strip().lower()
    limpio = re.sub(r"\s+", "-", limpio)  # espacios -> guion
    limpio = re.sub(r"[^a-z0-9-]", "", limpio)  # quitar símbolos raros
    limpio = re.sub(r"-{2,}", "-", limpio)  # colapsar guiones
    return limpio.strip("-")


def _obtener_o_crear_licencia(db) -> Licencia:
    """Devuelve la licencia singleton, creándola si no existe."""
    lic = db.query(Licencia).first()
    if lic is None:
        lic = Licencia(id=1, cliente_id="demo")
        db.add(lic)
        db.commit()
        db.refresh(lic)
    return lic


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python configurar_cliente.py <cliente_id>")
        print("Ejemplo: python configurar_cliente.py libreria-pedro")
        return 1

    cliente_id = _normalizar(sys.argv[1])
    if not _PATRON_VALIDO.match(cliente_id):
        print(
            "ERROR: el cliente_id debe tener entre 3 y 120 caracteres, "
            "solo minúsculas, dígitos y guiones (sin empezar/terminar en guion)."
        )
        return 1

    db = SessionLocal()
    try:
        lic = _obtener_o_crear_licencia(db)
        anterior = lic.cliente_id
        lic.cliente_id = cliente_id
        lic.actualizado_en = now_utc()
        db.commit()
        db.refresh(lic)

        huella = calcular_huella(lic.cliente_id)

        print("=" * 64)
        print("  INSTALACIÓN CONFIGURADA")
        print("=" * 64)
        print(f"  Cliente ID anterior : {anterior}")
        print(f"  Cliente ID nuevo    : {lic.cliente_id}")
        print(f"  Huella de esta PC    : {huella}")
        print("=" * 64)
        print("  PRÓXIMOS PASOS:")
        print("   1. Anotá el Cliente ID en tu planilla del proveedor.")
        print("   2. Iniciá el POS; en la pantalla de licencia aparecerá la")
        print("      huella. El cliente te la envía y vos devolvés un código.")
        print("=" * 64)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
