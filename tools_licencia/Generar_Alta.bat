@echo off
REM =====================================================================
REM  GENERAR CODIGO DE ALTA (uso del proveedor) - doble clic para usar.
REM ---------------------------------------------------------------------
REM  Aqui pegas la huella de la PC nueva y obtenes el codigo de alta del primer administrador.
REM
REM  IMPORTANTE: este archivo usa tu LLAVE PRIVADA. NO lo copies nunca a
REM  la PC de un cliente. Solo debe existir en tu maquina.
REM =====================================================================
chcp 65001 >nul
cd /d "%~dp0.."

set PY=app\.venv\Scripts\python.exe

if not exist "%PY%" (
  echo.
  echo   ERROR: no se encontro el entorno virtual en %PY%
  echo   Asegurate de ejecutar este archivo desde la carpeta del proyecto.
  echo.
  pause
  exit /b 1
)

"%PY%" tools_licencia\generar_alta.py

echo.
echo   (Podes cerrar esta ventana cuando termines.)
pause
