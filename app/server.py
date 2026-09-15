"""Arranque del servidor HTTP local (punto de entrada ejecutable).

Es el módulo que se empaqueta como `pos-backend.exe` (ver `pos-backend.spec`).
Levanta la aplicación FastAPI a través de uvicorn de forma autónoma
(self-host) por su "import string" `"app.main:app"`, escuchando por defecto en
http://127.0.0.1:8000.

No modifica `app/main.py` (la aplicación "biblioteca"): el flujo de desarrollo
`uvicorn app.main:app --reload` sigue intacto. Este módulo existe únicamente
para que el .exe levantado por Electron no termine a los pocos segundos (antes
sólo se *importaba* el app y no se ejecutaba ningún servidor).

Host/puerto configurables vía entorno (deben coincidir con `electron/main.js`):
    POS_BACKEND_HOST=127.0.0.1
    POS_BACKEND_PORT=8000
"""

import os

if __name__ == "__main__":
    import uvicorn

    # Por defecto: 127.0.0.1:8000. Sobre-escribibles por el wrapper de Electron.
    host = os.environ.get("POS_BACKEND_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("POS_BACKEND_PORT", "8000"))
    except (TypeError, ValueError):
        port = 8000

    # Import string (recomendado por uvicorn): el propio uvicorn resuelve
    # "app.main:app". Un solo worker y event-loop normal -> proceso estable,
    # sin modo reload, adecuado para un ejecutable de escritorio.
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
