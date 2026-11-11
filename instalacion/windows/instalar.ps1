# Instalador de RRHH Minoshkas para Windows 10/11.
# Uso: doble clic en INSTALAR.bat (en la carpeta principal). Pide permiso de administrador.
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

# 8. Tailscale: red privada para entrar desde los equipos de los administradores.
#    No toca el dominio, GoDaddy, Google ni el router.
Paso "Instalando Tailscale (red privada)"
$ts = "$env:ProgramFiles\Tailscale\tailscale.exe"
if (-not (Test-Path $ts)) {
    winget install -e --id Tailscale.Tailscale --accept-package-agreements --accept-source-agreements
    Start-Sleep -Seconds 8
}

# Corre un comando de tailscale y, si pide entrar o autorizar algo, abre el navegador solo.
function Tailscale-ConNavegador([string[]]$argumentos, [string]$mensaje) {
    $out = Join-Path $env:TEMP "rrhh-ts-out.txt"; $err = Join-Path $env:TEMP "rrhh-ts-err.txt"
    Remove-Item $out, $err -ErrorAction SilentlyContinue
    $p = Start-Process $ts -ArgumentList $argumentos -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    $abierto = $false
    while (-not $p.HasExited) {
        $texto = ((Get-Content $out, $err -Raw -ErrorAction SilentlyContinue) -join "`n")
        if (-not $abierto -and $texto -match 'https://login\.tailscale\.com/\S+') {
            Write-Host $mensaje -ForegroundColor Yellow
            Start-Process $Matches[0]
            $abierto = $true
        }
        Start-Sleep -Seconds 2
    }
}

$estado = (& $ts status --json 2>$null | ConvertFrom-Json)
if (-not $estado -or $estado.BackendState -ne "Running") {
    Tailscale-ConNavegador @("up", "--unattended") `
        "Se abrió el navegador: elige 'Sign in with Google' y entra con esantacruz@minoshkas.com. Luego regresa a esta ventana."
}

Paso "Publicando la aplicación dentro de la red privada (con candado HTTPS)"
Tailscale-ConNavegador @("serve", "--bg", "8000") `
    "Se abrió el navegador: presiona 'Enable' para permitir HTTPS en tu red. Luego regresa a esta ventana."

$nombre = ((& $ts status --json | ConvertFrom-Json).Self.DNSName).TrimEnd(".")
$url = "https://$nombre"
Set-Content -Encoding UTF8 "$Destino\direccion.txt" $url
@"
[InternetShortcut]
URL=$url
"@ | Set-Content -Encoding ASCII "$env:PUBLIC\Desktop\RRHH Minoshkas.url"

# 9. Usuarios administradores
Start-Sleep -Seconds 3
Paso "Usuarios de la aplicación"
Write-Host "Crea los usuarios (Sandra Marquez, Julio Santa Cruz, Estuardo). Deja el nombre vacío para terminar."
Push-Location $Destino
while ($true) {
    $n = Read-Host "Nombre completo (Enter para terminar)"
    if ([string]::IsNullOrWhiteSpace($n)) { break }
    $c = Read-Host "Correo"
    & "$Destino\.venv\Scripts\python.exe" -m scripts.crear_usuario $n $c
}
Pop-Location

Paso "Listo"
Write-Host "Dirección de RRHH: $url" -ForegroundColor Green
Write-Host "Quedó un acceso directo 'RRHH Minoshkas' en el Escritorio."
Write-Host "Para entrar desde otro celular o computadora: instala la app Tailscale, entra con la invitación y abre esa dirección."
