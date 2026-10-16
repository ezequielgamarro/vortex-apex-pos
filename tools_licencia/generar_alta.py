"""Generador de códigos de ALTA (herramienta PRIVADA del proveedor).

USO (en TU máquina, al dar de alta a un cliente nuevo):
    python tools_licencia/generar_alta.py

Flujo:
  1. En la PC del cliente, el programa arranca vacío y muestra el asistente de
     "Configuración inicial" con la HUELLA de esa PC.
  2. El cliente te pasa la huella (presencial: la leés vos; remoto: por WhatsApp).
  3. Pegás la huella y elegís el rubro del comercio.
  4. El script FIRMA un código `VXA....` que autoriza crear el primer
     administrador en ESA PC. Lo pegás (o el cliente lo pega) en el asistente.

Este código solo sirve para la huella indicada y solo mientras la instalación no
tenga usuarios. NO da la licencia: la licencia mensual se emite aparte con
generar_licencia.py.

SEGURIDAD:
  - Usa TU LLAVE PRIVADA (tools_licencia/vortex_private.key). NO lo distribuyas.
  - NUNCA copies este archivo ni la llave a la PC de un cliente.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.licencia_firma import firmar_alta  # noqa: E402

DIR = Path(__file__).resolve().parent
RUTA_PRIVADA = DIR / "vortex_private.key"

# Debe coincidir con RUBROS_VALIDOS de app/routers/auth.py.
RUBROS = (
    "general",
    "panaderia_alimentos",
    "indumentaria",
    "ferreteria",
    "libreria",
)


def _leer_texto(prompt: str) -> str:
    while True:
        valor = input(prompt).strip()
        if valor:
            return valor
        print("  ! Este dato es obligatorio.")


def _leer_rubro() -> str:
    print("  Rubros: " + ", ".join(f"{i}) {r}" for i, r in enumerate(RUBROS, 1)))
    while True:
        crudo = input("  Rubro (número o nombre) [1]: ").strip().lower()
        if not crudo:
            return RUBROS[0]
        if crudo.isdigit() and 1 <= int(crudo) <= len(RUBROS):
            return RUBROS[int(crudo) - 1]
        if crudo in RUBROS:
            return crudo
        print("  ! Rubro inválido.")


def _leer_cliente_id() -> str | None:
    """Identificador del comercio (opcional). Útil en instalaciones REMOTAS."""
    import re

    patron = re.compile(r"^[a-z0-9][a-z0-9-]{1,118}[a-z0-9]$")
    while True:
        crudo = input(
            "  Cliente ID (ej: libreria-pedro; Enter = no fijarlo ahora): "
        ).strip().lower()
        if not crudo:
            return None
        crudo = re.sub(r"[^a-z0-9-]", "", re.sub(r"\s+", "-", crudo)).strip("-")
        if patron.match(crudo):
            return crudo
        print("  ! Solo minúsculas, dígitos y guiones (3 a 120 caracteres).")


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
    print("  GENERADOR DE CÓDIGOS DE ALTA VORTEX  (uso interno)")
    print("=" * 64)

    huella = _leer_texto("  Huella de la PC del cliente (ej: POS-A8F299B1-DEMO): ")
    rubro = _leer_rubro()
    cliente_id = _leer_cliente_id()

    codigo = firmar_alta(
        private_key=private_key,
        huella=huella.upper(),
        rubro=rubro,
        cliente_id=cliente_id,
    )

    print("\n" + "=" * 64)
    print("  CÓDIGO DE ALTA GENERADO")
    print("=" * 64)
    print(f"  Huella  : {huella.upper()}")
    print(f"  Rubro   : {rubro}")
    print(f"  Cliente : {cliente_id or '(no fijado)'}")
    print(f"  Emitido : {datetime.now().isoformat(timespec='seconds')}")
    if cliente_id:
        print()
        print("  OJO: al fijar el Cliente ID la HUELLA de esa PC CAMBIA. Después del")
        print("  alta, pedile al cliente la huella nueva (pantalla de licencia) y")
        print("  generá la licencia con generar_licencia.py usando ESA huella.")
    print()
    print("  --- CÓDIGO DE ALTA (pegar en el asistente de la PC del cliente) ---")
    print(codigo)
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
