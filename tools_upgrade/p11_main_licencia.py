"""Módulo 6 — Wire del router de licencia y el middleware en main.py."""
from tools_upgrade.patcher import apply

M = "app/main.py"

# 1) Importar el router de licencia.
apply(
    M,
    (
        "from app.routers import (\n"
        "    productos,\n"
        "    ventas,\n"
        "    arqueo,\n"
        "    reportes,\n"
        "    auth,\n"
        "    categorias,\n"
        "    cuentas,\n"
        "    configuracion,\n"
        ")",
        "from app.routers import (\n"
        "    productos,\n"
        "    ventas,\n"
        "    arqueo,\n"
        "    reportes,\n"
        "    auth,\n"
        "    categorias,\n"
        "    cuentas,\n"
        "    configuracion,\n"
        "    licencia,\n"
        ")",
    ),
)

# 2) Registrar el middleware DESPUÉS de CORS (el último add_middleware tiene
#    la primera prioridad de ejecución; el orden CORS->licencia garantiza que
#    las respuestas de licencia también lleven cabeceras CORS).
apply(
    M,
    (
        "# Manejador de errores de autenticación/autorización\n"
        "@app.exception_handler(AuthError)",
        "# Middleware de licencia (bloqueo por falta de pago). Se agrega DESPUÉS\n"
        "# de CORS para que envuelva las respuestas (incluye las de bloqueo).\n"
        "from app.middleware.licencia import LicenciaMiddleware  # noqa: E402\n"
        "\n"
        "app.add_middleware(LicenciaMiddleware)\n"
        "\n"
        "\n"
        "# Manejador de errores de autenticación/autorización\n"
        "@app.exception_handler(AuthError)",
    ),
)

# 3) Incluir el router de licencia.
apply(
    M,
    (
        "app.include_router(configuracion.router, prefix=settings.API_PREFIX)",
        "app.include_router(configuracion.router, prefix=settings.API_PREFIX)\n"
        "app.include_router(licencia.router, prefix=settings.API_PREFIX)",
    ),
)
print("[main licencia] OK")
