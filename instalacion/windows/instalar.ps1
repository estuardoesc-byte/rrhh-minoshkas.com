# Instalador de RRHH Minoshkas para Windows 10/11.
# Uso: clic derecho sobre este archivo > "Ejecutar con PowerShell" (como administrador).
# Es seguro correrlo de nuevo para actualizar la aplicación: no borra datos.

$ErrorActionPreference = "Stop"
$Destino = "C:\RRHH-Minoshkas"
$Datos = "$Destino\datos"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Paso($texto) { Write-Host "`n==> $texto" -ForegroundColor Magenta }

# 1. Python
Paso "Revisando Python"
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Instalando Python 3.12 con winget..."
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# 2. Copiar la aplicación (sin tocar la carpeta de datos)
Paso "Copiando la aplicación a $Destino"
New-Item -ItemType Directory -Force -Path $Destino, $Datos, "$Datos\documentos" | Out-Null
foreach ($carpeta in "app", "scripts", "instalacion") {
    robocopy "$Repo\$carpeta" "$Destino\$carpeta" /MIR /NFL /NDL /NJH /NJS | Out-Null
}
Copy-Item "$Repo\requirements.txt" $Destino -Force

# 3. Entorno de Python y dependencias
Paso "Instalando dependencias"
if (-not (Test-Path "$Destino\.venv")) { py -3 -m venv "$Destino\.venv" }
& "$Destino\.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& "$Destino\.venv\Scripts\python.exe" -m pip install -r "$Destino\requirements.txt" --quiet

# 4. Configuración (.env) con clave secreta propia; se crea solo la primera vez
$envFile = "$Destino\.env"
if (-not (Test-Path $envFile)) {
    Paso "Creando configuración"
    $bytes = New-Object byte[] 48; [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secreto = [Convert]::ToBase64String($bytes)
    @"
DATABASE_URL=sqlite:///$($Datos -replace '\\','/')/rrhh.db
UPLOAD_DIR=$Datos\documentos
SECRET_KEY=$secreto
HTTPS_ONLY=1
"@ | Set-Content -Encoding UTF8 $envFile
}

# 5. Patronos y sucursales
Paso "Cargando patronos y sucursales"
Push-Location $Destino
& "$Destino\.venv\Scripts\python.exe" -m scripts.cargar_base
Pop-Location

# 6. Arranque automático al encender la computadora
Paso "Programando el arranque automático"
$accion = New-ScheduledTaskAction -Execute "$Destino\.venv\Scripts\python.exe" `
    -Argument "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers" -WorkingDirectory $Destino
$disparador = New-ScheduledTaskTrigger -AtStartup
$config = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit 0 -StartWhenAvailable
Register-ScheduledTask -TaskName "RRHH Minoshkas" -Action $accion -Trigger $disparador -Settings $config `
    -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName "RRHH Minoshkas"

# 7. Respaldo diario a las 7 p. m. (si existe la carpeta de Google Drive)
$drive = Get-ChildItem "$env:USERPROFILE" -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -in "Mi unidad", "My Drive", "Google Drive" } | Select-Object -First 1
if (-not $drive) { $drive = Get-PSDrive -PSProvider FileSystem | ForEach-Object { Join-Path $_.Root "Mi unidad" } | Where-Object { Test-Path $_ } | Select-Object -First 1 }
if ($drive) {
    $carpetaRespaldo = Join-Path $drive "Respaldos RRHH Minoshkas"
    Paso "Programando respaldo diario en $carpetaRespaldo"
    $accionR = New-ScheduledTaskAction -Execute "$Destino\.venv\Scripts\python.exe" `
        -Argument "-m scripts.respaldar `"$carpetaRespaldo`"" -WorkingDirectory $Destino
    $diario = New-ScheduledTaskTrigger -Daily -At 7pm
    Register-ScheduledTask -TaskName "RRHH Minoshkas - respaldo" -Action $accionR -Trigger $diario `
        -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable) -Force | Out-Null
} else {
    Write-Host "No encontré Google Drive para escritorio. Instálalo y vuelve a correr este instalador para activar el respaldo diario." -ForegroundColor Yellow
}

Start-Sleep -Seconds 4
Paso "Listo"
Write-Host "La aplicación corre en http://localhost:8000 en esta computadora."
Write-Host "Ahora crea los usuarios con: crear-usuario.ps1"
Write-Host "Y sigue la guía PUBLICAR.md para la dirección rrhh.minoshkas.com."
