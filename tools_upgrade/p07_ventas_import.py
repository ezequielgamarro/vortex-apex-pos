"""Fix import: requiere_rol en ventas.py."""
from tools_upgrade.patcher import apply

apply(
    "app/routers/ventas.py",
    (
        "from app.dependencies import get_current_user, UsuarioActual",
        "from app.dependencies import get_current_user, requiere_rol, UsuarioActual",
    ),
)
print("[ventas import] OK")
