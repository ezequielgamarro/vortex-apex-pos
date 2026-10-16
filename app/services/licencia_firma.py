"""Servicio de firma y verificación de códigos (licencias, altas y recuperación).

ARQUITECTURA (patrón desafío-respuesta / challenge-response):
  - El POS del cliente calcula una HUELLA de su máquina.
  - El proveedor (Vortex) FIRMA un código con su LLAVE PRIVADA (Ed25519).
  - El POS VERIFICA el código con la LLAVE PÚBLICA (embebida en el programa).

POR QUÉ FIRMA Y NO ENCRIPTACIÓN:
  Encriptar exige que el cliente tenga la clave para desencriptar; si la tiene,
  puede generar licencias. FIRMAR no: la llave privada NUNCA sale del lado del
  proveedor; el cliente solo puede VERIFICAR con la pública. Es imposible emitir
  un código válido sin la privada. (Base: firma digital Ed25519, RFC 8032.)

SEGURIDAD:
  - La llave PRIVADA vive SOLO en `tools_licencia/vortex_private.key` (lado
    proveedor). NUNCA se distribuye ni se empaqueta en el .exe.
  - La llave PÚBLICA se embebe en el POS; es inofensiva si la ven.

TIPOS DE CÓDIGO (todos `<PREFIJO>.<payload_b64url>.<firma_b64url>`):
  VX1  Licencia (formato original; sigue siendo válido).
       payload: {h: hash de huella, v: vence AAAAMMDD, g: días de gracia}
  VX2  Licencia con número de serie (anti-repetición).
       payload: {t:"lic", h, v, g, n: serie entera creciente}
  VXA  Alta del primer administrador de un comercio.
       payload: {t:"alta", h, r: rubro, n: n° de emisión, c: cliente_id (opcional)}
  VXR  Recuperación de contraseña del administrador.
       payload: {t:"rec", h, n: serie entera creciente, v: vence AAAAMMDD,
                 u: email del usuario (opcional)}

  El tipo `t` va DENTRO de lo firmado: un código de un tipo no puede
  reinterpretarse como otro cambiándole el prefijo.

HUELLA:
  Hash SHA-256 de datos del equipo + cliente_id. Se muestra con 16 caracteres
  hexadecimales. Dentro de lo firmado viajan solo los primeros 8 (VX1) o 12
  (tipos nuevos) para que el código sea corto; se compara por prefijo.

El payload es legible (no secreto): su integridad la garantiza la firma.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import secrets
import uuid
from collections.abc import Sequence
from functools import lru_cache
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Prefijos de tipo de código.
PREFIJO_VX = "VX1"  # licencia (original)
PREFIJO_VX2 = "VX2"  # licencia con número de serie
PREFIJO_ALTA = "VXA"
PREFIJO_REC = "VXR"

# Marcador inicial del texto de huella mostrado al cliente.
PREFIJO_HUELLA = "POS"

# Largo del hash de huella que se MUESTRA (hex).
LARGO_HASH_HUELLA = 16
# Largo que viaja DENTRO de lo firmado. Se mantiene corto para que el código sea
# cómodo de copiar por WhatsApp: VX1 conserva los 8 originales y los tipos nuevos
# usan 12. Alargarlo no mejora la seguridad: lo falsificable son los datos del
# equipo (MAC, nombre) de los que sale el hash, no cuántos caracteres se firman.
_LARGO_H_VX1 = 8
_LARGO_H_NUEVO = 12
_MIN_HASH_PAYLOAD = 8


# ==========================================================================
# CODIFICACIÓN BASE64URL (sin padding, alfabeto seguro para WhatsApp/URLs)
# ==========================================================================


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
      - platform.machine() + system -> firma del sistema.
    LÍMITE HONESTO: MAC y nombre de equipo se pueden falsificar; la huella ata
    la licencia a un equipo en la práctica, no es una defensa criptográfica.
    Es la huella ORIGINAL: se conserva porque las licencias ya emitidas la usan.
    La huella que se muestra hoy suma identificadores de Windows (ver
    `_senales_hardware_v2`).
    """
    partes = [
        str(uuid.getnode()),
        platform.node(),
        platform.system(),
        platform.machine(),
    ]
    return "|".join(partes)


