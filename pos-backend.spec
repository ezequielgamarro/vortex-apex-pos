# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

# Validar que los estilos de Tailwind existan antes de empaquetar
css_dist = Path('frontend') / 'dist' / 'css' / 'app.css'
if not css_dist.exists():
    raise SystemExit(
        f"\n[ERROR BUILD] No se encontró el archivo de estilos: '{css_dist}'.\n"
        "Debes compilar los estilos de Tailwind antes de empaquetar con PyInstaller.\n"
        "Ejecuta: npm run build:css\n"
    )

# El app.main se resuelve en runtime por "import string" desde uvicorn
# ("app.main:app"), así que recogemos manualmente todo el paquete `app` para
# que el exe lleve TODOS los routers/modelos/config (los imports dinámicos no
# los detecta el análisis estático de PyInstaller).
hiddenimports = collect_submodules('app') + collect_submodules('alembic') + [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
]

# La UI estática (frontend/*) debe ir ADENTRO del ejecutable para servirse por su
# cuenta. PyInstaller la extrae a sys._MEIPASS (ver app.main:_ruta_frontend).
# Recopilamos todos los archivos del frontend excluyendo 'node_modules' y logs
# para evitar inflar el ejecutable y optimizar los tiempos de arranque.
datas = []
frontend_dir = Path('frontend')
for root, dirs, files in os.walk(frontend_dir):
    if 'node_modules' in dirs:
        dirs.remove('node_modules')
    for f in files:
        if f.endswith('.log'):
            continue
        src = Path(root) / f
        rel = src.relative_to(frontend_dir)
        dest = Path('frontend') / rel.parent
        datas.append((str(src), str(dest)))

# Mapeo explícito de la carpeta dist compilada (('frontend/dist', 'dist'))
# para garantizar resolución tanto en /dist como en /frontend/dist
datas.append(('frontend/dist', 'dist'))

# ---------------------------------------------------------------------------
# LLAVE PÚBLICA DE LICENCIAS (CRÍTICO)
# ---------------------------------------------------------------------------
# El POS necesita `app/licencia_public.key` para VERIFICAR los códigos firmados
# (ver app/services/licencia_firma.cargar_llave_publica). Sin ella, la activación
# falla por fail-secure. En PyInstaller onefile, `__file__` de
# app/services/licencia_firma.py resuelve a sys._MEIPASS/app/services/... y
# cargar_llave_publica busca en `parent.parent` = sys._MEIPASS/app. Por eso el
# archivo se empaqueta con destino 'app'.
licencia_pub = Path('app') / 'licencia_public.key'
if not licencia_pub.exists():
    raise SystemExit(
        f"\n[ERROR BUILD] No se encontró la llave pública: '{licencia_pub}'.\n"
        "Es necesaria para verificar licencias. Copiala desde tools_licencia/.\n"
    )
datas.append((str(licencia_pub), 'app'))

# Migraciones de Alembic: se cargan como ARCHIVOS (no son un paquete importable).
datas.append(('app/migraciones', 'app/migraciones'))

# ---------------------------------------------------------------------------
# GUARDA DE SEGURIDAD: la LLAVE PRIVADA nunca debe empaquetarse
# ---------------------------------------------------------------------------
# `tools_licencia/` contiene vortex_private.key (la llave del PROVEEDOR). Si esa
# llave se filtra dentro del .exe, cualquiera podría firmar licencias válidas.
# Esta guarda ABORTA la compilación si detecta que la privada o la carpeta de
# herramientas entraron al bundle (datas o binaries). Es defensa en profundidad:
# aunque hoy solo se recorre 'frontend/', protege ante cambios futuros.
_PROHIBIDOS = ('vortex_private.key', 'tools_licencia')
def _contiene_privada(coleccion):
    for tupla in coleccion:
        for parte in tupla:
            if isinstance(parte, str) and any(p in parte for p in _PROHIBIDOS):
                return True
    return False

if _contiene_privada(datas):
    raise SystemExit(
        "\n[ERROR BUILD] SEGURIDAD: se detectó 'tools_licencia/' o la llave "
        "privada dentro de los datos a empaquetar. La llave privada NUNCA debe "
        "incluirse en el .exe del cliente. Abortando compilación.\n"
    )

a = Analysis(
    ['app/server.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='pos-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
