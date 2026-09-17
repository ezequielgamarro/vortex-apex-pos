"""Servicio de firma y verificación de licencias (modelo "código firmado").

ARQUITECTURA (patrón desafío-respuesta / challenge-response):
  - El POS del cliente calcula una HUELLA de su máquina.
  - El proveedor (Vortex) FIRMA una licencia con su LLAVE PRIVADA (Ed25519).
  - El POS VERIFICA la licencia con la LLAVE PÚBLICA (embebida en el programa).

POR QUÉ FIRMA Y NO ENCRIPTACIÓN:
  Encriptar exige que el cliente tenga la clave para desencriptar; si la tiene,
  puede generar licencias. FIRMAR no: la llave privada NUNCA sale del lado del
  proveedor; el cliente solo puede VERIFICAR con la pública. Es imposible emitir
  una licencia válida sin la privada. (Base: firma digital Ed25519, RFC 8032.)

SEGURIDAD:
  - La llave PRIVADA vive SOLO en `tools_licencia/vortex_private.key` (lado
    proveedor). NUNCA se distribuye ni se empaqueta en el .exe.
  - La llave PÚBLICA se embebe en el POS; es inofensiva si la ven.

FORMATO DEL CÓDIGO (compacto, optimizado para WhatsApp):
  VX1.<payload_b64>.<firma_b64>
    - VX1          : prefijo de versión (Vortex v1).
    - payload_b64  : JSON MÍNIMO, codificado en Base64URL (sin padding).
                     Claves de 1 letra: h (hash huella), v (vence: YYYYMMDD),
                     g (gracia). NO incluye cliente_id: el POS ya conoce el
                     suyo y la pertenencia se valida por el hash de la huella.
    - firma_b64    : firma Ed25519 (64 bytes), codificada en Base64URL.

POR QUÉ COMPACTO:
  El código se envía por WhatsApp y se pega a mano. Cada carácter de más aumenta
  el riesgo de truncado/error de copiado. Por eso el payload usa claves de 1
  letra, fecha compacta y solo el HASH de 8 de la huella; y la codificación es
  Base64URL (6 bits/carácter) en vez de Base32 (5 bits/carácter), ~17% más corto.

  PISO MATEMÁTICO HONESTO: la firma Ed25519 pesa 64 bytes FIJOS. No se puede
  reducir sin degradar la seguridad. El código queda en ~130 caracteres (cabe
  holgado en un mensaje de WhatsApp, sin cortes). Reducir más exigiría un esquema
  simétrico (HMAC) que metería el secreto en el POS: INACEPTABLE.

El payload es legible (no secreto): su integridad la garantiza la firma. El POS
recomputa la huella de la máquina y compara su hash con el del payload para atar
la licencia a ESE equipo.
"""

from __future__ import annotations

import base64
import hashlib
import json
import platform
import uuid
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Prefijo de versión del formato de licencia.
PREFIJO_VX = "VX1"

# Marcador inicial del texto de huella mostrado al cliente.
PREFIJO_HUELLA = "POS"


# ==========================================================================
# CODIFICACIÓN BASE64URL (sin padding, alfabeto seguro para WhatsApp/URLs)
# ==========================================================================
# Base64URL usa 6 bits por carácter (vs 5 de Base32) => ~17% más corto.
# Alfabeto: A-Z a-z 0-9 - _  (sin '+', '/', '=' que rompen en mensajería).


