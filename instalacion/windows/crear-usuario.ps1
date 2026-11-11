# Crea o actualiza un usuario de RRHH Minoshkas.
# Uso: clic derecho > "Ejecutar con PowerShell". Pide nombre, correo y contraseña.
$Destino = "C:\RRHH-Minoshkas"
$nombre = Read-Host "Nombre completo"
$correo = Read-Host "Correo"
Push-Location $Destino
& "$Destino\.venv\Scripts\python.exe" -m scripts.crear_usuario $nombre $correo
Pop-Location
Read-Host "Presiona Enter para cerrar"
