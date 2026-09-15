"""Dependencias de autenticación y autorización locales.

Seguridad 100% local para la aplicación de escritorio:
- Hashing de contraseñas con bcrypt (librería oficial, sin passlib).
  (`passlib` está sin mantenimiento y es incompatible con bcrypt >= 4.1).
- Emisión y verificación de JWT con python-jose (algorithm HS256).
- Protege las rutas de la API mediante `OAuth2PasswordBearer`.

No depende de ningún servicio externo (sin Supabase).
"""

import bcrypt
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Usuario

# --- Emisión de tokens JWT locales -------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Roles válidos del sistema
ROL_ADMIN = "admin"
ROL_CAJERO = "cajero"


@dataclass
class UsuarioActual:
    """Representa al usuario autenticado y su rol."""

    id: int
    email: str
    nombre: str
    rol: str


class AuthError(Exception):
    """Error de autenticación o autorización."""

    def __init__(self, detalle: str, status_code: int):
        super().__init__(detalle)
        self.detalle = detalle
        self.status_code = status_code


# ========================= UTILIDADES DE SEGURIDAD ==========================

# Cost factor bcrypt: 12 rondas es un balance razonable seguridad/CPU en una
# app de escritorio. Para contraseñas con más de 72 bytes, se trunca a 72
# (límite intrínseco del algoritmo bcrypt) antes de procesar.
_BCRYPT_ROUNDS = 12


def _encode(password: str) -> bytes:
    """Codifica la contraseña a bytes y la trunca al límite de bcrypt (72 bytes)."""
    raw = password.encode("utf-8")
    return raw[:72]


def verificar_password(password_plano: str, password_hash: str) -> bool:
    """Verifica una contraseña en texto plano contra su hash bcrypt.

    `bcrypt.checkpw` realiza la comparación con timing seguro.
    Se envuelve en try/except porque un hash malformado lanza ValueError;
    ante eso, la verificación debe fallar (False), nunca lanzar.
    """
    try:
        return bcrypt.checkpw(_encode(password_plano), password_hash.encode("utf-8"))
    except ValueError:
        return False


def hash_password(password_plano: str) -> str:
    """Genera el hash bcrypt de una contraseña en texto plano."""
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(_encode(password_plano), salt).decode("utf-8")


def crear_token_acceso(
    subject: str | int,
    rol: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Crea y firma un token JWT de acceso (HS256).

    Args:
        subject: identificador único del usuario (sub claim).
        rol: rol del usuario (se incluye como claim `rol`).
        expires_delta: duración del token; si es None se usa el valor de settings.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    # `sub` debe ser un valor serializable para el estándar JWT.
    if isinstance(subject, int):
        subject_str = str(subject)
    else:
        subject_str = subject

    to_encode = {
        "sub": subject_str,
        "rol": rol,
        "exp": expire,
    }
    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _decode_token(token: str) -> dict:
    """Decodifica y valida un JWT. Lanza `AuthError` si es inválido/expirado."""
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as exc:
        raise AuthError(
            "No se pudo validar las credenciales",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc


# ============================ DEPENDENCIAS ==================================


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UsuarioActual:
    """Dependencia: obtiene el usuario autenticado actual.

    Decodifica el JWT local, consulta la base de datos y devuelve el usuario
    autenticado. Usar en rutas que requieran cualquier usuario logueado.
    """
    credenciales = _decode_token(token)

    try:
        user_id = int(credenciales.get("sub"))
    except (TypeError, ValueError):
        raise AuthError(
            "Token inválido",
            status.HTTP_401_UNAUTHORIZED,
        )

    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if usuario is None:
        raise AuthError(
            "Usuario no encontrado",
            status.HTTP_401_UNAUTHORIZED,
        )
    if not usuario.activo:
        raise AuthError(
            "Usuario desactivado",
            status.HTTP_403_FORBIDDEN,
        )

    return UsuarioActual(
        id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre_completo,
        rol=usuario.rol,
    )


def requiere_rol(*roles: str) -> Callable:
    """Fábrica de dependencias que exige que el usuario tenga alguno de los roles.

    Uso:
        @router.get(...)
        def ruta(user: UsuarioActual = Depends(requiere_rol("admin"))):
            ...
    """
    roles_requeridos = set(roles)

    def _dependency(user: UsuarioActual = Depends(get_current_user)) -> UsuarioActual:
        if not roles_requeridos:
            return user
        if user.rol not in roles_requeridos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta acción.",
            )
        return user

    return _dependency


def get_current_admin(
    user: UsuarioActual = Depends(requiere_rol(ROL_ADMIN)),
) -> UsuarioActual:
    """Dependencia: exige que el usuario tenga rol 'admin'."""
    return user
