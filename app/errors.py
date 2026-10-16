"""Manejo de errores internos: el detalle técnico va al log, no al cliente."""

import logging

logger = logging.getLogger("uvicorn.error")


def detalle_error_interno(mensaje: str, exc: BaseException) -> str:
    """Registra el error completo en el log y devuelve solo el mensaje genérico.

    Se usa como `detail=` de un HTTPException 500. Así el cliente no ve mensajes
    de SQLAlchemy, rutas de archivos ni datos internos; quien da soporte los
    encuentra en el log del backend.
    """
    logger.error("%s", mensaje, exc_info=exc)
    return mensaje
