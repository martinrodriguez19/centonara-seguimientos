# Actualiza el agente en esta PC al commit que fija el panel. Un comando:
#
#     powershell -ExecutionPolicy Bypass -File $HOME\centonara-seguimientos\agente\instalador\actualizar.ps1
#
# No es más que un atajo a `actualizar.py`, que es el que hace el trabajo y el
# que corre solo al iniciar sesión y cada hora (tarea "Centonara Actualizador").
# Correrlo a mano sirve para no esperar la hora, y para ver qué dice.
#
# Se corre la copia de `~\.centonara\bin\` si existe: es la que usa el sistema,
# y un script no puede pisarse a sí mismo mientras corre.

param(
    [string]$Repo = "",
    [string]$Sha = "",
    [switch]$SinVerificar
)

$ErrorActionPreference = "Stop"

if (-not $Repo) {
    $Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
$copia = Join-Path $HOME ".centonara\bin\actualizar.py"
$python = Join-Path $Repo "agente\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $python) {
    Write-Error "No se encontró Python: ni el entorno del agente ni uno del sistema."
    exit 1
}

$env:PATH = "$HOME\.local\bin;" + $env:PATH

$script = if (Test-Path $copia) { $copia } else { Join-Path $Repo "agente\instalador\actualizar.py" }
$argumentos = @($script, "--repo", $Repo)
if ($Sha) { $argumentos += @("--sha", $Sha) }
if ($SinVerificar) { $argumentos += "--sin-verificar" }

& $python @argumentos
exit $LASTEXITCODE
