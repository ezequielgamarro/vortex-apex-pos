"""Router de autenticación y gestión de perfiles.

Autenticación 100% local:
- POST /auth/login: emite el JWT local tras validar credenciales.
- Verificación de token/selección de usuario delegada a `app.dependencies`.

Usuarios persistidos en SQLite (tabla `usuarios`).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    crear_token_acceso,
    hash_password,
    verificar_password,
    get_current_user,
    requiere_rol,
    es_superadmin,
    email_superadmin,
    UsuarioActual,
)
from app.models import Usuario

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# Rubros válidos del sistema (multi-rubro). Single Source of Truth para la
# validación del rubro que solo el SuperAdmin puede fijar. Cualquier valor
# fuera de esta lista se normaliza a 'general'.
RUBROS_VALIDOS = (
    "general",
    "panaderia_alimentos",
    "indumentaria",
    "ferreteria",
    "libreria",
)
RUBRO_DEFAULT = "general"


def _normalizar_rubro(valor: str | None) -> str:
    """Devuelve un rubro válido o el por defecto si el valor es inválido/vacío."""
    limpio = (valor or "").strip().lower()
    return limpio if limpio in RUBROS_VALIDOS else RUBRO_DEFAULT


class TokenRespuesta(BaseModel):
    """Estructura de respuesta del login."""

    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """Payload del alta de usuario (registro público/local)."""

    nombre: str = Field(..., min_length=1, max_length=255)
    email: str
    password: str = Field(..., min_length=6)

    _normalizar_email = validator("email", allow_reuse=True)(
        lambda v: v.strip().lower()
    )


class AdminCrearUsuario(BaseModel):
    """Payload para crear un usuario desde la gestión del admin (con rol)."""

    nombre: str = Field(..., min_length=1, max_length=255)
    email: str
    password: str = Field(...)
    rol: str = Field("cajero", description="'admin' | 'cajero'")
    # Rubro del negocio. SOLO lo respeta el backend cuando quien crea el usuario
    # es el SuperAdministrador (ver `crear_usuario_admin`). Para un admin
    # estándar el valor se IGNORA y se hereda el rubro del comercio (el del
    # SuperAdmin). Por eso aquí basta con un valor por defecto seguro.
    rubro: str = Field("general", max_length=40)

    # Mini-validador local (repetido por claridad; no hereda de RegisterRequest).
    _normalizar_email = validator("email", allow_reuse=True)(
        lambda v: v.strip().lower()
    )


@router.post(
    "/register",
    response_model=TokenRespuesta,
    summary="Registrar un nuevo usuario (rol cajero por defecto)",
)
def registrar_usuario(
    data: RegisterRequest,
    db: Session = Depends(get_db),
):
    """Crea un usuario nuevo en SQLite y devuelve un token para iniciar sesión.

    Reglas:
      - El email debe ser único (rechaza duplicados con 409).
      - El rol asignado por defecto es 'cajero' (nunca 'admin').
      - El usuario se crea activo; un admin puede gestionar rol/estado después.
    """
    email = data.email.strip().lower()
    existe = db.query(Usuario).filter(Usuario.email == email).first()
    if existe is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese correo electrónico",
        )

    usuario = Usuario(
        email=email,
        nombre_completo=data.nombre.strip(),
        password_hash=hash_password(data.password),
        rol="cajero",
        activo=True,
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese correo electrónico",
        )
    db.refresh(usuario)

    token = crear_token_acceso(subject=usuario.id, rol=usuario.rol)
    return TokenRespuesta(access_token=token)


@router.post("/login", response_model=TokenRespuesta, summary="Iniciar sesión")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Autentica un usuario local y devuelve un token JWT.

    El body esperado es `application/x-www-form-urlencoded` con los campos
    `username` y `password` (formato OAuth2 estándar).
    """
    usuario = db.query(Usuario).filter(Usuario.email == form_data.username).first()
    if usuario is None or not verificar_password(
        form_data.password, usuario.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado",
        )

    token = crear_token_acceso(subject=usuario.id, rol=usuario.rol)
    return TokenRespuesta(access_token=token)


@router.get("/perfil", summary="Perfil del usuario actual")
def obtener_perfil(
    usuario: UsuarioActual = Depends(get_current_user),
):
    """Devuelve la información del usuario autenticado (id, email, nombre, rol).

    Útil para que el frontend conozca el rol y adapte la interfaz.

    Incluye `es_superadmin`: bandera AUTORITATIVA calculada en el backend que
    indica si el usuario es el SuperAdministrador de la instalación. El
    frontend la usa para decidir si muestra el selector de "rubro" (solo el
    SuperAdmin puede elegirlo); así el criterio vive en un único lugar y no se
    duplica como magic string en el cliente.
    """
    # El rubro depende de la fila completa; `UsuarioActual` no lo trae, así
    # que se consulta la BD para exponerlo en el perfil de display.
    from app.database import SessionLocal  # noqa: PLC0415

    _db = SessionLocal()
    try:
        u = _db.query(Usuario).filter(Usuario.id == usuario.id).first()
        rubro = (u.rubro if u is not None else None) or "general"
    finally:
        _db.close()
    return {
        "id": usuario.id,
        "email": usuario.email,
        "nombre": usuario.nombre,
        "rol": usuario.rol,
        "rubro": rubro,
        "es_superadmin": es_superadmin(usuario.email),
    }


