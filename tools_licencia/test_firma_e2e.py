"""Prueba de extremo a extremo del sistema de firma de licencias.

Verifica el ciclo completo y los casos de TRAMPA:

  ✅ Caso feliz: licencia emitida por el proveedor se acepta en la máquina
     correcta.
  ❌ Código manipulado: si se altera el payload, la firma falla.
  ❌ Otra máquina: una licencia válida NO vale en un equipo distinto.
  ❌ Emisor falso: un atacante con OTRA llave privada no puede firmar.
  ❌ Código corrupto: texto basura no rompe el verificador (devuelve inválido).

USO:
    python tools_licencia/test_firma_e2e.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.licencia_firma import (  # noqa: E402
    calcular_huella,
    calcular_hash_huella,
    firmar_licencia,
    verificar_licencia,
    _b64url_encodear,
)

# --- Claves de prueba (NO son las reales; se generan al vuelo) ---
PROVEEDOR = Ed25519PrivateKey.generate()
PROVEEDOR_PUB = PROVEEDOR.public_key()
ATACANTE = Ed25519PrivateKey.generate()
ATACANTE_PUB = ATACANTE.public_key()

CLIENTE_ID = "DEMO"
HUELLA_MAQUINA_A = calcular_huella(CLIENTE_ID)
HUELLA_MAQUINA_B = "POS-DEADBEEF-OTRO"  # simulada (equipo distinto)

VENCE = date.today() + timedelta(days=30)


def _check(cond: bool, desc: str, extra: str = "") -> bool:
    marca = "OK  " if cond else "FALLO"
    print(f"  [{marca}] {desc}" + (f"  -> {extra}" if extra else ""))
    return cond


def main() -> int:
    print("\n" + "=" * 64)
    print("  TEST E2E — FIRMA Y VERIFICACIÓN DE LICENCIAS (Ed25519)")
    print("=" * 64)
    print(f"  Huella de ESTA máquina: {HUELLA_MAQUINA_A}\n")

    resultados: list[bool] = []

    # --- 1) CASO FELIZ ---
    codigo = firmar_licencia(PROVEEDOR, CLIENTE_ID, HUELLA_MAQUINA_A, VENCE, 7)
    r = verificar_licencia(PROVEEDOR_PUB, codigo, HUELLA_MAQUINA_A)
    resultados.append(
        _check(
            r.valido
            and r.fecha_vencimiento == VENCE
            and r.dias_gracia == 7
            and r.huella == calcular_hash_huella(CLIENTE_ID),
            "Caso feliz: licencia legítima se acepta en su máquina",
            r.motivo,
        )
    )
    # Verificación de longitud (usabilidad WhatsApp): objetivo razonable.
    # Piso matemático: firma Ed25519 = 64 bytes fijos -> ~130-150 chars.
    print(f"       Longitud del código: {len(codigo)} caracteres")
    resultados.append(
        _check(
            len(codigo) <= 150,
            "Compacto: el código entra cómodo en un mensaje de WhatsApp",
            f"{len(codigo)} chars",
        )
    )

    # --- 2) CÓDIGO MANIPULADO (cambio la fecha a 10 años) ---
    vence_lejano = (date.today() + timedelta(days=3650)).strftime("%Y%m%d")
    payload_alterado = f'{{"g":7,"h":"{calcular_hash_huella(CLIENTE_ID)}","v":"{vence_lejano}"}}'.encode()
    codigo_alterado = f"VX1.{_b64url_encodear(payload_alterado)}.{codigo.split('.')[2]}"
    r = verificar_licencia(PROVEEDOR_PUB, codigo_alterado, HUELLA_MAQUINA_A)
    resultados.append(
        _check(
            not r.valido,
            "Anti-trampa: cambiar la fecha invalida la firma",
            r.motivo,
        )
    )

    # --- 3) OTRA MÁQUINA ---
    r = verificar_licencia(PROVEEDOR_PUB, codigo, HUELLA_MAQUINA_B)
    resultados.append(
        _check(
            not r.valido,
            "Anti-trampa: la licencia NO vale en otra máquina",
            r.motivo,
        )
    )

    # --- 4) EMISOR FALSO (un atacante intenta firmar) ---
    codigo_falso = firmar_licencia(ATACANTE, CLIENTE_ID, HUELLA_MAQUINA_A, VENCE, 7)
    r = verificar_licencia(PROVEEDOR_PUB, codigo_falso, HUELLA_MAQUINA_A)
    resultados.append(
        _check(
            not r.valido,
            "Anti-trampa: firma de un emisor no autorizado se rechaza",
            r.motivo,
        )
    )
    # Pero su propia llave pública SÍ lo vería válido (prueba de que es la clave):
    r2 = verificar_licencia(ATACANTE_PUB, codigo_falso, HUELLA_MAQUINA_A)
    resultados.append(
        _check(
            r2.valido,
            "Control: el mismo código SÍ es válido con la clave del atacante",
        )
    )

    # --- 5) CÓDIGOS CORRUPTOS ---
    for basura in ["", "hola", "VX1.XXX", "VX2.aaaa.bbbb", "VX1.@@@.@@@"]:
        r = verificar_licencia(PROVEEDOR_PUB, basura, HUELLA_MAQUINA_A)
        resultados.append(
            _check(
                not r.valido,
                f"Robustez: entrada inválida rechazada ({basura!r})",
                r.motivo,
            )
        )

    total = len(resultados)
    ok = sum(1 for x in resultados if x)
    print("\n" + "=" * 64)
    print(f"  RESULTADO: {ok}/{total} pruebas OK")
    print("=" * 64 + "\n")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
