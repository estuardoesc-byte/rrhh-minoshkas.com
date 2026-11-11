# Publicar RRHH Minoshkas en rrhh.minoshkas.com (sin costo)

La aplicación corre en una computadora de la oficina con Windows. Un túnel gratuito de Cloudflare
le da la dirección `https://rrhh.minoshkas.com`, con candado de seguridad, para entrar desde cualquier lugar.
No hay que abrir puertos del router.

Costo: Q0. Solo se sigue pagando la renovación del dominio en GoDaddy.

## Requisitos

- Una computadora con Windows 10 u 11 que quede encendida en horario de trabajo.
- Que no se suspenda: *Configuración > Sistema > Inicio/apagado y suspensión > Suspender: Nunca* (cuando está conectada).
- Google Drive para escritorio instalado con la cuenta de Minoshkas, para los respaldos diarios.

## Parte 1: instalar la aplicación (15 minutos)

1. En GitHub, abre el repositorio, botón verde **Code > Download ZIP**, y descomprímelo en el Escritorio.
2. Abre la carpeta `instalacion\windows`, clic derecho sobre `instalar.ps1` > **Ejecutar con PowerShell**.
   Si Windows pide permiso, acepta. Si dice que la ejecución de scripts está deshabilitada, abre PowerShell como administrador y escribe:
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, y vuelve a intentarlo.
3. Al terminar, ejecuta `crear-usuario.ps1` tres veces: Sandra Marquez, Julio Santa Cruz y Estuardo.
4. Abre `http://localhost:8000` en el navegador de esa computadora y entra con tu usuario.

## Parte 2: la dirección rrhh.minoshkas.com (20 minutos)

### 2.1 Pasar el dominio a Cloudflare (gratis)

1. Crea una cuenta en https://dash.cloudflare.com/sign-up con el correo de Minoshkas.
2. **Add a domain** > escribe `minoshkas.com` > plan **Free**.
3. Cloudflare copia los registros que ya tiene el dominio. **Antes de seguir**, revisa que aparezcan los registros **MX**
   (son los del correo @minoshkas.com). Si el dominio tiene correo y no aparecen MX, detente y avísale a Claude.
4. Cloudflare te muestra dos *nameservers* (por ejemplo `ana.ns.cloudflare.com`).
5. En GoDaddy: **Mis productos > minoshkas.com > DNS > Nameservers > Cambiar > Usar mis propios nameservers**,
   pega los dos de Cloudflare y guarda. El cambio tarda entre minutos y unas horas.

### 2.2 Crear el túnel

1. En Cloudflare: **Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared**. Nombre: `rrhh-minoshkas`.
2. Elige **Windows** y copia el comando que muestra (`cloudflared.exe service install ...`).
3. En la computadora de la oficina, abre PowerShell como administrador, instala cloudflared con
   `winget install --id Cloudflare.cloudflared` y pega el comando copiado.
4. En **Public Hostname**: subdominio `rrhh`, dominio `minoshkas.com`, tipo `HTTP`, URL `localhost:8000`. Guarda.
5. Abre `https://rrhh.minoshkas.com` desde tu celular. Debe aparecer la pantalla de entrada.

## Después

- **Importar empleados:** menú **Importar**, con la pestaña "empleados" del ERP descargada como CSV.
- **Patronos:** completa NIT y número patronal de IGSS en **Patronos**.
- **Respaldos:** cada día a las 7 p. m. se guarda un .zip en `Mi unidad\Respaldos RRHH Minoshkas` (se conservan 30).
- **Actualizar la aplicación:** descarga el ZIP nuevo de GitHub y vuelve a ejecutar `instalar.ps1`. Los datos no se tocan.

## Si la computadora se apaga

La aplicación vuelve sola al encenderla. Mientras esté apagada, nadie puede entrar, pero los datos no se pierden.

## Restaurar un respaldo

1. Detén la tarea: `Stop-ScheduledTask -TaskName "RRHH Minoshkas"` (PowerShell como administrador).
2. Descomprime el .zip: `rrhh.db` va a `C:\RRHH-Minoshkas\datos\` y la carpeta `documentos` a `C:\RRHH-Minoshkas\datos\documentos`.
3. Arranca de nuevo: `Start-ScheduledTask -TaskName "RRHH Minoshkas"`.