def _b64url_encodear(data: bytes) -> str:
    """Codifica bytes a Base64URL sin padding (fácil de copiar/pegar)."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decodear(texto: str) -> bytes:
    """Decodifica Base64URL tolerando la ausencia de padding."""
    t = (texto or "").strip()
    faltante = (-len(t)) % 4
    return base64.urlsafe_b64decode(t + ("=" * faltante))


# ==========================================================================
# HUELLA DE MÁQUINA
# ==========================================================================


def _datos_hardware_estables() -> str:
    """Reúne identificadores de hardware lo más estables posible.

    Objetivo: que la huella sobreviva a reinicios y usos normales, pero cambie
    si el equipo es otro. Se combinan varios identificadores porque ninguno por
    separado es perfecto:
      - uuid.getnode() -> MAC (estable salvo cambio de placa de red).
      - platform.node() -> nombre del equipo.
      - platform.arquitectura + sistema -> firma del sistema.
    Nota: en contenedores/VMs puede ser inestable; se documenta como límite.
    """
    partes = [
        str(uuid.getnode()),
        platform.node(),
        platform.system(),
        platform.machine(),
    ]
    return "|".join(partes)


def calcular_hash_huella(cliente_id: str) -> str:
    """Devuelve SOLO el hash de 8 caracteres de la huella (sin prefijos).

    Es lo que viaja dentro del código firmado: compacto, pero suficiente para
    atar la licencia a ESTA máquina (el POS recomputa y compara el hash).
    """
    material = f"{_datos_hardware_estables()}|{cliente_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest().upper()[:8]


def calcular_huella(cliente_id: str) -> str:
    """Calcula la huella de ESTA máquina para el `cliente_id` dado.

    La huella ata la licencia a un equipo concreto: copiar el código a otra PC
    hace que la huella no coincida y la verificación falle.

    Formato devuelto: 'POS-<HASH8>-<CLIENTEID>' -> p.ej. 'POS-A8F299B1-DEMO'.
    Este texto es el que se MUESTRA al cliente (legible). Dentro del código
    firmado solo viaja el <HASH8> (ver `calcular_hash_huella`).
    """
    digest = calcular_hash_huella(cliente_id)
    cid = (cliente_id or "demo").strip().upper()
    return f"{PREFIJO_HUELLA}-{digest}-{cid}"


# ==========================================================================
# FIRMA (lado proveedor — requiere llave privada)
# ==========================================================================


def firmar_licencia(
    private_key: Ed25519PrivateKey,
    cliente_id: str,
    huella: str,
    fecha_vencimiento: date,
    dias_gracia: int = 7,
) -> str:
    """Firma una licencia y devuelve el código `VX1.<payload>.<firma>` (compacto).

    Este código lo genera SOLO el proveedor (con su llave privada) y se envía
    al cliente para que lo pegue en el POS.

    El payload es MÍNIMO para WhatsApp: solo hash de huella (h), fecha (v) y
    gracia (g). NO incluye cliente_id (el POS ya lo conoce; la pertenencia se
    valida por el hash). Acepta la huella en cualquiera de sus formatos
    ('POS-<hash8>-<cid>' o '<hash8>') y extrae el hash. `cliente_id` se conserva
    en la firma como parámetro para trazabilidad del lado proveedor.
    """
    # Extraer el hash de 8 de la huella (tolerando formato largo o corto).
    huella_txt = (huella or "").strip().upper()
    if huella_txt.startswith(f"{PREFIJO_HUELLA}-") and huella_txt.count("-") >= 2:
        hash_huella = huella_txt.split("-")[1]
    else:
        hash_huella = huella_txt

    payload = {
        "h": hash_huella,
        "v": fecha_vencimiento.strftime("%Y%m%d"),
        "g": int(dias_gracia),
    }
    # compact separators: código más corto (mejor para WhatsApp).
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )

    firma = private_key.sign(payload_bytes)

    return f"{PREFIJO_VX}.{_b64url_encodear(payload_bytes)}.{_b64url_encodear(firma)}"


# ==========================================================================
# VERIFICACIÓN (lado POS — requiere llave pública)
# ==========================================================================


@dataclass
class ResultadoVerificacion:
    """Resultado de verificar un código de licencia."""

    valido: bool
    motivo: str  # descripción legible del resultado
    cliente_id: str | None = None
    huella: str | None = None
    fecha_vencimiento: date | None = None
    dias_gracia: int | None = None


def verificar_licencia(
    public_key: Ed25519PublicKey,
    codigo: str,
    huella_esperada: str,
) -> ResultadoVerificacion:
    """Verifica un código `VX1.<payload>.<firma>` contra la llave pública.

    Comprueba, EN ESTE ORDEN:
      1. Formato y prefijo válidos.
      2. Firma criptográfica válida (prueba que lo emitió el proveedor).
      3. La huella del payload coincide con ESTA máquina.
      4. La fecha de vencimiento es legible.

    NOTA: la vigencia por fecha NO se decide aquí; el bloqueo por vencimiento
    sigue viviendo en `licencia_service.evaluar` (una sola fuente de verdad).
    Esta función solo garantiza autenticidad + pertenencia + parseo.
    """
    if not codigo or not isinstance(codigo, str):
        return ResultadoVerificacion(False, "Código vacío.")

    partes = codigo.strip().split(".")
    if len(partes) != 3 or partes[0] != PREFIJO_VX:
        return ResultadoVerificacion(
            False, "Formato de código inválido (se espera VX1.<payload>.<firma>)."
        )

    try:
        payload_bytes = _b64url_decodear(partes[1])
        firma = _b64url_decodear(partes[2])
    except Exception:  # noqa: BLE001 (base64url inválido => código corrupto)
        return ResultadoVerificacion(False, "Código corrupto (no se pudo decodificar).")

    # 2) Firma criptográfica.
    try:
        public_key.verify(firma, payload_bytes)
    except InvalidSignature:
        return ResultadoVerificacion(
            False, "Firma inválida: la licencia no fue emitida por Vortex."
        )

    # 3) Parseo del payload mínimo {h, v, g}.
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
        hash_payload = str(payload["h"]).strip().upper()
        vence = datetime.strptime(str(payload["v"]), "%Y%m%d").date()
        gracia = int(payload.get("g", 0))
    except Exception:  # noqa: BLE001 (payload manipulado/anómalo)
        return ResultadoVerificacion(False, "Contenido de licencia inválido.")

    # 4) Pertenencia a esta máquina: comparar por HASH de huella.
    # Se acepta 'huella_esperada' en formato largo ('POS-<hash8>-<cid>') o el
    # hash solo ('<hash8>'): en ambos casos se extrae el hash de 8.
    esperada_txt = (huella_esperada or "").strip().upper()
    if esperada_txt.startswith(f"{PREFIJO_HUELLA}-") and esperada_txt.count("-") >= 2:
        hash_esperado = esperada_txt.split("-")[1]
    else:
        hash_esperado = esperada_txt

    if hash_payload != hash_esperado:
        return ResultadoVerificacion(
            False,
            "La licencia es para otra máquina (la huella no coincide).",
            huella=hash_payload,
        )

    return ResultadoVerificacion(
        True,
        "Licencia válida.",
        huella=hash_payload,
        fecha_vencimiento=vence,
        dias_gracia=gracia,
    )


# ==========================================================================
# CARGA DE LA LLAVE PÚBLICA (lado POS)
# ==========================================================================

# Ruta del archivo con la llave pública que acompaña al backend. Vive dentro de
# `app/` (no en el frontend): el navegador nunca la ve. NO es secreta, pero se
# mantiene del lado servidor por higiene y para poder rotarla sin tocar JS.
RUTA_PUBLICA_DEFECTO = Path(__file__).resolve().parent.parent / "licencia_public.key"


class LlavePublicaNoDisponible(Exception):
    """La llave pública del proveedor no está cargada en esta instalación.

    Se levanta en la ACTIVACIÓN (fail-secure): sin llave no se puede verificar
    ninguna licencia, así que se rechaza la activación con este error. El resto
    del sistema (bloqueo por fecha, ventas, etc.) sigue operativo.
    """


def cargar_llave_publica(ruta: Path | str | None = None) -> Ed25519PublicKey:
    """Carga la llave pública Ed25519 desde disco.

    Args:
        ruta: ruta alternativa; por defecto `app/licencia_public.key`.

    Raises:
        LlavePublicaNoDisponible: si el archivo no existe o está corrupto.
    """
    objetivo = Path(ruta) if ruta is not None else RUTA_PUBLICA_DEFECTO
    try:
        pem = objetivo.read_bytes()
    except OSError as exc:
        raise LlavePublicaNoDisponible(
            f"No se encontró la llave pública en {objetivo}."
        ) from exc

    from cryptography.hazmat.primitives import serialization

    try:
        key = serialization.load_pem_public_key(pem)
    except Exception as exc:  # noqa: BLE001 (PEM corrupto)
        raise LlavePublicaNoDisponible(
            "La llave pública está corrupta (PEM inválido)."
        ) from exc

    if not isinstance(key, Ed25519PublicKey):
        raise LlavePublicaNoDisponible("La llave pública no es de tipo Ed25519.")
    return key


def verificar_codigo_para_maquina(
    codigo: str, cliente_id: str, ruta_publica: Path | str | None = None
) -> ResultadoVerificacion:
    """Verifica un código contra la máquina actual, cargando la pública sola.

    Conveniencia para el router: calcula la huella de ESTA máquina para
    `cliente_id`, carga la pública y delega en `verificar_licencia`.

    Raises:
        LlavePublicaNoDisponible: si falta o está corrupta la pública.
    """
    public_key = cargar_llave_publica(ruta_publica)
    huella = calcular_huella(cliente_id)
    return verificar_licencia(public_key, codigo, huella)
