"""Módulo 1 — Backend multi-rubro en auth.py.

  * AdminCrearUsuario: acepta `rubro` (opcional) -> propaga el rubro a los
    usuarios creados. Si no se indica, hereda el rubro del admin creador.
  * /perfil: expone `rubro` para que el frontend adapte la UI.
  * listar_usuarios / crear_usuario_admin: devuelven y persisten `rubro`.
"""
from tools_upgrade.patcher import apply

A = "app/routers/auth.py"

RUBRO_VALIDOS = "general|panaderia_alimentos|indumentaria|ferreteria|libreria"

# 1) AdminCrearUsuario: campo rubro.
apply(
    A,
    (
        'class AdminCrearUsuario(BaseModel):\n'
        '    """Payload para crear un usuario desde la gestión del admin (con rol)."""\n'
        "\n"
        "    nombre: str = Field(..., min_length=1, max_length=255)\n"
        "    email: str\n"
        "    password: str = Field(...)\n"
        '    rol: str = Field("cajero", description="\'admin\' | \'cajero\'")',
        'class AdminCrearUsuario(BaseModel):\n'
        '    """Payload para crear un usuario desde la gestión del admin (con rol)."""\n'
        "\n"
        "    nombre: str = Field(..., min_length=1, max_length=255)\n"
        "    email: str\n"
        "    password: str = Field(...)\n"
        '    rol: str = Field("cajero", description="\'admin\' | \'cajero\'")\n'
        "    # Rubro del negocio. Si vacío, el backend lo hereda del admin creador.\n"
        '    rubro: str = Field("", max_length=40)',
    ),
)

# 2) /perfil expone rubro.
apply(
    A,
    (
        '    return {\n'
        '        "id": usuario.id,\n'
        '        "email": usuario.email,\n'
        '        "nombre": usuario.nombre,\n'
        '        "rol": usuario.rol,\n'
        "    }",
        '    # El rubro depende de la fila completa; `UsuarioActual` no lo trae, así\n'
        "    # que se consulta la BD para exponerlo en el perfil de display.\n"
        "    from app.database import SessionLocal  # noqa: PLC0415\n"
        "\n"
        "    _db = SessionLocal()\n"
        "    try:\n"
        "        u = _db.query(Usuario).filter(Usuario.id == usuario.id).first()\n"
        "        rubro = (u.rubro if u is not None else None) or 'general'\n"
        "    finally:\n"
        "        _db.close()\n"
        "    return {\n"
        '        "id": usuario.id,\n'
        '        "email": usuario.email,\n'
        '        "nombre": usuario.nombre,\n'
        '        "rol": usuario.rol,\n'
        '        "rubro": rubro,\n'
        "    }",
    ),
)

# 3) listar_usuarios incluye rubro.
apply(
    A,
    (
        '            "rol": u.rol,\n'
        '            "activo": u.activo,\n'
        '            "creado_en": u.creado_en,\n'
        "        }\n"
        "        for u in usuarios\n"
        "    ]",
        '            "rol": u.rol,\n'
        '            "rubro": u.rubro,\n'
        '            "activo": u.activo,\n'
        '            "creado_en": u.creado_en,\n'
        "        }\n"
        "        for u in usuarios\n"
        "    ]",
    ),
)

# 4) crear_usuario_admin: valida y hereda rubro.
apply(
    A,
    (
        "    existe = db.query(Usuario).filter(Usuario.email == email).first()\n"
        "    if existe is not None:\n"
        "        raise HTTPException(\n"
        "            status_code=status.HTTP_409_CONFLICT,\n"
        '            detail="Ya existe un usuario con ese correo electrónico.",\n'
        "        )\n"
        "\n"
        "    nuevo = Usuario(\n"
        "        email=email,\n"
        "        nombre_completo=data.nombre.strip(),\n"
        "        password_hash=hash_password(data.password),\n"
        "        rol=rol,\n"
        "        activo=True,\n"
        "    )",
        "    existe = db.query(Usuario).filter(Usuario.email == email).first()\n"
        "    if existe is not None:\n"
        "        raise HTTPException(\n"
        "            status_code=status.HTTP_409_CONFLICT,\n"
        '            detail="Ya existe un usuario con ese correo electrónico.",\n'
        "        )\n"
        "\n"
        "    # Rubro: el indicado o, por defecto, el del admin creador (herencia).\n"
        f"    rubros_validos = \"{RUBRO_VALIDOS}\".split(\"|\")\n"
        "    rubro = (data.rubro or \"\").strip()\n"
        "    if not rubro:\n"
        "        admin = db.query(Usuario).filter(Usuario.id == usuario.id).first()\n"
        "        rubro = (admin.rubro if admin is not None else None) or \"general\"\n"
        "    if rubro not in rubros_validos:\n"
        "        rubro = \"general\"\n"
        "\n"
        "    nuevo = Usuario(\n"
        "        email=email,\n"
        "        nombre_completo=data.nombre.strip(),\n"
        "        password_hash=hash_password(data.password),\n"
        "        rol=rol,\n"
        "        rubro=rubro,\n"
        "        activo=True,\n"
        "    )",
    ),
)

# 5) Respuesta de crear_usuario_admin incluye rubro.
apply(
    A,
    (
        '    return {\n'
        '        "id": nuevo.id,\n'
        '        "email": nuevo.email,\n'
        '        "nombre_completo": nuevo.nombre_completo,\n'
        '        "rol": nuevo.rol,\n'
        '        "activo": nuevo.activo,\n'
        '        "creado_en": nuevo.creado_en,\n'
        "    }",
        '    return {\n'
        '        "id": nuevo.id,\n'
        '        "email": nuevo.email,\n'
        '        "nombre_completo": nuevo.nombre_completo,\n'
        '        "rol": nuevo.rol,\n'
        '        "rubro": nuevo.rubro,\n'
        '        "activo": nuevo.activo,\n'
        '        "creado_en": nuevo.creado_en,\n'
        "    }",
    ),
)

print("[auth rubro] OK")
