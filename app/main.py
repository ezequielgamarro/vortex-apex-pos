"""Punto de entrada principal de la API de Punto de Venta."""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Modelos ORM: importarlos ANTES de create_all para que las tablas de
# cada modelo queden registradas en Base.metadata.
import app.models  # noqa: F401  (efecto secundario intencional: registrar tablas)

from app.config import settings
from app.database import Base, engine
from app.dependencies import AuthError
from app.routers import (
    productos,
    ventas,
    arqueo,
    reportes,
    auth,
    categorias,
    cuentas,
    configuracion,
    licencia,
)


def _ruta_frontend() -> str:
    """Resuelve la carpeta de UI estática de forma robusta (dev y empaquetado).

    - Desarrollo: `frontend/` en la raíz del proyecto (junto a app/).
    - Exe PyInstaller (onefile): PyInstaller extrae `frontend` a `sys._MEIPASS`,
      de modo que aquí se apunta ahí (lectura estática).
    """
    if getattr(sys, "_MEIPASS", None):
        candidate = Path(sys._MEIPASS) / "frontend"
        if (candidate / "index.html").exists():
            return str(candidate)
    # Fallback desarrollo: raíz del proyecto = parent del paquete `app`.
    return str(Path(__file__).resolve().parent.parent / "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación.

    En el arranque: crea el archivo `pos_local.db` (si no existe) y genera
    todas las tablas definidas en los modelos (arranque idempotente). Después,
    si la base está VACÍA, siembra automáticamente el usuario administrador
    por defecto (ver app.seed) para permitir el primer acceso en una PC nueva.
    """
    import logging

    from app.database import SessionLocal  # noqa: PLC0415

    logger = logging.getLogger("uvicorn.error")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Base de datos SQLite verificada y tablas sincronizadas.")

        # Migración ligera y segura para bases pre-existentes (columnas nuevas).
        from app.migrations import run_light_migrations  # noqa: PLC0415

        _db = SessionLocal()
        try:
            run_light_migrations(_db)
        finally:
            _db.close()

        # Siembra automática del administrador en base vacía (producción).
        from app.seed import crear_admin_si_hace_falta  # noqa: PLC0415

        db = SessionLocal()
        try:
            crear_admin_si_hace_falta(db)
        finally:
            db.close()
    except Exception:
        # No detener el arranque si la BD falla transitoriamente; el log
        # permite diagnosticar. En producción, revisar el log.
        logger.exception("Error al inicializar la base de datos.")
    yield
    engine.dispose()


# Instancia de la aplicación
app = FastAPI(
    title=settings.APP_NAME,
    description="Backend para sistema de punto de venta de quiosco/drugstore.",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configuración de CORS (orígenes desde settings, evita cáscara dura)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware de licencia (bloqueo por falta de pago). Se agrega DESPUÉS
# de CORS para que envuelva las respuestas (incluye las de bloqueo).
from app.middleware.licencia import LicenciaMiddleware  # noqa: E402

app.add_middleware(LicenciaMiddleware)


# Manejador de errores de autenticación/autorización
@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detalle},
    )


# Manejador global de excepciones no controladas
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Devuelve un error 500 genérico sin filtrar detalles internos."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor. Contacta al administrador."},
    )


# ============================================================
# RUTAS DE SISTEMA (healthcheck) — deben registrarse ANTES de montar el
# StaticFiles en "/". Si la montura "/" (catch-all) se registrara antes,
# interceptaría TODA ruta y /health (el healthcheck del wrapper Electron)
# jamás llegaría aquí → pantalla blanca porque el backend "no responde".
# ============================================================
@app.get("/health", tags=["Health"])
def health() -> dict:
    """Healthcheck interno para Electron / orquestadores."""
    return {"status": "healthy", "env": settings.ENV}


@app.get("/", tags=["Health"])
def root() -> RedirectResponse:
    """Raíz: redirige a la UI de login servida como estático."""
    return RedirectResponse(url="/login.html")


# ============================================================
# REGISTRO DE ROUTERS DE LA API
# IMPORTANTE: deben registrarse ANTES del app.mount("/", StaticFiles...)
# para que el prefijo /api (y demás rutas) se resuelvan correctamente.
# Si el mount estático se registra primero, captura TODAS las rutas
# (incluido /api/*) y solo sirve GET/HEAD → POST/otros devuelven
# "Method Not Allowed" / 404 en la API.
# ============================================================
app.include_router(productos.router, prefix=settings.API_PREFIX)
app.include_router(ventas.router, prefix=settings.API_PREFIX)
app.include_router(arqueo.router, prefix=settings.API_PREFIX)
app.include_router(reportes.router, prefix=settings.API_PREFIX)
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(categorias.router, prefix=settings.API_PREFIX)
app.include_router(cuentas.router, prefix=settings.API_PREFIX)
app.include_router(configuracion.router, prefix=settings.API_PREFIX)
app.include_router(licencia.router, prefix=settings.API_PREFIX)

# Servir el frontend estático SIEMPRE EN ÚLTIMO LUGAR (catch-all)
app.mount("/", StaticFiles(directory=_ruta_frontend(), html=True), name="frontend")
