# Sistema de Seguimiento Comercial — comandos por computadora

> Sólo los comandos y para qué sirve cada uno. El paso a paso completo está en
> `SOP-instalar-mac.md` y `SOP-instalar-windows.md`.
>
> Cada comando se copia **entero** y se pega de una sola vez. Si en la hoja se ve cortado en
> dos renglones es sólo cómo entra en el ancho: al copiarlo va completo.

---

# Mac (Lautaro, Thomas)

Todo se pega en la **Terminal** (Cmd + barra espaciadora, escribir `Terminal`, Enter).

## Instalar por primera vez, o poner al día una Mac ya instalada

```bash
curl -fsSL --http1.1 https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/instalar.sh | bash
```

## Verificar que quedó bien

```bash
launchctl list | grep centonara
```

```bash
cat ~/centonara-seguimientos/agente/VERSION
```

```bash
tail -20 ~/Library/Logs/centonara/actualizador.log
```

## Actualizar ahora, sin esperar la hora

```bash
bash ~/centonara-seguimientos/agente/instalador/actualizar.sh
```

## Reiniciar el agente

```bash
launchctl kickstart -k gui/$(id -u)/com.centonara.agente
```

## Parar el agente

```bash
launchctl bootout gui/$(id -u)/com.centonara.agente
```

## Volver a arrancar el agente

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.centonara.agente.plist
```

## Ver qué está haciendo el agente, en vivo

```bash
tail -f ~/Library/Logs/centonara/agente.log
```

## Vincular el navegador que escribe los mensajes (una vez, o si venció)

```bash
cd ~/centonara-seguimientos && uv run --directory agente python -m agente.main --vincular
```

## Diagnóstico de la máquina

```bash
cd ~/centonara-seguimientos && uv run --directory agente python -m agente.main --diagnostico
```

---

# PC de Sofía (Windows, ya funciona)

Todo se pega en **PowerShell** (tecla Windows, escribir `PowerShell`, Enter). No hace falta
"como administrador".

## Agregar la actualización automática (una sola vez; no toca nada más)

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.ps1))) -SoloActualizador
```

## Verificar que quedó bien

```powershell
Get-ScheduledTask "Centonara Actualizador"
```

```powershell
Get-Content ~\centonara-seguimientos\agente\VERSION
```

```powershell
Get-Content $env:LOCALAPPDATA\Centonara\logs\actualizador.log -Tail 20
```

## Actualizar ahora, sin esperar la hora

```powershell
powershell -ExecutionPolicy Bypass -File ~\centonara-seguimientos\agente\instalador\actualizar.ps1
```

## Ver si el agente está vivo y con qué versión

```powershell
Get-Content ~\.centonara\estado\vivo.json
```

## Ver qué está haciendo el agente

```powershell
Get-Content $env:LOCALAPPDATA\Centonara\logs\agente.log -Tail 50
```

## Arrancar el agente a mano (sólo si no está corriendo ya)

```powershell
cd ~\centonara-seguimientos; uv run --directory agente python -m agente.main
```

---

# PC nueva con Windows

Todo se pega en **PowerShell** (tecla Windows, escribir `PowerShell`, Enter). No hace falta
"como administrador".

## Instalar por primera vez, o poner al día una PC ya instalada con esto

```powershell
irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.ps1 | iex
```

## Verificar que quedó bien

```powershell
Get-ScheduledTask | Where-Object TaskName -like "Centonara*"
```

```powershell
Get-Content ~\centonara-seguimientos\agente\VERSION
```

## Actualizar ahora, sin esperar la hora

```powershell
powershell -ExecutionPolicy Bypass -File ~\centonara-seguimientos\agente\instalador\actualizar.ps1
```

## Arrancar el agente

```powershell
Start-ScheduledTask "Centonara Agente"
```

## Parar el agente

```powershell
Stop-ScheduledTask "Centonara Agente"
```

## Ver qué está haciendo el agente

```powershell
Get-Content $env:LOCALAPPDATA\Centonara\logs\agente.log -Tail 50
```

## Vincular el navegador que escribe los mensajes (una vez, o si venció)

```powershell
cd ~\centonara-seguimientos; uv run --directory agente python -m agente.main --vincular
```

## Diagnóstico de la máquina

```powershell
cd ~\centonara-seguimientos; uv run --directory agente python -m agente.main --diagnostico
```

---

# Desde el panel (sin tocar ninguna computadora)

## Fijar qué versión corren todas las máquinas, o volver atrás

Configuración → **Versión del agente** → pegar el commit → *Fijar versión*.
Vacío = lo último publicado. Todas las máquinas van a ésa en menos de una hora.

## Ver qué versión corre cada máquina

Panel → tarjeta de la máquina → **Versión**: el commit, y *al día* / *atrasada*.
