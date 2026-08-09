@echo off
setlocal
title Control De Deslizamiento - Seybaplaya

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

set "PYTHON_EXE=%APP_DIR%runtime\python\python.exe"
if not exist "%PYTHON_EXE%" (
  echo.
  echo No se encontro Python portable en:
  echo %PYTHON_EXE%
  echo.
  echo El paquete esta incompleto. Solicita nuevamente el ZIP completo.
  pause
  exit /b 1
)

if not exist "%APP_DIR%launcher.py" (
  echo.
  echo No se encontro launcher.py en:
  echo %APP_DIR%
  echo.
  echo El paquete esta incompleto. Solicita nuevamente el ZIP completo.
  pause
  exit /b 1
)

if not exist "%APP_DIR%slipform" (
  echo.
  echo No se encontro la carpeta slipform.
  echo El paquete esta incompleto o no se descomprimio completo.
  pause
  exit /b 1
)

if not exist "%APP_DIR%static" (
  echo.
  echo No se encontro la carpeta static.
  echo El paquete esta incompleto o no se descomprimio completo.
  pause
  exit /b 1
)

if not exist "%APP_DIR%data" mkdir "%APP_DIR%data"
if not exist "%APP_DIR%data\backups" mkdir "%APP_DIR%data\backups"
if not exist "%APP_DIR%logs" mkdir "%APP_DIR%logs"

set "PYTHONPATH=%APP_DIR%"

echo.
echo ================================================================
echo  Control De Deslizamiento - Seybaplaya
echo ================================================================
echo.
echo  1. Se abrira el navegador cuando el servidor este listo.
echo  2. No cierres esta ventana mientras estes usando el programa.
echo  3. Si el puerto 8010 esta ocupado, se usara otro puerto disponible.
echo  4. Para terminar, cierra esta ventana.
echo.

"%PYTHON_EXE%" "%APP_DIR%launcher.py"

echo.
echo El programa se detuvo.
pause