@router.get("/usuarios", summary="Listar usuarios del sistema (solo admin)")
def listar_usuarios(
    db: Session = Depends(get_db),
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
):
    """Devuelve todos los usuarios registrados. Solo accesible para administradores.

    PRIVACIDAD DEL SUPERADMIN: la cuenta del SuperAdministrador
    (`admin@pos.local`) se EXCLUYE del listado cuando quien consulta es un
    administrador estándar. Solo el propio SuperAdmin ve su fila. Así el dueño
    de la instalación opera sin exponerse a los administradores del comercio.
    """
    consulta = db.query(Usuario).order_by(Usuario.nombre_completo)
    if not es_superadmin(usuario.email):
        consulta = consulta.filter(Usuario.email != email_superadmin())
    usuarios = consulta.all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "nombre_completo": u.nombre_completo,
            "rol": u.rol,
            "rubro": u.rubro,
            "activo": u.activo,
            "creado_en": u.creado_en,
            "es_superadmin": es_superadmin(u.email),
        }
        for u in usuarios
    ]


@router.patch(
    "/usuarios/{user_id}/rol", summary="Cambiar rol de un usuario (solo admin)"
)
def cambiar_rol(
    user_id: int,
    rol: str,
    db: Session = Depends(get_db),
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
):
    """Actualiza el rol de un usuario. Solo accesible para administradores.

    `rol` debe ser 'admin' o 'cajero'.
    """
    if rol not in ("admin", "cajero"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rol inválido. Debe ser 'admin' o 'cajero'.",
        )
    target = db.query(Usuario).filter(Usuario.id == user_id).first()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    # BLINDAJE DEL SUPERADMIN: el objetivo no puede ser tocado por un admin
    # estándar. Evita que un administrador del comercio degrade o altere la
    # cuenta de la autoridad de la instalación.
    if es_superadmin(target.email) and not es_superadmin(usuario.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para modificar al SuperAdministrador.",
        )
    # El SuperAdmin no puede degradarse a sí mismo (perdería el control total).
    if target.id == usuario.id and es_superadmin(usuario.email) and rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El SuperAdministrador no puede quitarse su propio rol.",
        )
    target.rol = rol
    db.commit()
    db.refresh(target)
    return {
        "id": target.id,
        "email": target.email,
        "rol": target.rol,
    }


@router.post(
    "/usuarios",
    summary="Crear un usuario con rol (solo admin)",
    status_code=status.HTTP_201_CREATED,
)
def crear_usuario_admin(
    data: AdminCrearUsuario,
    db: Session = Depends(get_db),
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
):
    """Crea un nuevo usuario asignándole el rol que el admin elija.

    - email único (409 si ya existe)
    - rol válido: 'admin' o 'cajero'
    - el usuario se crea siempre activo
    """
    rol = data.rol.strip().lower()
    if rol not in ("admin", "cajero"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rol inválido. Debe ser 'admin' o 'cajero'.",
        )
    if len(data.password or "") < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe tener al menos 6 caracteres.",
        )

    email = data.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ingresa un correo electrónico válido.",
        )

    existe = db.query(Usuario).filter(Usuario.email == email).first()
    if existe is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese correo electrónico.",
        )

    # --- RUBRO (autorización por identidad) ---------------------------------
    # REGLA DE NEGOCIO: solo el SuperAdministrador puede elegir el rubro de un
    # usuario. Un administrador estándar NO puede fijarlo: sus usuarios heredan
    # el rubro del COMERCIO (el rubro del SuperAdmin en BD), garantizando la
    # coherencia multi-rubro de la instalación.
    #
    # La verificación se hace contra el email AUTORITATIVO de la BD
    # (`usuario.email`, proveniente de `get_current_user`), nunca contra el
    # payload. Un admin estándar que envíe `rubro` en el body es IGNORADO.
    if es_superadmin(usuario.email):
        rubro = _normalizar_rubro(data.rubro)
    else:
        admin_comercio = (
            db.query(Usuario).filter(Usuario.email == email_superadmin()).first()
        )
        rubro = _normalizar_rubro(
            admin_comercio.rubro if admin_comercio is not None else None
        )

    nuevo = Usuario(
        email=email,
        nombre_completo=data.nombre.strip(),
        password_hash=hash_password(data.password),
        rol=rol,
        rubro=rubro,
        activo=True,
    )
    db.add(nuevo)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese correo electrónico.",
        )
    db.refresh(nuevo)
    return {
        "id": nuevo.id,
        "email": nuevo.email,
        "nombre_completo": nuevo.nombre_completo,
        "rol": nuevo.rol,
        "rubro": nuevo.rubro,
        "activo": nuevo.activo,
        "creado_en": nuevo.creado_en,
    }


@router.patch(
    "/usuarios/{user_id}/estado",
    summary="Activar o desactivar un usuario (solo admin)",
)
def cambiar_estado_usuario(
    user_id: int,
    activo: bool,
    db: Session = Depends(get_db),
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
):
    """Habilita (`activo=true`) o deshabilita (`activo=false`) un usuario.

    Regla de seguridad: un admin no puede desactivarse a sí mismo (si no,
    se quedaría fuera del sistema sin saberlo).
    """
    target = db.query(Usuario).filter(Usuario.id == user_id).first()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    # BLINDAJE DEL SUPERADMIN: un admin estándar no puede desactivar la cuenta
    # de la autoridad de la instalación.
    if es_superadmin(target.email) and not es_superadmin(usuario.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para modificar al SuperAdministrador.",
        )
    if target.id == usuario.id and not activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta.",
        )
    target.activo = bool(activo)
    db.commit()
    db.refresh(target)
    return {
        "id": target.id,
        "email": target.email,
        "activo": target.activo,
    }
