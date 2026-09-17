@echo off
REM =====================================================================
REM  GENERAR CLAVES (SOLO UNA VEZ EN LA VIDA) — doble clic para usar.
REM ---------------------------------------------------------------------
REM  ATENCION: Esto crea el par de llaves privada/publica del proveedor.
REM  Si lo volves a ejecutar, las licencias emitidas ANTES dejan de ser
REM  validas. NO lo hagas salvo que quieras empezar de cero.
REM
REM  Guarda el archivo vortex_private.key en un lugar SEGURO y con BACKUP.
REM =====================================================================
chcp 65001 >nul
cd /d "%~dp0.."

set PY=app\.venv\Scripts\python.exe

if not exist "%PY%" (
  echo.
  echo   ERROR: no se encontro el entorno virtual en %PY%
  echo.
  pause
  exit /b 1
)

echo   ADVERTENCIA: generar claves nuevas invalida las licencias anteriores.
echo   Escribi SI para continuar, o cerra esta ventana para cancelar.
echo.
"%PY%" tools_licencia\generar_claves.py

echo.
pause
