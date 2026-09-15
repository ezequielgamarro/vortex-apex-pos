"""Configuración central de la aplicación.

Centraliza la carga de variables de entorno usando Pydantic Settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración global de la aplicación."""

    # Metadatos de la aplicación
    APP_NAME: str = "Punto de Venta API"
    APP_VERSION: str = "1.0.0"
    ENV: str = "development"  # development | production

    # Seguridad local (JWT + hashing)
    # SECRET_KEY robusta. En producción, generar con:
    #   python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str = "dev-secret-change-me-por-entorno"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 horas (jornada de trabajo)

    # Configuración opcional del API
    API_PREFIX: str = "/api"
    DEBUG: bool = True

    # Configuración del usuario administrador por defecto.
    # Si la base queda VACÍA, el backend siembra este admin automáticamente en
    # el arranque (ver app/seed.py). Recomendado configurar ADMIN_PASSWORD con
    # una contraseña fuerte para entornos productivos.
    ADMIN_EMAIL: str = ""  # fallback (vacío): admin@pos.local
    ADMIN_NOMBRE_COMPLETO: str = ""  # fallback (vacío): "Administrador"
    ADMIN_PASSWORD: str = ""  # si vacío: dev=admin123, prod=aleatoria

    # CORS (orígenes permitidos, separados por coma)
    CORS_ORIGINS: str = "*"

    # --- Licencia SaaS (control de pago remoto) ---
    # Clave compartida con el SuperAdmin para activar/renovar la licencia
    # desde la instalacion local. Debe configurarse por entorno en prod.
    CLAVE_ACTIVACION: str = "ACTIVACION-DEMO"
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
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


# Instancia singleton reutilizable en toda la app
settings = Settings()
