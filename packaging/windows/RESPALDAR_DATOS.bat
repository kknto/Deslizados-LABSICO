@echo off
setlocal
title Respaldar Datos - Control De Deslizamiento

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

if not exist "%APP_DIR%data\slipform.sqlite" (
  echo.
  echo No se encontro la base de datos:
  echo %APP_DIR%data\slipform.sqlite
  echo.
  echo Abre primero el programa o revisa que el paquete este completo.
  pause
  exit /b 1
)

if not exist "%APP_DIR%data\backups" mkdir "%APP_DIR%data\backups"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
set "TARGET=%APP_DIR%data\backups\slipform_respaldo_manual_%STAMP%.sqlite"

copy "%APP_DIR%data\slipform.sqlite" "%TARGET%" > nul
if errorlevel 1 (
  echo.
  echo No se pudo crear el respaldo.
  pause
  exit /b 1
)

echo.
echo Respaldo creado correctamente:
echo %TARGET%
echo.
pause
