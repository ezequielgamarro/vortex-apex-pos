# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules


# El app.main se resuelve en runtime por "import string" desde uvicorn
# ("app.main:app"), así que recogemos manualmente todo el paquete `app` para
# que el exe lleve TODOS los routers/modelos/config (los imports dinámicos no
# los detecta el análisis estático de PyInstaller).
hiddenimports = collect_submodules('app') + [
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
datas = [('frontend', 'frontend')]

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
