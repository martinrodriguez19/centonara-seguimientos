# Sistema de Seguimiento Comercial — comandos por computadora

> Sólo los comandos y para qué sirve cada uno. El paso a paso completo está en
> `SOP-instalar-mac.md` y `SOP-instalar-windows.md`, y **la misma guía con botón para copiar
> cada comando está en el panel: Ajustes → Instalar y reparar**, con una pestaña por tipo de
> computadora (Mac, Mac con macOS anterior a 13, Windows).
>
> Cada comando se copia **entero** y se pega de una sola vez. Si en la hoja se ve cortado en
> dos renglones es sólo cómo entra en el ancho: al copiarlo va completo.
>
> Comandos corregidos el 30/09/2026: los de Windows con `irm … | iex` **no funcionaban**
> (ver `PLAN-INSTALACION-Y-REINSTALACION.md`). Si tenés una hoja anterior, es ésta la que vale.

---

# Mac

Todo se pega en la **Terminal** (Cmd + barra espaciadora, escribir `Terminal`, Enter).

## Instalar por primera vez, o arreglar encima una Mac ya instalada

Se pega **dos veces** en una Mac nueva: la primera se detiene pidiendo iniciar sesión en Claude
Code (`claude` → iniciar sesión → `/exit`). Al final tiene que decir `QUEDÓ AL DÍA: <commit>`.

```bash
curl -fsSL --http1.1 https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/instalar.sh | bash
```

Si dice "macOS 13 o más" y se detiene, esa Mac es vieja: pestaña "Mac con macOS anterior a 13"
en el panel, y después este mismo comando.

## Reinstalar desde cero (la máquina falla y sigue fallando)

1. Desinstalar. Pide escribir `SI`. Conserva la sesión de WhatsApp del navegador de envío y el
   login de Claude Code; borra todo lo demás del agente:

```bash
curl -fsSL --http1.1 https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/desinstalar.sh | bash
```

   Para borrar también la sesión del navegador de envío (cambio de vendedor o de línea):

```bash
curl -fsSL --http1.1 https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/desinstalar.sh | bash -s -- --todo
```

2. Instalar de nuevo: el comando de arriba. Si el token no está anotado, en el panel: Máquinas
   → la máquina → ⋯ → **Rotar token**.

## Verificar que quedó bien

```bash
launchctl list | grep centonara
```

```bash
cat ~/.centonara/estado/vivo.json
```

```bash
cat ~/centonara-seguimientos/agente/VERSION
```

