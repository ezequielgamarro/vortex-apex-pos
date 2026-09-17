@echo off
REM =====================================================================
REM  CONFIGURAR CLIENTE — doble clic para usar (al instalar el POS).
REM ---------------------------------------------------------------------
REM  Asigna el identificador del comercio a ESTA instalacion. Ejemplo:
REM    libreria-don-pedro
REM  Al terminar, te muestra la HUELLA de esta PC. Anotala en tu planilla.
REM
REM  Si haces doble clic sin escribir nada, te pedira el identificador.
REM =====================================================================
chcp 65001 >nul
cd /d "%~dp0"

set PY=app\.venv\Scripts\python.exe

if not exist "%PY%" (
  echo.
  echo   ERROR: no se encontro el entorno virtual en %PY%
  echo.
  pause
  exit /b 1
)

if "%~1"=="" (
  echo.
  set /p CID="  Escribi el identificador del cliente (ej: libreria-don-pedro): "
  echo.
  "%PY%" configurar_cliente.py "%CID%"
) else (
  "%PY%" configurar_cliente.py "%~1"
)

echo.
pause
