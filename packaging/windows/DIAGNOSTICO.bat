@echo off
setlocal
title Diagnostico - Control De Deslizamiento

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

set "PYTHON_EXE=%APP_DIR%runtime\python\python.exe"

echo.
echo ================================================================
echo  Diagnostico - Control De Deslizamiento
echo ================================================================
echo.

if not exist "%PYTHON_EXE%" (
  echo ERROR: No se encontro Python portable.
  echo Ruta esperada: %PYTHON_EXE%
  pause
  exit /b 1
)

if not exist "%APP_DIR%launcher.py" (
  echo ERROR: No se encontro launcher.py.
  pause
  exit /b 1
)

"%PYTHON_EXE%" "%APP_DIR%launcher.py" --check
set "STATUS=%ERRORLEVEL%"

echo.
if "%STATUS%"=="0" (
  echo Diagnostico correcto. Puedes abrir INICIAR_PROGRAMA.bat.
) else (
  echo El diagnostico encontro un problema.
  echo Revisa la carpeta logs y comparte el archivo mas reciente.
)
echo.
pause
exit /b %STATUS%
