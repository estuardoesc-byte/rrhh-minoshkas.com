# Instalar RRHH Minoshkas en la computadora de la oficina (sin costo)

La aplicación corre en una computadora de la oficina con Windows. **Tailscale** crea una red privada
entre esa computadora y los equipos de Sandra, Julio y Estuardo, con candado HTTPS.

- No toca el dominio minoshkas.com, GoDaddy, el correo de Google ni el router.
- La aplicación no queda visible en internet: solo entran los equipos autorizados.
- Costo: Q0 (plan gratuito de Tailscale, hasta 3 usuarios).

## Antes de empezar

- Windows 10 u 11, que quede encendida en horario de trabajo y que no se suspenda:
  *Configuración > Sistema > Inicio/apagado y suspensión > Suspender: Nunca* (cuando está conectada).
- Google Drive para escritorio con la cuenta de Minoshkas, para el respaldo diario.
- La contraseña de esantacruz@minoshkas.com a la mano (solo para identificarse en Tailscale).

## Instalación: un doble clic (unos 20 minutos)

1. Descarga el ZIP de la aplicación y descomprímelo en el Escritorio.
2. Abre la carpeta y da **doble clic en `INSTALAR.bat`**. Acepta el permiso de administrador.
3. El instalador hace todo solo: Python, la aplicación, el arranque automático, el respaldo diario y Tailscale.
   Solo te va a pedir dos cosas en el navegador, que se abre solo:
   - **Sign in with Google** con esantacruz@minoshkas.com.
   - **Enable** para permitir HTTPS en tu red privada.
4. Al final pide los usuarios: escribe nombre y correo de Sandra Marquez, Julio Santa Cruz y Estuardo,
   y una contraseña de al menos 10 caracteres para cada uno. Enter vacío para terminar.
5. Queda un acceso directo **RRHH Minoshkas** en el Escritorio. La dirección también queda en
   `C:\RRHH-Minoshkas\direccion.txt` (algo como `https://nombre-pc.tail1234.ts.net`).

## Dar acceso a Sandra y Julio

1. Entra a https://login.tailscale.com/admin/users > **Invite users** y escribe sus correos.
2. **Computadora con Windows:** el instalador dejó en el Escritorio de la PC de la oficina la carpeta
   **RRHH - instalador para otras computadoras**. Cópiala a la otra computadora (USB o Google Drive)
   y da doble clic en **CONECTAR.bat**. Instala Tailscale, abre el navegador para entrar con el correo invitado
   y deja el acceso directo **RRHH Minoshkas** en el Escritorio.
3. **Celular:** instala la app **Tailscale** (App Store o Play Store), entra con el correo invitado
   y abre la dirección de RRHH. Conviene guardarla como favorito.

## Después

- **Importar empleados:** menú **Importar**, con la pestaña "empleados" del ERP descargada como CSV.
- **Patronos:** completa NIT y número patronal de IGSS en **Patronos**.
- **Respaldos:** cada día a las 7 p. m. se guarda un .zip en `Mi unidad\Respaldos RRHH Minoshkas` (se conservan 30).
- **Otro usuario o cambiar contraseña:** doble clic en `CREAR-USUARIO.bat`.
- **Actualizar la aplicación:** descarga el ZIP nuevo y vuelve a dar doble clic en `INSTALAR.bat`. Detiene la versión anterior, pone la nueva y los datos no se tocan.

## Si la computadora se apaga

La aplicación y Tailscale vuelven solos al encenderla. Mientras esté apagada nadie puede entrar, pero los datos no se pierden.

## Restaurar un respaldo

1. Detén la tarea: `Stop-ScheduledTask -TaskName "RRHH Minoshkas"` (PowerShell como administrador).
2. Descomprime el .zip: `rrhh.db` va a `C:\RRHH-Minoshkas\datos\` y la carpeta `documentos` a `C:\RRHH-Minoshkas\datos\documentos`.
3. Arranca de nuevo: `Start-ScheduledTask -TaskName "RRHH Minoshkas"`.
