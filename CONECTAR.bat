@echo off
rem Conecta esta computadora a RRHH Minoshkas: doble clic y aceptar el permiso.
net session >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
if exist "%~dp0conectar.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0conectar.ps1"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalacion\windows\conectar.ps1"
)
echo.
pause
