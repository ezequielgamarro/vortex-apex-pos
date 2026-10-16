"""Cabeceras de seguridad HTTP para todas las respuestas.

La interfaz es 100 % local (todo sale del mismo origen: HTML, JS, CSS, imágenes
y la API), así que se puede usar una Content-Security-Policy estricta:

  - script-src 'self'            : solo scripts propios. SIN 'unsafe-inline': un
                                   `<img onerror=...>` inyectado no se ejecuta.
  - connect-src 'self'           : la página solo habla con la API local; un
                                   script malicioso no puede enviar datos afuera.
  - object-src 'none', base-uri, form-action, frame-ancestors: cierran vectores
                                   clásicos (plugins, <base>, formularios ajenos,
                                   clickjacking).
  - style-src 'unsafe-inline'    : se mantiene porque hay `<style>` y estilos en
                                   línea; ejecutar CSS no ejecuta código.

ASGI puro (no BaseHTTPMiddleware) para no romper respuestas en streaming.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

_CABECERAS = [
    (b"content-security-policy", CSP.encode("latin-1")),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
]


class CabecerasSeguridadMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_con_cabeceras(message: Message) -> None:
            if message["type"] == "http.response.start":
                existentes = {k.lower() for k, _ in message.get("headers", [])}
                extra = [h for h in _CABECERAS if h[0] not in existentes]
                # Sin esto el navegador puede reutilizar HTML viejo tras una
                # actualización del programa. `no-cache` obliga a revalidar
                # (respuesta 304 instantánea: el servidor es local).
                if b"cache-control" not in existentes:
                    extra.append((b"cache-control", b"no-cache"))
                message = {
                    **message,
                    "headers": list(message.get("headers", [])) + extra,
                }
            await send(message)

        await self.app(scope, receive, send_con_cabeceras)