```bash
tail -n 40 ~/Library/Logs/centonara/actualizador.log
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

## Ver los errores del agente

```bash
tail -n 50 ~/Library/Logs/centonara/agente.err
```

## Vincular el navegador que escribe los mensajes (una vez, o si venció)

```bash
cd ~/centonara-seguimientos && uv run --directory agente python -m agente.main --vincular
```

## Diagnóstico de la máquina

```bash
cd ~/centonara-seguimientos && uv run --directory agente python -m agente.main --diagnostico
```

## Cuando vence la sesión de Claude Code

Se ve como una corrida que falla con *"la sesión de Claude Code venció"* u *"OAuth session
expired"*. En la Terminal de esa Mac, con el usuario que la usa:

```bash
claude
```

Iniciar sesión (si no la ofrece, escribir `/login`), y salir con `/exit`. Después, en el panel,
cancelar la corrida frenada y volver a disparar.

## La Mac no se actualiza

Primero, ver qué pasa. Este comando no cambia nada:

```bash
echo "--- git:"; ls -d ~/centonara-seguimientos/.git; echo "--- servicios:"; ls ~/Library/LaunchAgents | grep centonara; echo "--- actualizador:"; ls ~/.centonara/bin/; echo "--- version:"; cat ~/centonara-seguimientos/agente/VERSION; echo "--- log:"; tail -15 ~/Library/Logs/centonara/actualizador.log
```

| Lo que dice | Qué es |
|---|---|
| Aparece `.git`, hay 2 servicios y no hay `actualizar.py` | Es una instalación vieja (de cuando la guía decía `git clone`). Volver a correr el instalador: aparta el `.git` solo y deja los tres servicios |
| 3 servicios, y el log dice `al día` pero la versión es vieja | En el panel, Ajustes → Sistema → **Versión del agente** tiene un commit fijado. Tiene que estar vacío |
| El log dice `desconocida` | GitHub no le contesta al servidor. Se ve también como alerta en el panel; no es de esta Mac |

---

# Windows

Todo se pega en **PowerShell** (tecla Windows, escribir `PowerShell`, Enter). No hace falta
"como administrador". Cada comando es **una sola línea**, aunque tenga un punto y coma.

## Instalar por primera vez, o arreglar encima una PC ya instalada

Se pega **dos veces** en una PC nueva: la primera se detiene pidiendo iniciar sesión en Claude
Code (`claude` → iniciar sesión → `/exit`). Al final tiene que decir `QUEDÓ AL DÍA: <commit>`.

```powershell
irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.ps1 -OutFile "$env:TEMP\instalar.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\instalar.ps1"
```

## Que la PC nunca se suspenda ni hiberne

```powershell
powercfg /change standby-timeout-ac 0; powercfg /change standby-timeout-dc 0; powercfg /change hibernate-timeout-ac 0; powercfg /change hibernate-timeout-dc 0; powercfg /change monitor-timeout-ac 15; powercfg /change monitor-timeout-dc 15
```

Sólo notebooks, para que cerrar la tapa no suspenda:

```powershell
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0; powercfg /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0; powercfg /setactive SCHEME_CURRENT
```

## Una PC instalada a mano que ya funciona: agregarle sólo la actualización automática

```powershell
irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.ps1 -OutFile "$env:TEMP\instalar.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\instalar.ps1" -SoloActualizador
```

Si el proyecto está en otra carpeta, agregar ` -Repo "C:\la\carpeta"` al final.

## Reinstalar desde cero (la máquina falla y sigue fallando, o hay dos agentes)

1. Desinstalar. Pide escribir `SI`. Mata todos los agentes que estén corriendo. Conserva la
   sesión de WhatsApp del navegador de envío y el login de Claude Code:

```powershell
irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/desinstalar.ps1 -OutFile "$env:TEMP\desinstalar.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\desinstalar.ps1"
```

   Para borrar también la sesión del navegador de envío (cambio de vendedor o de línea):

```powershell
irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/desinstalar.ps1 -OutFile "$env:TEMP\desinstalar.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\desinstalar.ps1" -Todo
```

2. Instalar de nuevo: el comando de arriba. Si el token no está anotado, en el panel: Máquinas
   → la máquina → ⋯ → **Rotar token**.

## Verificar que quedó bien

```powershell
Get-ScheduledTask "Centonara Agente","Centonara Chrome","Centonara Actualizador" | Select-Object TaskName, State
```

```powershell
Get-Content ~\.centonara\estado\vivo.json
```

```powershell
Get-Content ~\centonara-seguimientos\agente\VERSION
```

```powershell
Get-Content $env:LOCALAPPDATA\Centonara\logs\actualizador.log -Tail 40
```

## Actualizar ahora, sin esperar la hora

```powershell
powershell -ExecutionPolicy Bypass -File ~\centonara-seguimientos\agente\instalador\actualizar.ps1
```

## Levantar el agente si no está corriendo

```powershell
Start-ScheduledTask "Centonara Agente"
```

⚠️ No arrancarlo a mano con `python -m agente.main` mientras exista la tarea: queda atado a la
ventana y, si la tarea ya corre, hay dos agentes con el mismo token. Si hay dudas, reinstalar
desde cero los mata a todos.

## Ver qué está haciendo el agente

```powershell
Get-Content $env:LOCALAPPDATA\Centonara\logs\agente.log -Tail 40
```

## Vincular el navegador que escribe los mensajes (una vez, o si venció)

```powershell
cd ~\centonara-seguimientos; uv run --directory agente python -m agente.main --vincular
```

## Diagnóstico de la máquina

```powershell
cd ~\centonara-seguimientos; uv run --directory agente python -m agente.main --diagnostico
```

## Cuando vence la sesión de Claude Code

Se ve como una corrida que falla con *"la sesión de Claude Code venció"* u *"OAuth session
expired"*. En PowerShell, con el usuario que usa esa PC:

```powershell
claude
```

Iniciar sesión (si no la ofrece, escribir `/login`), y salir con `/exit`. Después, en el panel,
cancelar la corrida frenada y volver a disparar.

---

# Desde el panel (sin tocar ninguna computadora)

## Fijar qué versión corren todas las máquinas, o volver atrás

Ajustes → Sistema → **Versión del agente** → pegar el commit → *Fijar versión*.
Vacío = lo último publicado. Todas las máquinas van a ésa en menos de una hora.

## Ver qué versión corre cada máquina, y si está viva

Máquinas → la máquina → **Resumen**: último latido, versión y *al día* / *atrasada*. Y
Análisis → **Errores y avisos** junta todo lo que hay que mirar, filtrable por máquina.

## Antes de reinstalar una computadora

Si estaba a mitad de una corrida: Inicio → **Cancelar corrida**, antes de desinstalar. Si el
token no está anotado: Máquinas → la máquina → ⋯ → **Rotar token**. No hay que dar de baja ni
volver a dar de alta la máquina.
