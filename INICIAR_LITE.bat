@echo off
setlocal
cd /d "%~dp0"
echo Iniciando SeybaPlaya Deslizamiento Lite...
echo.
py -3 -m slipform.server
if errorlevel 1 (
  echo.
  echo No se pudo iniciar con py -3. Revisa que Python este instalado.
  pause
)
