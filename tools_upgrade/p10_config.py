"""Módulo 6 — Settings de licencia (clave de activación y contacto)."""
from tools_upgrade.patcher import apply

apply(
    "app/config.py",
    (
        '    # CORS (orígenes permitidos, separados por coma)\n'
        '    CORS_ORIGINS: str = "*"',
        '    # CORS (orígenes permitidos, separados por coma)\n'
        '    CORS_ORIGINS: str = "*"\n'
        "\n"
        "    # --- Licencia SaaS (control de pago remoto) ---\n"
        "    # Clave compartida con el SuperAdmin para activar/renovar la licencia\n"
        "    # desde la instalacion local. Debe configurarse por entorno en prod.\n"
        '    CLAVE_ACTIVACION: str = "ACTIVACION-DEMO"\n'
        "    # Texto de contacto (WhatsApp/tel/mail) mostrado en la pantalla de pago.\n"
        '    LICENCIA_CONTACTO: str = ""',
    ),
)
print("[config licencia] OK")
