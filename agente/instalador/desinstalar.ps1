# Deja la PC como si el agente nunca se hubiera instalado. Un comando, pegado
# en una PowerShell común (sin administrador):
#
#   irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/desinstalar.ps1 -OutFile "$env:TEMP\desinstalar.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\desinstalar.ps1"
#
# Es la mitad de "reinstalar desde cero": esto, y después el instalador de
# siempre. Existe porque una PC que falla y sigue fallando no se arregla
# volviendo a correr el instalador encima —que conserva el .env, el entorno y
# lo que sea que esté roto—, y porque en Windows el agente que se relanzó por
# una versión nueva ya no cuelga de la tarea: "Stop-ScheduledTask" no lo
# detiene, y podía quedar más de uno corriendo con el mismo token. Se baja de
# GitHub y no del repositorio de la PC a propósito: el repositorio puede ser
# justo lo que está roto.
#
# Qué borra:
#   - Las tres tareas programadas (Centonara Agente, Centonara Chrome,
#     Centonara Actualizador)
#   - Los procesos: todo python que corra el agente (también los que quedaron
#     de versiones anteriores), el actualizador, y el navegador dedicado del
#     motor de envío si estaba abierto
#   - ~\centonara-seguimientos entero (incluido el .env con el token)
#   - ~\.centonara (señal de vida, copia del actualizador, respaldos, candado)
#   - %LOCALAPPDATA%\Centonara\logs
#
# Qué CONSERVA, salvo que se pida -Todo:
#   - La sesión de WhatsApp del navegador que escribe los mensajes
#     (%LOCALAPPDATA%\Centonara\Chrome): así reinstalar no obliga a escanear
#     el QR de nuevo
#   - El login de Claude Code, uv y claude: son de la PC, no del agente
#   - El Chrome del vendedor: no se toca nunca
#
# Pide confirmación por teclado; con -Si no pregunta.
#
# Después de esto, el panel va a mostrar la máquina "sin conexión" —es lo
# esperado— hasta que se vuelva a instalar. El identificador y el token se
# vuelven a pedir en la instalación: el identificador se imprime acá; el token,
# si no está anotado, se rota desde el panel (Máquinas → la máquina → ⋯ →
# Rotar token) y sale uno nuevo.

param(
    [switch]$Todo,
    [switch]$Si,
    [string]$Repo = "$HOME\centonara-seguimientos"
)

$ErrorActionPreference = "Continue"

$ESTADO = Join-Path $HOME ".centonara"
$CENTONARA_LOCAL = Join-Path $env:LOCALAPPDATA "Centonara"
$LOGS = Join-Path $CENTONARA_LOCAL "logs"
$SESION_ENVIO = Join-Path $CENTONARA_LOCAL "Chrome"
$TAREAS = @("Centonara Agente", "Centonara Chrome", "Centonara Actualizador")

function Titulo($texto) { Write-Host ""; Write-Host $texto -ForegroundColor White }
function Ok($texto) { Write-Host "  ok  $texto" }
function Mal($texto) { Write-Host "  MAL $texto" -ForegroundColor Red }

# ---------------------------------------------------------------------------
Titulo "Qué hay instalado"

$machineId = ""
$envArchivo = Join-Path $Repo ".env"
if (Test-Path $envArchivo) {
    foreach ($linea in Get-Content $envArchivo) {
        if ($linea -match '^\s*AGENTE_MACHINE_ID\s*=\s*(.*?)\s*(#.*)?$') { $machineId = $matches[1] }
    }
}
if ($machineId) { Write-Host "  identificador de esta máquina en el panel: $machineId" }
else { Write-Host "  (no hay un .env con identificador: la instalación no llegó a ese paso)" }
foreach ($tarea in $TAREAS) {
    if (Get-ScheduledTask -TaskName $tarea -ErrorAction SilentlyContinue) { Write-Host "  tarea: $tarea" }
}
if (Test-Path $Repo) { Write-Host "  proyecto: $Repo" }
if (Test-Path $ESTADO) { Write-Host "  estado: $ESTADO" }
if (Test-Path $LOGS) { Write-Host "  logs: $LOGS" }
if (Test-Path $SESION_ENVIO) {
    if ($Todo) { Write-Host "  sesión del navegador de envío: $SESION_ENVIO  <- se borra (-Todo)" }
    else { Write-Host "  sesión del navegador de envío: $SESION_ENVIO  <- se conserva" }
}

