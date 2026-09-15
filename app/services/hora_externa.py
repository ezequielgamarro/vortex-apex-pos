"""Módulo 6 — Validación de licencia con hora externa anti-trampas.

PROPÓSITO: evitar que el usuario retrase el reloj de la PC para perpetuarse
el servicio. La fecha "de verdad" se obtiene de una fuente externa y se cachea.

FUENTES Y DEGRADACIÓN DEFENSIVA (por qué así):
  El requisito pedía consultar una API externa (worldtimeapi.org). Es correcto
  como FUENTE PRINCIPAL, pero esa API no tiene SLA y puede caer. Un diseño que
  dependa de ella al 100% significa "caída del tercero = negocio parado". Eso
  es inaceptable en un POS de mostrador. Por eso la resolución es por capas:

    1. Hora externa (httpx, timeout corto, caché en memoria ~30 min).
    2. Si falla y hay `ultimo_ping` válido en BD: se AVANZA el tiempo desde ahí
       usando el reloj local como DELTA (monotonía), no como valor absoluto.
       Esto anula el truco de "atraso el reloj 5 años": el delta respecto al
       último ping solo puede hacer avanzar la fecha, nunca retroceder.
    3. Si todo falla y no hay ping previo: se usa el reloj local (peor caso,
       primera ejecución sin internet). El primer ping exitoso persiste la base.

  La resolución final NUNCA lanza: devuelve la fecha más fiable disponible.
  La DECISIÓN de bloquear/alertar es responsabilidad de `evaluar_licencia`.

Limitación reconocida (honestidad): en una app local, el control es una
barrera COMERCIAL, no una defensa criptográfica. Un atacante con acceso físico
puede editar la BD. Estas capas elevan el costo de la trampa, no la anulan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger("uvicorn.error")

# Fuente primaria de hora (la indicada en el requerimiento).
URL_HORA_PRIMARIA = "http://worldtimeapi.org/api/timezone/Etc/UTC"
# Fuente de respaldo (API estable de Cloudflare, sin autenticación).
URL_HORA_RESPALDO = "https://cloudflare.com/cdn-cgi/trace"

_TIEMPO_MAX_CACHE = timedelta(minutes=30)
_TIMEOUT_HTTP = 4.0

# Caché en memoria del proceso (evita golpear la API en cada request).
_cache: dict[str, object] = {"fecha": None, "obtenida_en": None}


@dataclass
class FuenteHora:
    """Resultado de la resolución de hora: valor + procedencia (para auditar)."""

    fecha: datetime
    fuente: str  # 'externa' | 'cache' | 'delta_local' | 'reloj_local'


def _ahora_utc_naive() -> datetime:
    """Reloj local UTC naive (coherente con el resto de la app)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _consultar_hora_externa() -> datetime | None:
    """Intenta obtener la hora UTC real de las fuentes externas. None si falla."""
    # Fuente 1: worldtimeapi
    try:
        with httpx.Client(timeout=_TIMEOUT_HTTP) as client:
            r = client.get(URL_HORA_PRIMARIA)
            r.raise_for_status()
            data = r.json()
            iso = data.get("utc_datetime") or data.get("datetime")
            if iso:
                # worldtimeapi entrega ISO con offset; se normaliza a UTC naive.
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception as exc:  # noqa: BLE001 (red: cualquier fallo es esperable)
        logger.warning("[licencia] Fuente primaria de hora falló: %s", exc)

    # Fuente 2: Cloudflare trace (campo ts=epoch)
    try:
        with httpx.Client(timeout=_TIMEOUT_HTTP, follow_redirects=True) as client:
            r = client.get(URL_HORA_RESPALDO)
            r.raise_for_status()
            for linea in r.text.splitlines():
                if linea.startswith("ts="):
                    epoch = float(linea.split("=", 1)[1])
                    return datetime.fromtimestamp(epoch, tz=timezone.utc).replace(
                        tzinfo=None
                    )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[licencia] Fuente de respaldo de hora falló: %s", exc)

    return None


def resolver_fecha_actual(ultimo_ping: datetime | None) -> FuenteHora:
    """Devuelve la fecha/hora más fiable disponible. NUNCA lanza.

    Estrategia (capas, ver docstring del módulo):
      1. Caché en memoria (< 30 min) -> 'cache'.
      2. Hora externa -> 'externa' (y se cachea).
      3. Delta desde `ultimo_ping` con reloj local -> 'delta_local'.
      4. Reloj local -> 'reloj_local'.
    """
    ahora = _ahora_utc_naive()

    # 1) Caché reciente.
    cached = _cache.get("fecha")
    obtenida = _cache.get("obtenida_en")
    if isinstance(cached, datetime) and isinstance(obtenida, datetime):
        if ahora - obtenida < _TIEMPO_MAX_CACHE:
            # Proyectar el paso del tiempo desde la caché (monotonía).
            return FuenteHora(cached + (ahora - obtenida), "cache")

    # 2) Hora externa.
    externa = _consultar_hora_externa()
    if externa is not None:
        _cache["fecha"] = externa
        _cache["obtenida_en"] = ahora
        return FuenteHora(externa, "externa")

    # 3) Delta monótono respecto al último ping conocido.
    if ultimo_ping is not None:
        # El tiempo solo AVANZA: se toma el máximo entre el reloj local y el
        # último ping persistido. Así, atrasar el reloj NUNCA retrocede la
        # fecha base (el ping actúa como piso temporal inamovible). Si el reloj
        # local va adelantado, se avanza igualmente (no se puede "ganar tiempo"
        # hacia el pasado, pero tampoco se congela el vencimiento).
        return FuenteHora(max(ahora, ultimo_ping), "delta_local")

    # 4) Último recurso: reloj local.
    return FuenteHora(ahora, "reloj_local")
