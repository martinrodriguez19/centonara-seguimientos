# Instala TODO el agente en la PC Windows de un vendedor, con un solo comando
# (pegado en una PowerShell común, sin ser administrador):
#
#   irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.ps1 -OutFile "$env:TEMP\instalar.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\instalar.ps1"
#
# ⚠️ Se baja a un archivo y se corre con -File, y no `irm … | iex`, a
# propósito. Con `iex` el script llega como texto: un `exit` cierra la ventana
# entera —y se pierde el mensaje que decía qué arreglar—, no se le pueden pasar
# opciones, y el BOM del archivo queda pegado adelante del primer comentario y
# rompe el `param()` (pasó el 25/09/2026 en las dos primeras PC: ninguno de los
# comandos de la documentación anduvo).
#
# El BOM se QUEDA, y un test vigila que esté: Windows PowerShell 5.1 lee un
# .ps1 sin BOM como ANSI, y entonces todos los acentos de estos mensajes salen
# rotos. Con -File el BOM no molesta y los acentos se leen bien.
#
# Es el hermano de instalar.sh (Mac): los mismos ocho pasos, con lo que cambia
# en Windows. Es seguro correrlo las veces que haga falta: lo que ya está hecho
# lo saltea, lo que falta lo dice en castellano, y correrlo de nuevo arregla lo
# que falte. Actualizar NO requiere volver a correr esto: queda una tarea
# programada ("Centonara Actualizador", D46) que corre al iniciar sesión y cada
# hora y pone el agente en el commit que fija el panel.
#
# Para dejar la PC como si nunca se hubiera instalado (y reinstalar desde cero):
# desinstalar.ps1, en esta misma carpeta.
#
# Qué hace:
#   1. Instala las herramientas que falten (uv y Claude Code)
#   2. Comprueba que Claude Code tenga una sesión iniciada
#   3. Baja el proyecto a ~\centonara-seguimientos, si no está
#   4. Crea el entorno del agente
#   5. Averigua solo el perfil de Chrome y el deviceId, y escribe el .env —
#      sólo pregunta el identificador y el token del panel, y si ya estaban, no
#      pregunta nada
#   6. Registra las tres tareas programadas: Chrome al iniciar sesión, el agente
#      (que se vuelve a levantar solo si se cae o se reinicia), y el actualizador
#   7. Arranca todo y se pone en la versión que fija el panel
#   8. Ofrece vincular el navegador que escribe los mensajes
#   Y al final espera la señal de vida del agente: dice QUEDÓ AL DÍA con el
#   commit, o NO QUEDÓ AL DÍA con lo que falta. Sin señal de vida no dice
#   "completa".
#
# Qué NO hace, a propósito:
#   - No da el permiso de sitio de la extensión: lo abre una persona, en la extensión.
#   - No activa la máquina. Instalar no es activar: eso se decide en el panel.
#
# Con -SoloActualizador registra ÚNICAMENTE la tarea del actualizador y copia
# el script, sin tocar nada de lo demás. Es para una máquina que ya funciona,
# instalada a mano: se le agrega la actualización automática y nada más.

