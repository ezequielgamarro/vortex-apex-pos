"""Módulo 6 — Servicio de licencia: evaluación de estado y anti-trampas.

Centraliza la regla de negocio de licenciamiento (single source of truth), de
modo que el middleware, el router y los reportes consuman la MISMA decisión.

Modelo de estado:
  - 'activa'    : dentro del plazo (+ gracia). Sin restricción.
  - 'por_vencer': <= 7 días para el vencimiento (aviso preventivo, no bloquea).
  - 'gracia'    : vencida pero dentro de `dias_gracia` (bloqueo suave: avisa).
  - 'vencida'   : fuera de gracia -> bloqueo. El frontend muestra pantalla de pago.
  - 'suspendida': bloqueada manualmente por el SuperAdmin.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import _dir_datos
from app.models import Licencia, now_utc
from app.services.hora_externa import resolver_fecha_actual
from app.services.licencia_firma import (
    LlavePublicaNoDisponible,
    _datos_hardware_estables,
    cargar_llave_publica,
    huellas_aceptadas,
    verificar_licencia,
)

logger = logging.getLogger("uvicorn.error")

DIAS_AVISO = 7
DIAS_DEMO = 30


@dataclass
class EstadoLicencia:
    """Resultado de evaluar la licencia (contrato estable para la API)."""

    cliente_id: str
    estado: str  # activa | por_vencer | gracia | vencida | suspendida
    bloqueada: bool  # True => el middleware debe cortar operaciones
    fecha_actual: datetime
    fuente_hora: str  # externa | cache | delta_local | reloj_local
    fecha_vencimiento: datetime | None
    dias_restantes: int | None
    mensaje: str


def _ruta_ancla():
    return _dir_datos() / "instalacion.json"


def _sello(inicio_iso: str) -> str:
    """Sello (HMAC) del ancla, atado a datos de esta PC."""
    clave = hashlib.sha256(
        ("vx-ancla|" + _datos_hardware_estables()).encode("utf-8")
    ).digest()
    return hmac.new(clave, inicio_iso.encode("utf-8"), hashlib.sha256).hexdigest()


def _inicio_instalacion(db_tenia_fila: bool = False) -> datetime:
    """Fecha en que se instaló por primera vez, guardada FUERA de la base.

    Así, borrar la fila de licencia (o la base) no devuelve otra demo de 30 días.
    Si el archivo falta se crea con la fecha actual; si fue modificado (sello
    inválido) se trata como una demo ya vencida.

    LÍMITE HONESTO: quien borre la base Y este archivo vuelve a empezar. Es una
    barrera comercial, no una defensa criptográfica (ver hora_externa.py).
    """
    ruta = _ruta_ancla()
    ahora = now_utc()
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
        inicio_iso = str(data["inicio"])
        if hmac.compare_digest(_sello(inicio_iso), str(data["sello"])):
            return datetime.fromisoformat(inicio_iso)
        logger.warning("[licencia] El ancla de instalación fue modificada.")
        return ahora - timedelta(days=365)
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001 (ilegible/corrupto)
        logger.warning("[licencia] El ancla de instalación es ilegible.")
        return ahora - timedelta(days=365)

    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        iso = ahora.replace(microsecond=0).isoformat()
        ruta.write_text(json.dumps({"inicio": iso, "sello": _sello(iso)}), encoding="utf-8")
    except OSError as exc:
        logger.warning("[licencia] No se pudo guardar el ancla: %s", exc)
    return ahora


def _get_o_crear(db: Session) -> Licencia:
    """Obtiene la licencia singleton o crea una licencia demo de 30 días.

    En una instalación nueva sin licencia cargada, se otorga una licencia demo
    temporal para no bloquear el negocio desde el segundo cero (evita un fallo
    de negocio por configuración). La demo cuenta desde la PRIMERA instalación
    (ancla fuera de la base), no desde que se crea la fila.
    """
    lic = db.query(Licencia).first()
    if lic is None:
        lic = Licencia(
            cliente_id="demo",
            fecha_vencimiento=_inicio_instalacion() + timedelta(days=DIAS_DEMO),
            dias_gracia=3,
            estado="activa",
            ultimo_ping=now_utc(),
            actualizado_en=now_utc(),
        )
        db.add(lic)
        db.commit()
        db.refresh(lic)
    elif not _ruta_ancla().exists():
        # Instalación anterior a esta versión: fija el ancla ahora.
        _inicio_instalacion(db_tenia_fila=True)
    return lic


# Resultado de verificar el código guardado: (vence, gracia) | None (sin código
# o sin llave pública: se usan las columnas) | _INVALIDA (firma/huella no valen).
_INVALIDA = "invalida"
_cache_vigencia: dict[tuple[str, str], object] = {}


def _vigencia_firmada(lic: Licencia):
    """Vencimiento y gracia tomados de LA FIRMA del código con que se activó.

    Editar `fecha_vencimiento` en la base no extiende la licencia cuando hay un
    código guardado: manda lo que dice el código firmado por el proveedor.
    """
    codigo = (lic.codigo_activacion or "").strip()
    if not codigo:
        return None
    clave = (codigo, lic.cliente_id or "demo")
    if clave in _cache_vigencia:
        return _cache_vigencia[clave]
    try:
        publica = cargar_llave_publica()
    except LlavePublicaNoDisponible:
        return None  # sin llave no se puede verificar: se usan las columnas
    res = verificar_licencia(publica, codigo, huellas_aceptadas(clave[1]))
    if res.valido:
        valor = (
            datetime.combine(res.fecha_vencimiento, datetime.min.time()),
            int(res.dias_gracia or 0),
        )
    else:
        logger.warning("[licencia] El código guardado ya no es válido: %s", res.motivo)
        valor = _INVALIDA
    _cache_vigencia[clave] = valor
    return valor


def evaluar(db: Session, persistir_ping: bool = False) -> EstadoLicencia:
    """Evalúa el estado de la licencia usando la hora más fiable disponible.

    Args:
        persistir_ping: si True, actualiza `ultimo_ping` con la fecha resuelta
            (se usa en el endpoint de estado para afianzar el anti-trampas).
    """
    lic = _get_o_crear(db)

    fuente = resolver_fecha_actual(lic.ultimo_ping)
    fecha_actual = fuente.fecha

    # Anti-trampas: la fecha actual NUNCA puede retroceder respecto al último
    # ping persistido. Si el usuario atrasó el reloj, se conserva el piso.
    if lic.ultimo_ping is not None and fecha_actual < lic.ultimo_ping:
        fecha_actual = lic.ultimo_ping

    if persistir_ping and (lic.ultimo_ping is None or fecha_actual > lic.ultimo_ping):
        lic.ultimo_ping = fecha_actual
        lic.actualizado_en = now_utc()
        db.commit()
        db.refresh(lic)

    # Regla de estado.
    if lic.estado == "suspendida":
        return EstadoLicencia(
            cliente_id=lic.cliente_id,
            estado="suspendida",
            bloqueada=True,
            fecha_actual=fecha_actual,
            fuente_hora=fuente.fuente,
            fecha_vencimiento=lic.fecha_vencimiento,
            dias_restantes=None,
            mensaje="Licencia suspendida por el administrador del sistema.",
        )

    # Vigencia: si hay un código firmado guardado, MANDA la firma (no las
    # columnas editables de la base).
    vigencia = _vigencia_firmada(lic)
    if vigencia == _INVALIDA:
        return EstadoLicencia(
            cliente_id=lic.cliente_id,
            estado="vencida",
            bloqueada=True,
            fecha_actual=fecha_actual,
            fuente_hora=fuente.fuente,
            fecha_vencimiento=lic.fecha_vencimiento,
            dias_restantes=None,
            mensaje=(
                "La licencia instalada no es válida para esta PC. Pedí un código "
                "nuevo a tu proveedor. Tus datos están a salvo."
            ),
        )
    if isinstance(vigencia, tuple):
        vence, gracia = vigencia
    else:
        vence, gracia = lic.fecha_vencimiento, int(lic.dias_gracia or 0)

    if vence is None:
        # Sin vencimiento definido: no se bloquea (evita falsos positivos).
        return EstadoLicencia(
            cliente_id=lic.cliente_id,
            estado="activa",
            bloqueada=False,
            fecha_actual=fecha_actual,
            fuente_hora=fuente.fuente,
            fecha_vencimiento=None,
            dias_restantes=None,
            mensaje="Licencia activa sin fecha de vencimiento.",
        )

    delta = vence - fecha_actual
    dias = delta.days
    limite_gracia = vence + timedelta(days=int(gracia or 0))

    if fecha_actual > limite_gracia:
        return EstadoLicencia(
            cliente_id=lic.cliente_id,
            estado="vencida",
            bloqueada=True,
            fecha_actual=fecha_actual,
            fuente_hora=fuente.fuente,
            fecha_vencimiento=vence,
            dias_restantes=dias,
            mensaje=(
                "La licencia venció. Regulariza el pago para continuar "
                "operando. Tus datos están a salvo."
            ),
        )

    if fecha_actual > vence:
        return EstadoLicencia(
            cliente_id=lic.cliente_id,
            estado="gracia",
            bloqueada=False,  # gracia: avisa pero permite operar
            fecha_actual=fecha_actual,
            fuente_hora=fuente.fuente,
            fecha_vencimiento=vence,
            dias_restantes=dias,
            mensaje=(
                f"Licencia vencida en período de gracia ({gracia} días). "
                "Regularizá el pago para evitar el bloqueo."
            ),
        )

    if dias <= DIAS_AVISO:
        return EstadoLicencia(
            cliente_id=lic.cliente_id,
            estado="por_vencer",
            bloqueada=False,
            fecha_actual=fecha_actual,
            fuente_hora=fuente.fuente,
            fecha_vencimiento=vence,
            dias_restantes=dias,
            mensaje=f"Tu licencia vence en {dias} día(s).",
        )

    return EstadoLicencia(
        cliente_id=lic.cliente_id,
        estado="activa",
        bloqueada=False,
        fecha_actual=fecha_actual,
        fuente_hora=fuente.fuente,
        fecha_vencimiento=vence,
        dias_restantes=dias,
        mensaje="Licencia activa.",
    )


# --- Tolerancia a fallos del control de licencia ----------------------------
# Si evaluar() falla por un error interno, NO se corta la venta de inmediato
# (un bug nuestro no debe dejar sin vender a un comercio), pero tampoco queda
# abierto para siempre: pasadas HORAS_TOLERANCIA_FALLO seguidas fallando, se
# bloquean las escrituras. El primer fallo se guarda FUERA de la base.
HORAS_TOLERANCIA_FALLO = 72


def _ruta_fallo():
    return _dir_datos() / "licencia_fallo.json"


def registrar_control_ok() -> None:
    """El control funcionó: borra el contador de fallos."""
    try:
        _ruta_fallo().unlink(missing_ok=True)
    except OSError:
        pass


def fallo_control_excedido(ahora: float | None = None) -> bool:
    """Registra un fallo del control y dice si ya pasó la tolerancia.

    True => hay que bloquear escrituras. Si no se puede leer ni escribir el
    archivo de estado se bloquea (cerrado): sin estado no hay forma de limitar
    la tolerancia.
    """
    ahora = time.time() if ahora is None else ahora
    ruta = _ruta_fallo()
    try:
        primero = float(json.loads(ruta.read_text(encoding="utf-8"))["primero"])
    except FileNotFoundError:
        primero = ahora
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps({"primero": primero}), encoding="utf-8")
        except OSError:
            return True
    except Exception:  # noqa: BLE001 (archivo ilegible o alterado)
        return True
    # Un "primero" en el futuro (reloj movido) también cierra.
    if primero > ahora + 3600:
        return True
    return (ahora - primero) > HORAS_TOLERANCIA_FALLO * 3600


# Rutas de escritura (cobro de ventas, caja y catálogo) que se bloquean si la
# licencia está vencida. Las lecturas y la propia gestión de licencia SIEMPRE
# pasan, para que el negocio pueda consultar sus datos y pagar/regularizar.
#
# NOTA (por qué /productos): el bloqueo por mora debe impedir OPERAR el
# negocio, no solo facturar. Un moroso que puede seguir creando/editando
# productos y cargando stock sigue derivando valor del sistema sin pagarlo.
# Por eso se bloquea la ESCRITURA del catálogo (crear/editar/borrar/importar),
# PERO se mantiene libre la lectura y el export a Excel (GET /productos/exportar),
# en coherencia con el principio de NO secuestrar los datos del comercio.
# /clientes (cuentas corrientes y abonos, que ingresan efectivo a la caja) y
# /categorias (catálogo) también son operatoria: sin ellos un moroso seguiría
# cobrando abonos y editando el catálogo con la licencia vencida.
PREFIJOS_BLOQUEADOS = ("/ventas", "/arqueo", "/productos", "/clientes", "/categorias")
METODOS_ESCRITURA = {"POST", "PUT", "PATCH", "DELETE"}


def requiere_bloqueo(metodo: str, path: str) -> bool:
    """True si el request debe bloquearse por licencia vencida.

    Se bloquea SOLO la ESCRITURA (POST/PUT/PATCH/DELETE) sobre las rutas de
    operatoria del negocio (ventas, caja y catálogo de productos), nunca la
    lectura. Así un moroso no puede facturar, ni abrir/cerrar caja, ni crear,
    editar, borrar o importar productos, PERO sí puede consultar y exportar
    sus datos (GET), en coherencia con el principio de no secuestrar la
    información del comercio.

    Casos concretos:
      - Anular una venta (POST /ventas/{id}/anular) -> se bloquea.
      - Exportar catálogo (GET /productos/exportar) -> NO se bloquea (lectura).
      - Importar catálogo (POST /productos/importar) -> se bloquea (escritura).
      - El login, perfil y /licencia/* nunca se bloquean (permiten regularizar).
    """
    if metodo not in METODOS_ESCRITURA:
        return False
    # Normalizar: la ruta incluye el prefijo /api.
    p = path.split("?")[0]
    return any(p.startswith(pref) or f"/api{pref}" in p for pref in PREFIJOS_BLOQUEADOS)
