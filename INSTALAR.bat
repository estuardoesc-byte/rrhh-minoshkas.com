@echo off
rem Instalador de RRHH Minoshkas: doble clic y aceptar el permiso de administrador.
net session >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalacion\windows\instalar.ps1"
echo.
pause
