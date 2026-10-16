"""Generador de códigos de RECUPERACIÓN de contraseña (herramienta PRIVADA).

USO (en TU máquina, cuando un cliente olvidó la contraseña de su administrador):
    python tools_licencia/generar_recuperacion.py

Flujo:
  1. El cliente abre la pantalla "¿Olvidaste tu contraseña?" del login: ahí ve la
     HUELLA de su PC y te la manda por WhatsApp junto con su correo.
  2. Pegás la huella (y el correo si querés atar el código a esa cuenta).
  3. El script FIRMA un código `VXR...` que sirve SOLO para esa PC, hasta la
     fecha de vencimiento y UNA vez (la serie es la hora de emisión: el programa
     rechaza un código más viejo que el último aplicado).
  4. El cliente lo pega en esa pantalla y elige una contraseña nueva.

SEGURIDAD:
  - Usa TU LLAVE PRIVADA (tools_licencia/vortex_private.key). NO lo distribuyas.
  - Verificá por otro medio que quien lo pide es el dueño del comercio.
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.licencia_firma import firmar_recuperacion  # noqa: E402

DIR = Path(__file__).resolve().parent
RUTA_PRIVADA = DIR / "vortex_private.key"
DIAS_VALIDEZ = 3


def _leer_texto(prompt: str, obligatorio: bool = True) -> str:
    while True:
        valor = input(prompt).strip()
        if valor or not obligatorio:
            return valor
        print("  ! Este dato es obligatorio.")


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
    print("  GENERADOR DE CÓDIGOS DE RECUPERACIÓN VORTEX  (uso interno)")
    print("=" * 64)

    huella = _leer_texto("  Huella de la PC del cliente (ej: POS-A8F2...-LIBRERIA-PEDRO): ")
    email = _leer_texto(
        "  Correo del administrador (Enter = cualquier administrador): ",
        obligatorio=False,
    )
    vence = date.today() + timedelta(days=DIAS_VALIDEZ)
    serie = int(time.time())

    codigo = firmar_recuperacion(
        private_key=private_key,
        huella=huella.upper(),
        serie=serie,
        vence=vence,
        email=email or None,
    )

    print("\n" + "=" * 64)
    print("  CÓDIGO DE RECUPERACIÓN GENERADO")
    print("=" * 64)
    print(f"  Huella  : {huella.upper()}")
    print(f"  Cuenta  : {email or '(cualquier administrador)'}")
    print(f"  Vence   : {vence.isoformat()} ({DIAS_VALIDEZ} días) - un solo uso")
    print(f"  Emitido : {datetime.now().isoformat(timespec='seconds')}")
    print()
    print("  --- CÓDIGO (enviar al cliente) ---")
    print(codigo)
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