# ---------------------------------------------------------------------------
Titulo "Confirmar"

Write-Host "  Se va a borrar todo lo de arriba. El Chrome del vendedor y el login de"
Write-Host "  Claude Code no se tocan. No se puede deshacer."
if ($Si) {
    Write-Host "  (-Si: sin preguntar)"
} else {
    $respuesta = Read-Host "  Para seguir, escribí SI en mayúsculas"
    if ($respuesta -cne "SI") { Write-Host "  Cancelado. No se borró nada."; exit 1 }
}

# ---------------------------------------------------------------------------
Titulo "[1/4] Parar las tareas"

foreach ($tarea in $TAREAS) {
    if (Get-ScheduledTask -TaskName $tarea -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $tarea -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $tarea -Confirm:$false -ErrorAction SilentlyContinue
        Ok "borrada la tarea $tarea"
    }
}

# ---------------------------------------------------------------------------
Titulo "[2/4] Matar los procesos"
#
# Por la línea de comandos, no por el nombre: "python" y "chrome" son también
# de otras cosas. El Chrome del vendedor no calza con ninguno de estos
# patrones: el navegador dedicado se reconoce por su carpeta de datos.
$patron = 'agente\.main|actualizar\.py|Centonara\\Chrome'
$procesos = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match $patron -and $_.ProcessId -ne $PID }
foreach ($proceso in $procesos) {
    Stop-Process -Id $proceso.ProcessId -Force -ErrorAction SilentlyContinue
    Ok "cerrado: $($proceso.Name) ($($proceso.ProcessId))"
}
Start-Sleep -Seconds 2

# ---------------------------------------------------------------------------
Titulo "[3/4] Borrar los archivos"

function Borrar($carpeta) {
    if (-not (Test-Path $carpeta)) { return }
    # Un archivo que todavía tiene abierto un proceso que recién se cerró
    # hace fallar el borrado: se reintenta un par de veces antes de rendirse.
    foreach ($intento in 1..5) {
        Remove-Item $carpeta -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $carpeta)) { Ok "borrado $carpeta"; return }
        Start-Sleep -Seconds 2
    }
    Mal "no se pudo borrar del todo $carpeta (algo lo tiene abierto)"
}
Borrar $Repo
Borrar $ESTADO
Borrar $LOGS
if ($Todo) { Borrar $SESION_ENVIO; Write-Host "  (la sesión de WhatsApp del motor se borró: hay que volver a escanear el QR)" }
Get-ChildItem $env:TEMP -Directory -Filter "centonara-*" -ErrorAction SilentlyContinue | ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

# ---------------------------------------------------------------------------
Titulo "[4/4] Comprobar"

$queda = @()
foreach ($tarea in $TAREAS) {
    if (Get-ScheduledTask -TaskName $tarea -ErrorAction SilentlyContinue) { $queda += "sigue la tarea $tarea" }
}
$vivos = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -match 'agente\.main' }
if ($vivos) { $queda += "hay un agente corriendo" }
if (Test-Path $Repo) { $queda += "sigue $Repo" }

if ($queda.Count -gt 0) {
    Mal ("NO QUEDÓ LIMPIA: " + ($queda -join "; "))
    Write-Host "  Reiniciá la PC y volvé a correr este mismo comando."
    exit 1
}

Titulo "DESINSTALACIÓN COMPLETA"
Write-Host @"
  La PC quedó sin el agente. En el panel va a figurar "sin conexión": es lo
  esperado hasta que se vuelva a instalar.

  Para instalar de nuevo, el comando de siempre (se pega dos veces si Claude
  Code pide iniciar sesión):

    irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.ps1 -OutFile "`$env:TEMP\instalar.ps1"; powershell -ExecutionPolicy Bypass -File "`$env:TEMP\instalar.ps1"

  Va a pedir el identificador$(if ($machineId) { " ($machineId)" }) y el token. Si el
  token no está anotado, en el panel: Máquinas → la máquina → ⋯ → Rotar token.
"@
exit 0
