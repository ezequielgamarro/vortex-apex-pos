"""Configuración central de la aplicación.

Centraliza la carga de variables de entorno usando Pydantic Settings.
"""

import os
import secrets
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor que traían las versiones anteriores. Es público (estaba en el código),
# así que si aparece se descarta y se usa el secreto propio de la instalación.
_SECRET_DEFECTO_ANTIGUO = "dev-secret-change-me-por-entorno"


def _dir_datos() -> Path:
    """Carpeta de datos de la instalación (misma precedencia que database.py)."""
    user_data = os.environ.get("USER_DATA_DIR", "").strip()
    if user_data:
        return Path(user_data)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def _secreto_de_instalacion() -> str:
    """Devuelve el secreto JWT propio de esta instalación (lo crea si falta).

    Se genera al azar la primera vez y se guarda en `secret.key` dentro de la
    carpeta de datos. Así cada PC firma sus tokens con una clave distinta y
    secreta, sin depender de un `.env` que el instalador no incluye.
    """
    ruta = _dir_datos() / "secret.key"
    try:
        existente = ruta.read_text(encoding="utf-8").strip()
        if len(existente) >= 32:
            return existente
    except OSError:
        pass

    nuevo = secrets.token_hex(32)
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(nuevo, encoding="utf-8")
        try:
            os.chmod(ruta, 0o600)
        except OSError:
            pass
    except OSError:
        # Sin disco escribible: secreto efímero (las sesiones no sobreviven
        # a un reinicio, pero nunca se cae a un valor conocido).
        pass
    return nuevo


class Settings(BaseSettings):
    """Configuración global de la aplicación."""

    # Metadatos de la aplicación
    APP_NAME: str = "Punto de Venta API"
    APP_VERSION: str = "1.0.0"
    # Por defecto producción: en desarrollo se pone ENV=development en el .env
    # (habilita /docs). Un instalador sin .env queda en el modo seguro.
    ENV: str = "production"  # development | production

    # Seguridad local (JWT + hashing)
    # Si SECRET_KEY no se define por entorno, se usa el secreto propio de la
    # instalación (ver `_secreto_de_instalacion`). Nunca un valor fijo en código.
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 horas (jornada de trabajo)

    # Configuración opcional del API
    API_PREFIX: str = "/api"
    DEBUG: bool = False

    # Administrador semilla SOLO para desarrollo/automatización: si la base está
    # vacía y ADMIN_PASSWORD está definida, se crea ese admin al arrancar (ver
    # app/seed.py). Sin ADMIN_PASSWORD NO se crea nada: el primer administrador
    # de un cliente se da de alta con el asistente de primer arranque, que exige
    # un código firmado por el proveedor (ver app/routers/setup.py).
    ADMIN_EMAIL: str = ""  # fallback (vacío): admin@pos.local
    ADMIN_NOMBRE_COMPLETO: str = ""  # fallback (vacío): "Administrador"
    ADMIN_PASSWORD: str = ""

    # CORS (orígenes permitidos, separados por coma). Vacío = solo la propia
    # app local (127.0.0.1 y localhost en el puerto del backend).
    CORS_ORIGINS: str = ""

    # --- Licencia SaaS (control de pago remoto) ---
    # Texto de contacto (WhatsApp/tel/mail) mostrado en la pantalla de pago.
    LICENCIA_CONTACTO: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Lista de orígenes CORS permitidos."""
        crudo = self.CORS_ORIGINS.strip()
        if not crudo:
            puerto = os.environ.get("POS_BACKEND_PORT", "8000").strip() or "8000"
            return [f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}"]
        if crudo == "*":
            return ["*"]
        return [o.strip() for o in crudo.split(",") if o.strip()]


# Instancia singleton reutilizable en toda la app
settings = Settings()

_secreto_resuelto: str | None = None


def obtener_secreto() -> str:
    """Secreto con el que se firman los tokens de sesión.

    Se resuelve la primera vez que se pide (no al importar el módulo: importar
    no debe escribir archivos, p. ej. durante la compilación con PyInstaller).
    Nunca es el valor público de versiones anteriores ni uno vacío: si el
    entorno no define uno, se usa el propio de la instalación (`secret.key`).
    """
    global _secreto_resuelto
    if _secreto_resuelto is None:
        definido = settings.SECRET_KEY.strip()
        if definido and definido != _SECRET_DEFECTO_ANTIGUO:
            _secreto_resuelto = definido
        else:
            _secreto_resuelto = _secreto_de_instalacion()
    return _secreto_resuelto
