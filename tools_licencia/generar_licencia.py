"""Generador de licencias firmadas (herramienta PRIVADA del proveedor).

USO (en TU máquina, cada vez que un cliente te pide activar/renovar):
    python tools_licencia/generar_licencia.py

Flujo:
  1. El cliente te pasa su HUELLA (la ve en su POS) y su CLIENTE ID.
  2. Pegás la huella, la fecha de vencimiento y los días de gracia.
  3. El script FIRMA y te muestra el CÓDIGO para enviar por WhatsApp.

Solo funciona si existe tools_licencia/vortex_private.key (generala antes
con generar_claves.py).

SEGURIDAD:
  - Este script usa TU LLAVE PRIVADA. NO lo distribuyas.
  - NUNCA copies este archivo a la PC de un cliente.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.licencia_firma import firmar_licencia  # noqa: E402

DIR = Path(__file__).resolve().parent
RUTA_PRIVADA = DIR / "vortex_private.key"


def _leer_texto(prompt: str, obligatorio: bool = True) -> str:
    """Pide un texto y valida que no esté vacío si es obligatorio."""
    while True:
        valor = input(prompt).strip()
        if valor or not obligatorio:
            return valor
        print("  ! Este dato es obligatorio.")


def _leer_fecha(prompt: str, por_defecto: date) -> date:
    """Pide una fecha AAAA-MM-DD; acepta Enter para usar la sugerida."""
    while True:
        crudo = input(f"{prompt} [{por_defecto.isoformat()}]: ").strip()
        if not crudo:
            return por_defecto
        try:
            return date.fromisoformat(crudo)
        except ValueError:
            print("  ! Formato inválido. Usá AAAA-MM-DD (ej: 2026-11-15).")


def main() -> None:
    if not RUTA_PRIVADA.exists():
        print("ERROR: no se encontró la llave privada en:")
        print(f"  {RUTA_PRIVADA}")
        print("Generala primero con: python tools_licencia/generar_claves.py")
        return

    private_key = serialization.load_pem_private_key(
        RUTA_PRIVADA.read_bytes(), password=None
    )

    print("\n" + "=" * 64)
    print("  GENERADOR DE LICENCIAS VORTEX  (uso interno)")
    print("=" * 64)
    print("  Tip: para probar, dejá todo y se usará una demo por 30 días.\n")

    # 1) Datos del cliente.
    huella = _leer_texto("  Huella del cliente (ej: POS-A8F299B1-DEMO): ")
    # El cliente_id se deduce de la huella (última parte) salvo que se indique.
    cliente_id = huella.split("-")[-1] if "-" in huella else huella
    cid_manual = _leer_texto(
        f"  Cliente ID [{cliente_id}]: ", obligatorio=False
    )
    if cid_manual:
        cliente_id = cid_manual

    # 2) Vigencia.
    sugerida = date.today() + timedelta(days=30)
    vence = _leer_fecha("  Vence el (AAAA-MM-DD)", sugerida)

    # 3) Gracia.
    crudo_gracia = input("  Días de gracia [7]: ").strip()
    try:
        gracia = int(crudo_gracia) if crudo_gracia else 7
    except ValueError:
        gracia = 7

    # 4) Firmar.
    codigo = firmar_licencia(
        private_key=private_key,
        cliente_id=cliente_id,
        huella=huella.upper(),
        fecha_vencimiento=vence,
        dias_gracia=gracia,
    )

    # 5) Mostrar el resultado para copiar y enviar.
    print("\n" + "=" * 64)
    print("  ✅ LICENCIA GENERADA")
    print("=" * 64)
    print(f"  Cliente ID : {cliente_id}")
    print(f"  Huella     : {huella.upper()}")
    print(f"  Vence      : {vence.isoformat()} (+{gracia} días de gracia)")
    print(f"  Emitida    : {datetime.now().isoformat(timespec='seconds')}")
    print()
    print("  --- CÓDIGO DE ACTIVACIÓN (enviar al cliente) ---")
    print(codigo)
    print("=" * 64)
    print("  Copiá el código y mandáselo al cliente por WhatsApp.")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