@lru_cache(maxsize=1)
def _senales_hardware_v2() -> tuple[str, ...]:
    """Identificadores de Windows más difíciles de falsificar que MAC y nombre.

    Todos salen del registro o de una llamada al sistema (sin lanzar procesos, así
    que son instantáneos): MachineGuid (se genera al instalar Windows), número de
    serie del volumen del sistema y datos de BIOS/placa base. Si una señal no está
    disponible se omite. Sin ninguna (otro sistema operativo) devuelve vacío y la
    huella queda en el formato original.
    """
    señales: list[str] = []
    try:
        import winreg

        def _leer(ruta: str, valor: str) -> str:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, ruta, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            ) as clave:
                return str(winreg.QueryValueEx(clave, valor)[0]).strip()

        try:
            señales.append("guid:" + _leer(r"SOFTWARE\Microsoft\Cryptography", "MachineGuid"))
        except OSError:
            pass
        bios = []
        for valor in ("SystemManufacturer", "SystemProductName", "BaseBoardProduct"):
            try:
                bios.append(_leer(r"HARDWARE\DESCRIPTION\System\BIOS", valor))
            except OSError:
                bios.append("")
        if any(bios):
            señales.append("bios:" + "/".join(bios))
    except ImportError:
        return ()
    try:
        import ctypes

        serie = ctypes.c_uint32(0)
        unidad = os.environ.get("SystemDrive", "C:") + "\\"
        ok = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(unidad), None, 0, ctypes.byref(serie), None, None, None, 0
        )
        if ok and serie.value:
            señales.append(f"vol:{serie.value:08X}")
    except Exception:  # noqa: BLE001 (sin ctypes/windll: se omite la señal)
        pass
    return tuple(señales)


def _hash_legacy(cliente_id: str) -> str:
    material = f"{_datos_hardware_estables()}|{cliente_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest().upper()[:LARGO_HASH_HUELLA]


def _hash_v2(cliente_id: str) -> str | None:
    señales = _senales_hardware_v2()
    if not señales:
        return None
    material = f"v2|{'|'.join(señales)}|{cliente_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest().upper()[:LARGO_HASH_HUELLA]


def calcular_hash_huella(cliente_id: str) -> str:
    """Devuelve el hash de la huella (16 hex), sin prefijos.

    Es el hash v2 (identificadores de Windows) cuando la PC los tiene; si no, el
    original. Los códigos VX1 antiguos llevan solo los 8 primeros caracteres: se
    comparan por prefijo (ver `_hash_coincide`).
    """
    return _hash_v2(cliente_id) or _hash_legacy(cliente_id)


def calcular_huella(cliente_id: str) -> str:
    """Calcula la huella de ESTA máquina para el `cliente_id` dado.

    Formato devuelto: 'POS-<HASH16>-<CLIENTEID>' -> p.ej.
    'POS-A8F299B1C03D55E2-DEMO'. Es el texto que se MUESTRA al cliente.
    """
    digest = calcular_hash_huella(cliente_id)
    cid = (cliente_id or "demo").strip().upper()
    return f"{PREFIJO_HUELLA}-{digest}-{cid}"


def huellas_aceptadas(cliente_id: str) -> tuple[str, ...]:
    """Huellas con las que un código firmado puede coincidir en ESTA máquina.

    La actual (v2) primero y la original después: así los clientes que ya tienen
    una licencia firmada con la huella original no la pierden al actualizar. Los
    códigos nuevos se emiten con la huella que muestra el programa (v2).
    """
    cid = (cliente_id or "demo").strip().upper()
    huellas = [calcular_huella(cliente_id)]
    legacy = f"{PREFIJO_HUELLA}-{_hash_legacy(cliente_id)}-{cid}"
    if legacy not in huellas:
        huellas.append(legacy)
    return tuple(huellas)


