"""Asistente de primer arranque: alta del primer administrador de un comercio.

PROBLEMA QUE RESUELVE
  El programa es 100 % local y el proveedor necesita poder dar de alta a cada
  cliente sin dejar una cuenta con contraseña conocida en todas las
  instalaciones. La autoridad del proveedor es su llave privada Ed25519 (la misma
  de las licencias), no una cuenta dentro de la base.

FLUJO
  1. La instalación nueva arranca SIN usuarios.
  2. La pantalla `setup.html` muestra la huella de la PC.
  3. El proveedor (presencial o por WhatsApp) firma un CÓDIGO DE ALTA para esa
     huella (`tools_licencia/generar_alta.py`).
  4. El cliente pega el código y elige el nombre, el correo y la contraseña de su
     administrador. Desde ahí el administrador crea cajeros u otros
     administradores con `POST /auth/usuarios`.

SEGURIDAD
  - Solo funciona mientras no exista NINGÚN usuario; después responde 409.
  - Sin código válido (firma Ed25519 + huella de esta PC) no se crea nada.
  - Si falta la llave pública, falla cerrado (503).
"""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import crear_token_acceso, hash_password
from app.models import Licencia, Usuario, now_utc
from app.routers.auth import TokenRespuesta, _normalizar_rubro
from app.services.licencia_firma import (
    LlavePublicaNoDisponible,
    calcular_huella,
    verificar_alta_para_maquina,
    verificar_recuperacion_para_maquina,
)
from app.services.licencia_service import _get_o_crear
from app.services.login_guard import LoginGuard, login_guard

router = APIRouter(prefix="/setup", tags=["Primer arranque"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PASSWORD_MIN = 8
# Mismo formato que valida configurar_cliente.py.
_CLIENTE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,118}[a-z0-9]$")
# Límite de intentos de recuperación (una sola clave global: no hay usuario aún).
_guardia_recuperacion = LoginGuard()
_CLAVE_RECUPERACION = "recuperacion"


class SetupEstadoOut(BaseModel):
    """Estado del primer arranque (público: no contiene datos sensibles)."""

    necesita_setup: bool
    # La huella no es secreta: sin la firma del proveedor no activa nada.
    huella: str | None = None


class SetupIn(BaseModel):
    codigo_alta: str = Field(..., min_length=10, max_length=1000)
    nombre: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=_PASSWORD_MIN, max_length=128)


def _sin_usuarios(db: Session) -> bool:
    return (db.query(func.count(Usuario.id)).scalar() or 0) == 0


def _cliente_id_actual(db: Session) -> str:
    lic = db.query(Licencia).first()
    return lic.cliente_id if lic and lic.cliente_id else "demo"


@router.get("/estado", response_model=SetupEstadoOut, summary="¿Falta el alta inicial?")
def estado_setup(db: Session = Depends(get_db)):
    """Indica si la instalación está vacía y devuelve la huella para el alta."""
    if not _sin_usuarios(db):
        return SetupEstadoOut(necesita_setup=False)
    return SetupEstadoOut(
        necesita_setup=True, huella=calcular_huella(_cliente_id_actual(db))
    )


@router.post(
    "/inicializar",
    response_model=TokenRespuesta,
    summary="Crear el primer administrador con un código de alta firmado",
)
def inicializar(data: SetupIn, db: Session = Depends(get_db)):
    if not _sin_usuarios(db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta instalación ya fue configurada.",
        )

    email = data.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ingresa un correo electrónico válido.",
        )

    try:
        resultado = verificar_alta_para_maquina(
            data.codigo_alta, _cliente_id_actual(db)
        )
    except LlavePublicaNoDisponible:
        # Fail-secure: sin llave pública no se puede verificar nada.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Esta instalación no tiene la llave de verificación del "
                "proveedor. Contactá al soporte para completar la instalación."
            ),
        )
    if not resultado.valido:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Código de alta rechazado: {resultado.motivo}",
        )

    # Instalación REMOTA: el proveedor puede fijar el identificador del comercio
    # dentro del código (no hace falta correr configurar_cliente.py).
    if resultado.cliente_id:
        if not _CLIENTE_ID_RE.match(resultado.cliente_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Código de alta rechazado: el identificador del comercio no es válido.",
            )
        lic = _get_o_crear(db)
        lic.cliente_id = resultado.cliente_id
        lic.actualizado_en = now_utc()

    usuario = Usuario(
        email=email,
        nombre_completo=data.nombre.strip(),
        password_hash=hash_password(data.password),
        rol="admin",
        # El rubro lo fija el proveedor dentro del código firmado.
        rubro=_normalizar_rubro(resultado.rubro),
        activo=True,
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta instalación ya fue configurada.",
        )
    db.refresh(usuario)

    return TokenRespuesta(
        access_token=crear_token_acceso(subject=usuario.id, rol=usuario.rol)
    )


