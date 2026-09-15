"""Módulo 6 — Middleware de bloqueo por licencia.

ASGI puro (no BaseHTTPMiddleware) para no romper el streaming de respuestas
(exportación de Excel vía StreamingResponse). Intercepta las operaciones
transaccionales (cobro, caja) y devuelve 402 Payment Required si la licencia
está vencida; el frontend interpreta ese código y muestra la pantalla de pago.

Por qué 402 y no 403: 402 ("Payment Required") comunica semánticamente que es
un problema de pago (distinto de falta de permisos), lo que permite al
frontend diferenciar "sesión caducada" de "licencia vencida" sin ambigüedad.

Por qué SOLO escritura: bloquear la lectura impediría al comerciante consultar
sus datos y regularizar. El bloqueo debe presionar el pago sin secuestrar la
información (principio de no-rehén de datos).
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from app.database import SessionLocal
from app.services.licencia_service import evaluar, requiere_bloqueo

logger = logging.getLogger("uvicorn.error")


class LicenciaMiddleware:
    """Middleware ASGI que aplica el bloqueo por licencia vencida."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        metodo = scope.get("method", "GET")

        # Guard clause: solo se evalúa lo que podría bloquearse (barato).
        if not requiere_bloqueo(metodo, path):
            await self.app(scope, receive, send)
            return

        bloqueada = False
        mensaje = ""
        # La BD se abre en un scope corto y se cierra siempre (no se filtra).
        db = SessionLocal()
        try:
            est = evaluar(db, persistir_ping=False)
            bloqueada = est.bloqueada
            mensaje = est.mensaje
        except Exception as exc:  # noqa: BLE001
            # FALLO ABIERTO (fail-open): si la evaluación falla por un error
            # inesperado, se PERMITE la operación. Nunca dejamos de vender por
            # un bug del subsistema de licencia (evita un fallo de negocio).
            logger.warning("[licencia] No se pudo evaluar; se permite operar: %s", exc)
            bloqueada = False
        finally:
            db.close()

        if bloqueada:
            import json

            body = json.dumps(
                {
                    "detail": mensaje or "Licencia vencida.",
                    "codigo": "LICENCIA_VENCIDA",
                }
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 402,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
