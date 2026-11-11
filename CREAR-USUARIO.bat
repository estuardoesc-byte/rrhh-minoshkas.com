@echo off
rem Crea o cambia la contraseña de un usuario de RRHH Minoshkas.
net session >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalacion\windows\crear-usuario.ps1"