# ---------------------------------------------------------------------------
# Recuperación de contraseña del administrador (código firmado por el proveedor)
# ---------------------------------------------------------------------------
class HuellaOut(BaseModel):
    huella: str


class RecuperarIn(BaseModel):
    codigo: str = Field(..., min_length=10, max_length=1000)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=_PASSWORD_MIN, max_length=128)


@router.get(
    "/huella",
    response_model=HuellaOut,
    summary="Huella de esta PC (para pedir un código de recuperación)",
)
def huella_publica(db: Session = Depends(get_db)):
    """Huella no secreta: sin la firma del proveedor no sirve para nada."""
    return HuellaOut(huella=calcular_huella(_cliente_id_actual(db)))


@router.post(
    "/recuperar",
    summary="Poner una contraseña nueva a un administrador con un código firmado",
)
def recuperar_contrasena(data: RecuperarIn, db: Session = Depends(get_db)):
    """Flujo para un administrador que olvidó su contraseña (cliente remoto).

    El cliente le manda su huella al proveedor; este devuelve un código `VXR`
    firmado, atado a esa PC, con vencimiento y de un solo uso. Sin el código no
    se cambia nada.
    """
    espera = _guardia_recuperacion.segundos_bloqueado(_CLAVE_RECUPERACION)
    if espera:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos. Probá de nuevo en {(espera + 59) // 60} minuto(s).",
            headers={"Retry-After": str(espera)},
        )

    def rechazar(detalle: str, codigo: int = status.HTTP_400_BAD_REQUEST):
        _guardia_recuperacion.registrar_fallo(_CLAVE_RECUPERACION)
        raise HTTPException(status_code=codigo, detail=detalle)

    email = data.email.strip().lower()
    if not _EMAIL_RE.match(email):
        rechazar("Ingresa un correo electrónico válido.")

    try:
        res = verificar_recuperacion_para_maquina(
            data.codigo, _cliente_id_actual(db)
        )
    except LlavePublicaNoDisponible:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Esta instalación no tiene la llave de verificación del "
                "proveedor. Contactá al soporte."
            ),
        )
    if not res.valido:
        rechazar(f"Código de recuperación rechazado: {res.motivo}")
    if res.vence < now_utc().date():
        rechazar("El código de recuperación venció. Pedí uno nuevo.")

    lic = _get_o_crear(db)
    if res.serie <= int(lic.ultimo_serial_rec or 0):
        rechazar("Ese código ya se usó o es más viejo que el último aplicado.")
    if res.email and res.email != email:
        rechazar("El código no corresponde a ese usuario.")

    usuario = db.query(Usuario).filter(Usuario.email == email).first()
    # Solo cuentas de administrador, y sin revelar si el correo existe.
    if usuario is None or usuario.rol != "admin":
        rechazar("No se pudo aplicar el código para ese usuario.")

    usuario.password_hash = hash_password(data.password)
    usuario.activo = True
    lic.ultimo_serial_rec = res.serie
    db.commit()

    # Si estaba bloqueado por intentos fallidos, queda libre.
    _guardia_recuperacion.registrar_exito(_CLAVE_RECUPERACION)
    login_guard.registrar_exito(login_guard.clave(email))
    return {"ok": True}