param(
    [switch]$SoloActualizador,
    [switch]$SinVincular,
    [string]$Repo = "$HOME\centonara-seguimientos",
    [string]$Backend = "https://backend-produccion-7yqr.onrender.com"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ZIP = "https://github.com/martinrodriguez19/centonara-seguimientos/archive/refs/heads/main.zip"
$LOGS = Join-Path $env:LOCALAPPDATA "Centonara\logs"
$BIN = Join-Path $HOME ".centonara\bin"
$TAREA_AGENTE = "Centonara Agente"
$TAREA_CHROME = "Centonara Chrome"
$TAREA_ACTUALIZADOR = "Centonara Actualizador"

function Titulo($texto) { Write-Host ""; Write-Host $texto -ForegroundColor White }
function Ok($texto) { Write-Host "  ok  $texto" }
function Mal($texto) { Write-Host "  MAL $texto" -ForegroundColor Red }
function RefrescarPath() {
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" +
        [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
        "$HOME\.local\bin;$env:LOCALAPPDATA\Programs\claude;" + $env:PATH
}

New-Item -ItemType Directory -Force -Path $LOGS | Out-Null
New-Item -ItemType Directory -Force -Path $BIN | Out-Null
RefrescarPath

# ---------------------------------------------------------------------------
# Las tareas programadas (D46). Corren como este usuario, en su sesión
# interactiva: la extensión vive en su Chrome y el agente tiene que verlo.
# ---------------------------------------------------------------------------

# Los comandos de las tareas escriben sus logs con `*>>`, que en PowerShell 5
# usa UTF-16 salvo que se le diga otra cosa — y el agente, cuando se relanza
# solo, escribe UTF-8 en el mismo archivo. Con esto los dos escriben igual y el
# log se puede leer. `$PSDefaultParameterValues` gobierna también la redirección.
$PREFACIO_UTF8 = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; `$PSDefaultParameterValues['Out-File:Encoding']='utf8'; "

function DetenerAgente() {
    # La tarea, y además todo python que corra `agente.main`: cuando llega una
    # versión nueva el agente se relanza desacoplado de la tarea (reinicio.py),
    # y a ése `Stop-ScheduledTask` no lo alcanza. Sin esto, volver a correr el
    # instalador dejaba DOS agentes con el mismo token.
    Stop-ScheduledTask -TaskName $TAREA_AGENTE -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^python' -and $_.CommandLine -and $_.CommandLine -match 'agente\.main' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function EsperarSenalDeVida($segundos) {
    # El agente escribe ~\.centonara\estado\vivo.json al registrarse y en cada
    # latido (30 s). Una marca de menos de 120 s es un agente vivo. Es lo mismo
    # que mira el actualizador, y lo único que dice la verdad: que la tarea
    # exista no significa que el agente esté corriendo.
    $archivo = Join-Path $HOME ".centonara\estado\vivo.json"
    $limite = (Get-Date).AddSeconds($segundos)
    while ((Get-Date) -lt $limite) {
        try {
            $marca = Get-Content $archivo -Raw -ErrorAction Stop | ConvertFrom-Json
            $edad = ((Get-Date).ToUniversalTime() - [DateTimeOffset]::Parse($marca.cuando).UtcDateTime).TotalSeconds
            if ($edad -lt 120) { return $true }
        } catch { }
        Start-Sleep -Seconds 3
    }
    return $false
}

function RegistrarTarea($nombre, $ejecutable, $argumentos, $carpeta, $disparador, $ajustes) {
    $accion = New-ScheduledTaskAction -Execute $ejecutable -Argument $argumentos -WorkingDirectory $carpeta
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Unregister-ScheduledTask -TaskName $nombre -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparador -Settings $ajustes -Principal $principal | Out-Null
    Ok "tarea programada: $nombre"
}

function RegistrarActualizador($python) {
    # La copia que corre el sistema, fuera del árbol que reemplaza. Si el árbol
    # instalado es anterior al actualizador (una PC instalada a mano), se baja
    # de GitHub: la primera vuelta del actualizador trae el resto.
    $origen = Join-Path $Repo "agente\instalador\actualizar.py"
    if (Test-Path $origen) {
        Copy-Item $origen (Join-Path $BIN "actualizar.py") -Force
    } else {
        Write-Host "  el proyecto instalado no trae el actualizador: se baja de GitHub"
        Invoke-WebRequest -Uri "https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/actualizar.py" -OutFile (Join-Path $BIN "actualizar.py")
    }
    $disparador = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $disparador.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
    $ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    $arg = "-WindowStyle Hidden -NoProfile -Command `"$PREFACIO_UTF8& '$python' '$BIN\actualizar.py' --repo '$Repo' *>> '$LOGS\actualizador.out'`""
    RegistrarTarea $TAREA_ACTUALIZADOR "powershell.exe" $arg $Repo $disparador $ajustes
}

if ($SoloActualizador) {
    Titulo "Sólo el actualizador (la máquina ya funciona: no se toca nada más)"
    $python = Join-Path $Repo "agente\.venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { Mal "no está $python — ¿el proyecto está en $Repo?"; exit 1 }
    if (-not (Test-Path (Join-Path $Repo ".env"))) { Mal "no hay .env en $Repo"; exit 1 }
    RegistrarActualizador $python
    Write-Host "  poniéndose en la versión que fija el panel..."
    & $python (Join-Path $BIN "actualizar.py") --repo $Repo --sin-verificar
    Start-ScheduledTask -TaskName $TAREA_ACTUALIZADOR
    Ok "listo: el actualizador corre al iniciar sesión y cada hora. Log: $LOGS\actualizador.log"
    exit 0
}

# ---------------------------------------------------------------------------
Titulo "[1/8] Las herramientas"

if (Get-Command uv -ErrorAction SilentlyContinue) { Ok "uv" } else {
    Write-Host "  instalando uv..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    RefrescarPath
}
if (Get-Command claude -ErrorAction SilentlyContinue) { Ok "claude" } else {
    Write-Host "  instalando Claude Code..."
    Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
    RefrescarPath
}
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Mal "Claude Code no quedó instalado. Cerrá esta ventana, abrí otra PowerShell y volvé a correr el instalador."
    exit 1
}
$CLAUDE_BIN = (Get-Command claude).Source
Ok "claude: $CLAUDE_BIN"