def _extraer_hash_huella(huella: str) -> str:
    """Obtiene el hash de una huella ('POS-<hash>-<cid>' o '<hash>')."""
    txt = (huella or "").strip().upper()
    if txt.startswith(f"{PREFIJO_HUELLA}-") and txt.count("-") >= 2:
        return txt.split("-")[1]
    return txt


def _hash_coincide(hash_payload: str, huella_esperada: "str | Sequence[str]") -> bool:
    """¿El hash firmado corresponde a esta máquina? Compara por prefijo.

    Acepta hashes firmados de 8 a 16 caracteres (los VX1 viejos usan 8), pero
    nunca vacíos ni más largos que el hash real. Comparación en tiempo constante.
    `huella_esperada` puede ser una huella o varias (ver `huellas_aceptadas`).
    """
    h = (hash_payload or "").strip().upper()
    candidatas = [huella_esperada] if isinstance(huella_esperada, str) else list(huella_esperada)
    coincide = False
    for huella in candidatas:
        esperado = _extraer_hash_huella(huella)
        if len(h) < _MIN_HASH_PAYLOAD or len(h) > len(esperado):
            continue
        if secrets.compare_digest(esperado[: len(h)], h):
            coincide = True
    return coincide


def _serializar(payload: dict) -> bytes:
    """JSON compacto y estable (claves ordenadas): lo que se firma."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _armar(private_key: Ed25519PrivateKey, prefijo: str, payload: dict) -> str:
    payload_bytes = _serializar(payload)
    firma = private_key.sign(payload_bytes)
    return f"{prefijo}.{_b64url_encodear(payload_bytes)}.{_b64url_encodear(firma)}"


class _CodigoInvalido(Exception):
    """Código malformado, con firma inválida o de otro tipo."""


def _abrir(
    public_key: Ed25519PublicKey, codigo: str, prefijos: tuple[str, ...], nombre: str
) -> tuple[str, dict]:
    """Valida formato + firma y devuelve (prefijo, payload). Lanza `_CodigoInvalido`."""
    if not codigo or not isinstance(codigo, str):
        raise _CodigoInvalido("Código vacío.")
    partes = codigo.strip().split(".")
    if len(partes) != 3 or partes[0] not in prefijos:
        raise _CodigoInvalido(
            f"Formato inválido (se espera un código de {nombre}: "
            f"<{'|'.join(prefijos)}>.<payload>.<firma>)."
        )
    try:
        payload_bytes = _b64url_decodear(partes[1])
        firma = _b64url_decodear(partes[2])
    except Exception:  # noqa: BLE001 (base64url inválido => código corrupto)
        raise _CodigoInvalido("Código corrupto (no se pudo decodificar).")
    try:
        public_key.verify(firma, payload_bytes)
    except InvalidSignature:
        raise _CodigoInvalido("Firma inválida: el código no fue emitido por Vortex.")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
    except Exception:  # noqa: BLE001
        raise _CodigoInvalido("Contenido del código inválido.")
    return partes[0], payload


# ==========================================================================
# LICENCIA (VX1 / VX2)
# ==========================================================================


def firmar_licencia(
    private_key: Ed25519PrivateKey,
    cliente_id: str,
    huella: str,
    fecha_vencimiento: date,
    dias_gracia: int = 7,
    serie: int | None = None,
) -> str:
    """Firma una licencia y devuelve el código (lado proveedor).

    Con `serie` (entero creciente, p. ej. la hora de emisión) se emite VX2, que
    el POS rechaza si ya aplicó uno igual o más nuevo (no se puede repetir un
    código viejo). Sin `serie` se emite VX1 (formato original, sin anti-repetición).
    `cliente_id` se conserva como parámetro para trazabilidad del proveedor.
    """
    largo = _LARGO_H_VX1 if serie is None else _LARGO_H_NUEVO
    payload = {
        "h": _extraer_hash_huella(huella)[:largo],
        "v": fecha_vencimiento.strftime("%Y%m%d"),
        "g": int(dias_gracia),
    }
    if serie is None:
        return _armar(private_key, PREFIJO_VX, payload)
    payload["t"] = "lic"
    payload["n"] = int(serie)
    return _armar(private_key, PREFIJO_VX2, payload)


@dataclass
class ResultadoVerificacion:
    """Resultado de verificar un código de licencia."""

    valido: bool
    motivo: str  # descripción legible del resultado
    cliente_id: str | None = None
    huella: str | None = None
    fecha_vencimiento: date | None = None
    dias_gracia: int | None = None
    serie: int | None = None  # None en VX1 (sin anti-repetición)


def verificar_licencia(
    public_key: Ed25519PublicKey,
    codigo: str,
    huella_esperada: "str | Sequence[str]",
) -> ResultadoVerificacion:
    """Verifica un código de licencia (VX1 o VX2) contra la llave pública.

    Comprueba, EN ESTE ORDEN: formato, firma, tipo/contenido, y que la huella
    firmada sea la de ESTA máquina. La vigencia por fecha y la repetición de
    series NO se deciden aquí (viven en el router y en `licencia_service`).
    """
    try:
        prefijo, payload = _abrir(
            public_key, codigo, (PREFIJO_VX, PREFIJO_VX2), "licencia"
        )
    except _CodigoInvalido as exc:
        return ResultadoVerificacion(False, str(exc))

    try:
        hash_payload = str(payload["h"]).strip().upper()
        vence = datetime.strptime(str(payload["v"]), "%Y%m%d").date()
        gracia = int(payload.get("g", 0))
        serie = None
        if prefijo == PREFIJO_VX2:
            if payload.get("t") != "lic":
                return ResultadoVerificacion(False, "El código no es una licencia.")
            serie = int(payload["n"])
    except Exception:  # noqa: BLE001 (payload manipulado/anómalo)
        return ResultadoVerificacion(False, "Contenido de licencia inválido.")

    if not _hash_coincide(hash_payload, huella_esperada):
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
        serie=serie,
    )


# ==========================================================================
# ALTA DEL PRIMER ADMINISTRADOR (VXA)
# ==========================================================================


def firmar_alta(
    private_key: Ed25519PrivateKey,
    huella: str,
    rubro: str = "general",
    serie: str | None = None,
    cliente_id: str | None = None,
) -> str:
    """Firma un código de alta atado a la huella de una PC (lado proveedor).

    `cliente_id` (opcional) fija el identificador del comercio en la instalación:
    así una instalación REMOTA no necesita correr `configurar_cliente.py`.
    Ojo: la huella depende del cliente_id, así que tras el alta la huella
    cambia y la licencia se emite con la huella nueva.
    """
    payload = {
        "t": "alta",
        "h": _extraer_hash_huella(huella)[:_LARGO_H_NUEVO],
        "r": (rubro or "general").strip().lower(),
        "n": serie or secrets.token_hex(4),
    }
    if cliente_id:
        payload["c"] = cliente_id.strip().lower()
    return _armar(private_key, PREFIJO_ALTA, payload)


@dataclass
class ResultadoAlta:
    """Resultado de verificar un código de alta."""

    valido: bool
    motivo: str
    rubro: str | None = None
    serie: str | None = None
    cliente_id: str | None = None


def verificar_alta(
    public_key: Ed25519PublicKey, codigo: str, huella_esperada: "str | Sequence[str]"
) -> ResultadoAlta:
    """Verifica un código `VXA.<payload>.<firma>` para ESTA máquina."""
    try:
        _, payload = _abrir(public_key, codigo, (PREFIJO_ALTA,), "alta")
    except _CodigoInvalido as exc:
        return ResultadoAlta(False, str(exc))

    try:
        if payload.get("t") != "alta":
            return ResultadoAlta(False, "El código no es un código de alta.")
        hash_payload = str(payload["h"]).strip().upper()
        rubro = str(payload.get("r") or "general").strip().lower()
        serie = str(payload.get("n") or "")
        cliente_id = str(payload["c"]).strip().lower() if payload.get("c") else None
    except Exception:  # noqa: BLE001
        return ResultadoAlta(False, "Contenido del código inválido.")

    if not _hash_coincide(hash_payload, huella_esperada):
        return ResultadoAlta(False, "El código es para otra PC (la huella no coincide).")

    return ResultadoAlta(
        True, "Código de alta válido.", rubro=rubro, serie=serie, cliente_id=cliente_id
    )


# ==========================================================================
# RECUPERACIÓN DE CONTRASEÑA (VXR)
# ==========================================================================


def firmar_recuperacion(
    private_key: Ed25519PrivateKey,
    huella: str,
    serie: int,
    vence: date,
    email: str | None = None,
) -> str:
    """Firma un código que permite poner una contraseña nueva al administrador.

    Vale para UNA PC (huella), hasta `vence`, y una sola vez (la `serie` debe ser
    mayor que la última recuperación aplicada). Con `email` solo sirve para esa
    cuenta; sin él, para el primer administrador de la instalación.
    """
    payload = {
        "t": "rec",
        "h": _extraer_hash_huella(huella)[:_LARGO_H_NUEVO],
        "n": int(serie),
        "v": vence.strftime("%Y%m%d"),
    }
    if email:
        payload["u"] = email.strip().lower()
    return _armar(private_key, PREFIJO_REC, payload)


@dataclass
class ResultadoRecuperacion:
    valido: bool
    motivo: str
    serie: int | None = None
    vence: date | None = None
    email: str | None = None


def verificar_recuperacion(
    public_key: Ed25519PublicKey, codigo: str, huella_esperada: "str | Sequence[str]"
) -> ResultadoRecuperacion:
    """Verifica un código `VXR...` para ESTA máquina (no mira vencimiento ni serie)."""
    try:
        _, payload = _abrir(public_key, codigo, (PREFIJO_REC,), "recuperación")
    except _CodigoInvalido as exc:
        return ResultadoRecuperacion(False, str(exc))

    try:
        if payload.get("t") != "rec":
            return ResultadoRecuperacion(False, "El código no es de recuperación.")
        hash_payload = str(payload["h"]).strip().upper()
        serie = int(payload["n"])
        vence = datetime.strptime(str(payload["v"]), "%Y%m%d").date()
        email = str(payload["u"]).strip().lower() if payload.get("u") else None
    except Exception:  # noqa: BLE001
        return ResultadoRecuperacion(False, "Contenido del código inválido.")

    if not _hash_coincide(hash_payload, huella_esperada):
        return ResultadoRecuperacion(
            False, "El código es para otra PC (la huella no coincide)."
        )
    return ResultadoRecuperacion(
        True, "Código de recuperación válido.", serie=serie, vence=vence, email=email
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
    ningún código, así que se rechaza con este error. El resto del sistema
    (bloqueo por fecha, ventas, etc.) sigue operativo.
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
    """Verifica una licencia contra la máquina actual, cargando la pública sola.

    Raises:
        LlavePublicaNoDisponible: si falta o está corrupta la pública.
    """
    public_key = cargar_llave_publica(ruta_publica)
    return verificar_licencia(public_key, codigo, huellas_aceptadas(cliente_id))


def verificar_alta_para_maquina(
    codigo: str, cliente_id: str, ruta_publica: Path | str | None = None
) -> ResultadoAlta:
    """Verifica un código de alta contra la máquina actual (carga la pública).

    Raises:
        LlavePublicaNoDisponible: si falta o está corrupta la pública.
    """
    public_key = cargar_llave_publica(ruta_publica)
    return verificar_alta(public_key, codigo, huellas_aceptadas(cliente_id))


def verificar_recuperacion_para_maquina(
    codigo: str, cliente_id: str, ruta_publica: Path | str | None = None
) -> ResultadoRecuperacion:
    """Verifica un código de recuperación contra la máquina actual.

    Raises:
        LlavePublicaNoDisponible: si falta o está corrupta la pública.
    """
    public_key = cargar_llave_publica(ruta_publica)
    return verificar_recuperacion(public_key, codigo, huellas_aceptadas(cliente_id))
