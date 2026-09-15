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

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Licencia, now_utc
from app.services.hora_externa import resolver_fecha_actual

DIAS_AVISO = 7


@dataclass
class EstadoLicencia:
    """Resultado de evaluar la licencia (contrato estable para la API)."""

    cliente_id: str
    estado: str            # activa | por_vencer | gracia | vencida | suspendida
    bloqueada: bool        # True => el middleware debe cortar operaciones
    fecha_actual: datetime
    fuente_hora: str       # externa | cache | delta_local | reloj_local
    fecha_vencimiento: datetime | None
    dias_restantes: int | None
    mensaje: str


def _get_o_crear(db: Session) -> Licencia:
    """Obtiene la licencia singleton o crea una licencia demo de 30 días.

    En una instalación nueva sin licencia cargada, se otorga una licencia demo
    temporal para no bloquear el negocio desde el segundo cero (evita un fallo
    de negocio por configuración). El instalador/SuperAdmin la reemplaza.
    """
    lic = db.query(Licencia).first()
    if lic is None:
        lic = Licencia(
            cliente_id="demo",
            fecha_vencimiento=now_utc() + timedelta(days=30),
            dias_gracia=3,
            estado="activa",
            ultimo_ping=now_utc(),
            actualizado_en=now_utc(),
        )
        db.add(lic)
        db.commit()
        db.refresh(lic)
    return lic


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

    if persistir_ping and (
        lic.ultimo_ping is None or fecha_actual > lic.ultimo_ping
    ):
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

    if lic.fecha_vencimiento is None:
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

    delta = lic.fecha_vencimiento - fecha_actual
    dias = delta.days
    limite_gracia = lic.fecha_vencimiento + timedelta(days=int(lic.dias_gracia or 0))

    if fecha_actual > limite_gracia:
        return EstadoLicencia(
            cliente_id=lic.cliente_id,
            estado="vencida",
            bloqueada=True,
            fecha_actual=fecha_actual,
            fuente_hora=fuente.fuente,
            fecha_vencimiento=lic.fecha_vencimiento,
            dias_restantes=dias,
            mensaje=(
                "La licencia venció. Regulariza el pago para continuar "
                "operando. Tus datos están a salvo."
            ),
        )

    if fecha_actual > lic.fecha_vencimiento:
        return EstadoLicencia(
            cliente_id=lic.cliente_id,
            estado="gracia",
            bloqueada=False,  # gracia: avisa pero permite operar
            fecha_actual=fecha_actual,
            fuente_hora=fuente.fuente,
            fecha_vencimiento=lic.fecha_vencimiento,
            dias_restantes=dias,
            mensaje=(
                f"Licencia vencida en período de gracia ({lic.dias_gracia} días). "
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
            fecha_vencimiento=lic.fecha_vencimiento,
            dias_restantes=dias,
            mensaje=f"Tu licencia vence en {dias} día(s).",
        )

    return EstadoLicencia(
        cliente_id=lic.cliente_id,
        estado="activa",
        bloqueada=False,
        fecha_actual=fecha_actual,
        fuente_hora=fuente.fuente,
        fecha_vencimiento=lic.fecha_vencimiento,
        dias_restantes=dias,
        mensaje="Licencia activa.",
    )


# Rutas de escritura (cobro de ventas, etc.) que se bloquean si la licencia
# está vencida. Las lecturas y la propia gestión de licencia SIEMPRE pasan,
# para que el negocio pueda consultar sus datos y pagar/regularizar.
PREFIJOS_BLOQUEADOS = ("/ventas", "/arqueo")
METODOS_ESCRITURA = {"POST", "PUT", "PATCH", "DELETE"}


def requiere_bloqueo(metodo: str, path: str) -> bool:
    """True si el request debe bloquearse por licencia vencida.

    Se bloquea SOLO la operación transaccional (cobrar/abrir-cerrar caja), no
    la lectura. Anular una venta es POST a /ventas/{id}/anular y también se
    bloquea (coherente). El login, perfil y /licencia/estado nunca se bloquean.
    """
    if metodo not in METODOS_ESCRITURA:
        return False
    # Normalizar: la ruta incluye el prefijo /api.
    p = path.split("?")[0]
    return any(p.startswith(pref) or f"/api{pref}" in p for pref in PREFIJOS_BLOQUEADOS)
