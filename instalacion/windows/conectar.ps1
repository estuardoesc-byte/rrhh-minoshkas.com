# Conecta esta computadora a RRHH Minoshkas (la aplicación sigue corriendo en la PC de la oficina).
# Uso: doble clic en CONECTAR.bat. Antes, el administrador debe invitar tu correo en Tailscale.
$ErrorActionPreference = "Stop"
function Paso($texto) { Write-Host "`n==> $texto" -ForegroundColor Magenta }

$archivoUrl = Join-Path $PSScriptRoot "direccion.txt"
if (Test-Path $archivoUrl) { $url = (Get-Content $archivoUrl -Raw).Trim() }
if (-not $url) { $url = (Read-Host "Dirección de RRHH (la que termina en .ts.net)").Trim() }

Paso "Instalando Tailscale (red privada)"
$ts = "$env:ProgramFiles\Tailscale\tailscale.exe"
if (-not (Test-Path $ts)) {
    winget install -e --id Tailscale.Tailscale --accept-package-agreements --accept-source-agreements
    Start-Sleep -Seconds 8
}

$estado = (& $ts status --json 2>$null | ConvertFrom-Json)
if (-not $estado -or $estado.BackendState -ne "Running") {
    Paso "Entrando a la red privada"
    $out = Join-Path $env:TEMP "rrhh-ts-out.txt"; $err = Join-Path $env:TEMP "rrhh-ts-err.txt"
    Remove-Item $out, $err -ErrorAction SilentlyContinue
    $p = Start-Process $ts -ArgumentList "up" -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    $abierto = $false
    while (-not $p.HasExited) {
        $texto = ((Get-Content $out, $err -Raw -ErrorAction SilentlyContinue) -join "`n")
        if (-not $abierto -and $texto -match 'https://login\.tailscale\.com/\S+') {
            Write-Host "Se abrió el navegador: entra con TU correo (el que invitaron) y presiona Connect. Luego regresa aquí." -ForegroundColor Yellow
            Start-Process $Matches[0]
            $abierto = $true
        }
        Start-Sleep -Seconds 2
    }
}

Paso "Creando el acceso directo"
@"
[InternetShortcut]
URL=$url
"@ | Set-Content -Encoding ASCII "$env:PUBLIC\Desktop\RRHH Minoshkas.url"
Start-Process $url

Paso "Listo"
Write-Host "Quedó el acceso directo 'RRHH Minoshkas' en el Escritorio: $url" -ForegroundColor Green
Write-Host "Entra con el usuario y la contraseña que te dio el administrador."