# ---------------------------------------------------------------------------
Titulo "[2/8] La sesión de Claude Code"

$sesionOk = $false
if (Test-Path "$HOME\.claude\.credentials.json") {
    Write-Host "  comprobando que la sesión siga viva (unos segundos)..."
    try {
        $null = "Contestá una sola palabra: ok" | & $CLAUDE_BIN -p 2>$null
        if ($LASTEXITCODE -eq 0) { $sesionOk = $true }
    } catch { }
}
if ($sesionOk) { Ok "sesión iniciada y viva" } else {
    Write-Host "  Nunca se inició sesión en Claude Code en esta máquina, o la sesión venció."
    Write-Host ""
    Write-Host "  Cómo se arregla:"
    Write-Host "    1. En esta PowerShell, corré:  claude"
    Write-Host "    2. Iniciá sesión (si no la ofrece, escribí /login) con la cuenta de Claude de ESTA máquina"
    Write-Host "    3. Salí escribiendo:  /exit"
    Write-Host "    4. Volvé a correr este instalador, el mismo comando de antes"
    exit 1
}

# ---------------------------------------------------------------------------
Titulo "[3/8] El proyecto"

# Un `.git` en la carpeta de un vendedor no es de un desarrollador: es una
# instalación vieja hecha con `git clone` (D53, igual que en Mac). Se aparta
# —no se borra— y se sigue como en una PC limpia. El .env y el .venv quedan.
if (Test-Path (Join-Path $Repo ".git")) {
    $aparte = Join-Path $HOME (".centonara\git-viejo-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Force -Path (Split-Path $aparte) | Out-Null
    Move-Item (Join-Path $Repo ".git") $aparte
    Write-Host "  aviso: $Repo era un clon de git de una instalación vieja."
    Write-Host "         Se apartó a $aparte y se baja la última versión."
}
# Se baja SIEMPRE, encima de lo que haya: el zip trae el código y nada más, así
# que el .env y el .venv de esta PC no se tocan. Antes, si el proyecto ya
# estaba, no se bajaba nada — y una PC instalada a mano seguía con código
# viejo hasta que el actualizador corriera. Si no se puede bajar pero ya hay
# una copia, se sigue con ésa: no poder actualizar no es no poder instalar.
Write-Host "  bajando la última versión a $Repo"
$temporal = Join-Path $env:TEMP ("centonara-" + [guid]::NewGuid().ToString("N"))
try {
    New-Item -ItemType Directory -Force -Path $temporal | Out-Null
    Invoke-WebRequest -Uri $ZIP -OutFile (Join-Path $temporal "main.zip")
    Expand-Archive -Path (Join-Path $temporal "main.zip") -DestinationPath $temporal -Force
    $raiz = Get-ChildItem $temporal -Directory | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path $Repo | Out-Null
    Copy-Item -Path (Join-Path $raiz.FullName "*") -Destination $Repo -Recurse -Force
    Ok "proyecto en $Repo"
} catch {
    if (Test-Path (Join-Path $Repo "agente\pyproject.toml")) {
        Write-Host "  aviso: no se pudo bajar la última versión desde GitHub ($($_.Exception.Message))."
        Write-Host "  Se sigue con la copia que ya está en $Repo."
    } else {
        Mal "no se pudo bajar el proyecto desde GitHub, y en $Repo no hay una copia. ¿Hay internet?"
        exit 1
    }
} finally {
    Remove-Item $temporal -Recurse -Force -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
Titulo "[4/8] El entorno del agente"

uv sync --directory (Join-Path $Repo "agente")
$PYTHON = Join-Path $Repo "agente\.venv\Scripts\python.exe"
if (-not (Test-Path $PYTHON)) { Mal "no quedó $PYTHON"; exit 1 }
Ok "entorno listo"

# ---------------------------------------------------------------------------
Titulo "[5/8] Los datos de esta máquina"

$ENV_ARCHIVO = Join-Path $Repo ".env"
$viejo = @{}
if (Test-Path $ENV_ARCHIVO) {
    foreach ($linea in Get-Content $ENV_ARCHIVO) {
        if ($linea -match '^\s*([A-Z_]+)\s*=\s*(.*?)\s*(#.*)?$') { $viejo[$matches[1]] = $matches[2] }
    }
}
$deviceViejo = $viejo["AGENTE_DEVICE_ID"]
if ($deviceViejo -like "PEGA-ACA*") { $deviceViejo = "" }

$script = @'
from agente.perfiles import listar, recomendar
r = recomendar(listar())
if r.listo:
    print("LISTO"); print(r.perfil.nombre); print(r.perfil.device_id or "")
else:
    print("FALTA"); print(r.problema); print(r.solucion)
'@
Push-Location (Join-Path $Repo "agente")
$datos = $script | & $PYTHON -
Pop-Location
$estado = $datos[0]; $linea2 = $datos[1]; $linea3 = $datos[2]

if ($estado -eq "LISTO") {
    $PERFIL = $linea2; $DEVICE_ID = $linea3
    Ok "perfil de Chrome: $PERFIL"
} else {
    $PERFIL = $viejo["CHROME_PERFIL_DIR"]; $DEVICE_ID = ""
    if (-not $PERFIL) {
        Write-Host "  Todavía no se puede seguir: $linea2"
        Write-Host "  Qué hacer: $linea3"
        Write-Host "  Después, volvé a correr este instalador."
        exit 1
    }
    Write-Host "  aviso: no se pudo verificar el perfil de Chrome ($linea2). Se conserva el del .env: $PERFIL"
}
if ($DEVICE_ID) { Ok "deviceId: $DEVICE_ID" }
elseif ($deviceViejo) { $DEVICE_ID = $deviceViejo; Ok "deviceId: el que ya estaba en el .env" }
else {
    # D47: no frena nada. El agente lo busca solo cuando alguien use la extensión.
    Write-Host "  aviso: la extensión de Claude todavía no tiene deviceId en esta máquina."
    Write-Host "  El agente se instala igual y lo va a encontrar solo la primera vez que alguien la use."
}

$BACKEND_URL = if ($viejo["AGENTE_BACKEND_URL"]) { $viejo["AGENTE_BACKEND_URL"] } else { $Backend }
$MACHINE_ID = $viejo["AGENTE_MACHINE_ID"]
$TOKEN = $viejo["AGENTE_TOKEN"]

Write-Host "  comprobando el servidor (si estaba dormido tarda un minuto)..."
try {
    $salud = Invoke-RestMethod -Uri "$BACKEND_URL/health" -TimeoutSec 120
    if (-not $salud.ok) { throw "sin ok" }
    Ok "el servidor contesta: $BACKEND_URL"
} catch {
    Mal "el servidor no contesta: $BACKEND_URL. ¿Hay internet? Esperá un minuto y volvé a correr el instalador."
    exit 1
}

if (-not $MACHINE_ID -or -not $TOKEN) {
    Write-Host ""
    Write-Host "  Dos datos salen del panel, de cuando se dio de alta esta máquina:"
    while (-not $MACHINE_ID) {
        $MACHINE_ID = (Read-Host "    Identificador de la máquina (ej: pc-sofia)").Trim()
        if ($MACHINE_ID -notmatch '^[a-z0-9][a-z0-9-]*$') { Write-Host "    Sólo minúsculas, números y guiones — idéntico al del panel."; $MACHINE_ID = "" }
    }
    while (-not $TOKEN) {
        $TOKEN = (Read-Host "    Token de la máquina (empieza con sgc_)").Trim()
        if ($TOKEN -notlike "sgc_?*") { Write-Host "    Tiene que empezar con sgc_. Si se perdió, en el panel se rota y sale uno nuevo."; $TOKEN = "" }
    }
} else { Ok "identificador y token ya estaban en el .env: se conservan" }

$contenidoEnv = @"
# Escrito por agente/instalador/instalar.ps1. Volver a correr el instalador lo
# regenera conservando estos valores. NO se comparte: tiene el token.
AGENTE_BACKEND_URL=$BACKEND_URL
CLAUDE_BIN=$CLAUDE_BIN
CHROME_PERFIL_DIR=$PERFIL
AGENTE_DEVICE_ID=$DEVICE_ID
AGENTE_MACHINE_ID=$MACHINE_ID
AGENTE_TOKEN=$TOKEN
"@
# Lo que alguien puso a mano en el .env y el instalador no conoce (otro
# navegador de envío, otro repositorio) se conserva: antes se perdía en cada
# reinstalación, y la PC volvía en silencio a la configuración de fábrica.
$conocidas = @("AGENTE_BACKEND_URL", "CLAUDE_BIN", "CHROME_PERFIL_DIR", "AGENTE_DEVICE_ID", "AGENTE_MACHINE_ID", "AGENTE_TOKEN")
$ajenas = @($viejo.Keys | Where-Object { $conocidas -notcontains $_ } | ForEach-Object { "$_=$($viejo[$_])" })
if ($ajenas.Count -gt 0) {
    $contenidoEnv += "`n# Conservado de la instalación anterior:`n" + ($ajenas -join "`n") + "`n"
    Ok ("conservadas del .env anterior: " + (($viejo.Keys | Where-Object { $conocidas -notcontains $_ }) -join ", "))
}
# Sin BOM, a propósito: `Out-File -Encoding utf8` en PowerShell 5 lo pone, y
# con BOM la primera clave del .env se lee como "﻿AGENTE_BACKEND_URL" —
# el agente arranca contra localhost sin decir por qué.
[System.IO.File]::WriteAllText($ENV_ARCHIVO, $contenidoEnv.Replace("`r`n", "`n"), (New-Object System.Text.UTF8Encoding $false))
Ok ".env escrito: $ENV_ARCHIVO"

# ---------------------------------------------------------------------------
Titulo "[6/8] El arranque automático"

# El permiso del modo headless (MVP #3), sin pisar la configuración de nadie.
Push-Location (Join-Path $Repo "agente")
& $PYTHON -c "from agente.permiso_mcp import asegurar; r = asegurar(); print('  permiso del modo headless: ' + r.detalle)"
Pop-Location

# Chrome al iniciar sesión, con el perfil de la extensión. Sin reintentos: si
# el vendedor lo cierra a propósito, el agente lo abre cuando llega trabajo.
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { Mal "no se encontró Chrome. Instalalo y volvé a correr esto."; exit 1 }
$ajustesChrome = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
RegistrarTarea $TAREA_CHROME $chrome "--profile-directory=`"$PERFIL`"" $Repo (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) $ajustesChrome

# El agente: al iniciar sesión, y si sale con error —también cuando sale a
# propósito para reiniciarse con código nuevo (D46, código 75)— la tarea lo
# vuelve a levantar al minuto.
$ajustesAgente = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$argAgente = "-WindowStyle Hidden -NoProfile -Command `"$PREFACIO_UTF8& '$PYTHON' -m agente.main *>> '$LOGS\agente.log'; exit `$LASTEXITCODE`""
RegistrarTarea $TAREA_AGENTE "powershell.exe" $argAgente (Join-Path $Repo "agente") (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) $ajustesAgente

RegistrarActualizador $PYTHON

# ---------------------------------------------------------------------------
Titulo "[7/8] Arrancar ahora"

Start-ScheduledTask -TaskName $TAREA_CHROME
Ok "Chrome al iniciar sesión"
DetenerAgente
Start-ScheduledTask -TaskName $TAREA_AGENTE
Ok "agente arrancado (si quedó vivo se comprueba al final)"

Write-Host "  poniéndose en la versión que fija el panel..."
& $PYTHON (Join-Path $BIN "actualizar.py") --repo $Repo --sin-verificar
if ($LASTEXITCODE -ne 0) { Write-Host "  aviso: el actualizador no pudo terminar; lo va a reintentar solo en una hora" }
Start-ScheduledTask -TaskName $TAREA_ACTUALIZADOR
Ok "actualizador al iniciar sesión y cada hora"

Push-Location (Join-Path $Repo "agente")
& $PYTHON -m agente.main --diagnostico
Pop-Location

# ---------------------------------------------------------------------------
Titulo "[8/8] El navegador que escribe los mensajes"

$VINCULAR = "cd $Repo; uv run --directory agente python -m agente.main --vincular"
$carpetaVinculo = Join-Path $env:LOCALAPPDATA "Centonara\Chrome"
if ((Test-Path $carpetaVinculo) -and (Get-ChildItem $carpetaVinculo | Select-Object -First 1)) {
    Ok "ya estaba vinculado, no hace falta escanear de nuevo"
} elseif ($SinVincular) {
    Write-Host "  Cuando puedas, corré:  $VINCULAR"
} else {
    Write-Host "  Este navegador es aparte del de todos los días: tiene su propia sesión de"
    Write-Host "  WhatsApp y es el que va a escribir los mensajes. Para vincularlo hay que"
    Write-Host "  escanear un QR con el teléfono del vendedor."
    $respuesta = Read-Host "  ¿Lo vinculamos ahora? Necesitás el teléfono a mano [S/n]"
    if ($respuesta -match '^[nN]') { Write-Host "  Listo, después. El comando es:  $VINCULAR" }
    else {
        Push-Location (Join-Path $Repo "agente")
        & $PYTHON -m agente.main --vincular
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
Titulo "¿Quedó al día?"
#
# Lo que importa al final no es que cada paso haya dicho "ok" sino que la PC
# haya quedado como tiene que quedar: las tres tareas registradas, una versión
# escrita, y el agente DANDO SEÑAL DE VIDA. Se dice en una línea que se pueda
# leer por teléfono: QUEDÓ AL DÍA o NO QUEDÓ AL DÍA.
$falta = @()
foreach ($tarea in @($TAREA_CHROME, $TAREA_AGENTE, $TAREA_ACTUALIZADOR)) {
    if (-not (Get-ScheduledTask -TaskName $tarea -ErrorAction SilentlyContinue)) { $falta += "falta la tarea $tarea" }
}
$archivoVersion = Join-Path $Repo "agente\VERSION"
$shaInstalado = ""
if (Test-Path $archivoVersion) { $shaInstalado = ((Get-Content $archivoVersion -First 1) -split " ")[0] }
if (-not $shaInstalado) { $falta += "no se escribió agente\VERSION" }
Write-Host "  esperando la señal de vida del agente (hasta 90 segundos)..."
if (EsperarSenalDeVida 90) {
    Ok "el agente dio señal de vida"
} else {
    $falta += "el agente no dio señal de vida en 90 s (mirá $LOGS\agente.log)"
}

if ($falta.Count -eq 0) {
    Write-Host "  QUEDÓ AL DÍA: $shaInstalado"
    Write-Host "  (el panel muestra ese commit en la tarjeta de esta máquina)"
} else {
    Mal ("NO QUEDÓ AL DÍA: " + ($falta -join "; "))
    Write-Host "  Volvé a correr este instalador. Si vuelve a decir lo mismo, mandá esta"
    Write-Host "  pantalla entera y los logs de $LOGS"
    Titulo "INSTALACIÓN INCOMPLETA"
    exit 1
}

# ---------------------------------------------------------------------------
Titulo "INSTALACIÓN COMPLETA"
Write-Host @"
  A partir de ahora, cada vez que el vendedor prenda esta PC e inicie sesión,
  Chrome y el agente arrancan solos; si el agente se cae, se vuelve a levantar
  solo; y una vez por hora se pone en la versión que fija el panel.

  Lo que queda, y NO se hace desde acá:

  1. En Chrome, con el mouse (una sola vez):
     ícono de Claude → configuración → permisos de sitios → web.whatsapp.com

  2. En el panel: registrar el consentimiento del vendedor y activar la
     máquina. Instalada no es activada: hasta activarla, no toma trabajo.

  Los logs quedan en $LOGS
  Las tareas se ven en el Programador de tareas: $TAREA_AGENTE, $TAREA_CHROME, $TAREA_ACTUALIZADOR
"@
