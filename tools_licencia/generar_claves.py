"""Generador del par de llaves Ed25519 para licencias Vortex.

USO (una sola vez, en TU máquina como proveedor):
    python tools_licencia/generar_claves.py

Genera:
  - tools_licencia/vortex_private.key  -> TU LLAVE PRIVADA. NUNCA la compartas
                                          ni la subas a internet. Si se filtra,
                                          cualquiera puede emitir licencias.
  - tools_licencia/vortex_public.key   -> LLAVE PÚBLICA. Esta SÍ se puede
                                          distribuir: va embebida en el POS.

SEGURIDAD:
  - No sobrescribe llaves existentes sin confirmación explícita.
  - La carpeta tools_licencia/ NO se empaqueta en el .exe (queda fuera de app/).
"""

from __future__ import annotations

import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Permite importar el paquete `app` al correr el script desde la raíz.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DIR = Path(__file__).resolve().parent
RUTA_PRIVADA = DIR / "vortex_private.key"
RUTA_PUBLICA = DIR / "vortex_public.key"


def _confirmar_sobrescritura() -> bool:
    """Pide confirmación si ya existen llaves (evita perder la privada)."""
    if RUTA_PRIVADA.exists() or RUTA_PUBLICA.exists():
        print("ADVERTENCIA: ya existen llaves en tools_licencia/.")
        print("Si las sobrescribís, las licencias emitidas ANTES dejan de ser")
        print("verificables con la llave pública nueva.")
        resp = input("¿Sobrescribir de todos modos? (escribe 'SI' para continuar): ")
        return resp.strip() == "SI"
    return True


def main() -> None:
    if not _confirmar_sobrescritura():
        print("Cancelado. No se generaron llaves nuevas.")
        return

    # 1) Generar el par Ed25519.
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # 2) Serializar.
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # 3) Escribir a disco.
    RUTA_PRIVADA.write_bytes(priv_pem)
    RUTA_PUBLICA.write_bytes(pub_pem)

    print("\n" + "=" * 64)
    print("  LLAVES GENERADAS CORRECTAMENTE")
    print("=" * 64)
    print(f"  Privada (SECRETA): {RUTA_PRIVADA}")
    print(f"  Pública (POS)    : {RUTA_PUBLICA}")
    print()
    print("  --- LLAVE PÚBLICA (esta debe ir embebida en el POS) ---")
    print(pub_pem.decode("ascii"))
    print("=" * 64)
    print("  RECORDATORIOS:")
    print("   - Hacé BACKUP de vortex_private.key en un lugar seguro.")
    print("   - NUNCA subas la privada a internet ni la compartas.")
    print("   - Copiá el contenido de vortex_public.key al POS (Etapa 2).")
    print("=" * 64)


if __name__ == "__main__":
    main()
