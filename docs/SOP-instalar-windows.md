# Sistema de Seguimiento Comercial — puesta en marcha en Windows

> El hermano de [`SOP-instalar-mac.md`](SOP-instalar-mac.md) para una PC con Windows 10 u 11.
> **La Parte 1 (en el panel) y la Parte 3 (encender el sistema) son las mismas y no se
> repiten acá**: leélas allá. Lo que cambia es la Parte 2, la que pasa en la computadora del
> vendedor, y el apéndice.
>
> Fecha: 10/09/2026; comandos corregidos el 30/09/2026 con lo aprendido en las dos PC del
> 25/09 (ver [`PLAN-INSTALACION-Y-REINSTALACION.md`](PLAN-INSTALACION-Y-REINSTALACION.md)).
> **La misma guía, con botón para copiar cada comando, está en el panel: Ajustes → Instalar y
> reparar → pestaña Windows.**

---

# Antes de empezar

- Lo mismo que en Mac: la PC con Chrome, una cuenta de Claude por máquina, el identificador y
  el token del panel, y el vendedor cerca con su teléfono.
- **Que la PC no se suspenda ni hiberne**: para la corrida programada de las 17 tiene que estar
  prendida y con sesión iniciada en Windows. El comando está en 2.2.
- **Contar con pegar el instalador dos veces**: la primera vez se detiene pidiendo iniciar sesión
  en Claude Code. No es una falla.

---

# Parte 2 — En la PC del vendedor

## 2.1 — Preparar Chrome (con el mouse)

Igual que en Mac, en el Chrome que el vendedor usa todos los días:

1. **Instalar la extensión Claude in Chrome** e iniciar sesión con la cuenta de Claude de
   **esta** máquina.
2. **Usarla una vez**: apretar el ícono de Claude y pedirle cualquier cosa. (Si te lo olvidás,
   no pasa nada: el agente encuentra solo el dato que necesita la primera vez que alguien la
   use.)
3. **Abrir `web.whatsapp.com`** y escanear el QR con el teléfono del vendedor.
4. **Dar el permiso de sitio**: ícono de Claude → **configuración → permisos de sitios →
   habilitar `web.whatsapp.com`**. No es el menú de Chrome; es el de adentro de la extensión.

## 2.2 — Un comando, y listo

Abrir **PowerShell** (tecla Windows, escribir `PowerShell`, Enter — **no** hace falta "como
administrador") y pegar esto, que es **una sola línea** con un punto y coma en el medio:

```powershell
irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.ps1 -OutFile "$env:TEMP\instalar.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\instalar.ps1"
```

Baja el instalador a un archivo temporal y lo corre. Instala lo que falte (`uv` y Claude Code),
baja el programa a `~\centonara-seguimientos`, averigua solo los datos de la máquina, registra
tres tareas programadas —Chrome al iniciar sesión, el agente, y el actualizador— y lo enciende.
En el camino:

- **Pregunta el identificador y el token** — los de la nota de la Parte 1.
- **Pide iniciar sesión en Claude Code**, una única vez, y se detiene: correr `claude` en la
  PowerShell, entrar con la cuenta de esta máquina, salir con `/exit`, y volver a pegar el
  mismo comando.
- **Al final ofrece vincular el navegador de envío** (2.3). Conviene decir que sí ahí mismo,
  con el teléfono a mano.
- **Termina esperando la señal de vida del agente** y dice **QUEDÓ AL DÍA** con el commit, y
  después **INSTALACIÓN COMPLETA**. Si dice **NO QUEDÓ AL DÍA**, dice qué falta: hacer eso y
  volver a pegar el mismo comando. Recién con "completa" se sigue con la Parte 3.

Si algo falta, el instalador **lo dice en castellano y se detiene**. La respuesta es siempre
la misma: hacer lo que dice y volver a pegar el mismo comando.

> ⚠️ **El comando viejo, `irm … | iex`, no funciona** en una PC nueva: falla con *"La expresión
> de asignación no es válida"* en la línea 37 (el archivo empieza con una marca invisible que
> `iex` no sabe saltear), y en el primer error cierra la ventana entera, con el mensaje que
> decía qué arreglar. Si lo ves en alguna guía vieja, es ése el que hay que reemplazar por el de
> arriba.

**Que la PC nunca se suspenda ni hiberne** (aplica al plan de energía activo):

```powershell
powercfg /change standby-timeout-ac 0; powercfg /change standby-timeout-dc 0; powercfg /change hibernate-timeout-ac 0; powercfg /change hibernate-timeout-dc 0; powercfg /change monitor-timeout-ac 15; powercfg /change monitor-timeout-dc 15
```

Sólo notebooks, para que cerrar la tapa no suspenda:

```powershell
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0; powercfg /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0; powercfg /setactive SCHEME_CURRENT
```

## 2.3 — Vincular el navegador que escribe los mensajes

Lo mismo que en Mac: un navegador aparte, con su propia sesión de WhatsApp. Si en su momento se
dijo que no, o si esa sesión vence más adelante:

```powershell
cd ~\centonara-seguimientos; uv run --directory agente python -m agente.main --vincular
```

⚠️ En Windows el circuito de envío (Playwright con carpeta dedicada) **no se probó todavía**:
la PC que está en producción deja borradores con la extensión, que es el circuito que no lo
necesita. Antes de habilitar envíos desde una PC, correr `--vincular` y
`--verificar-selectores` ahí y mirar que pasen.

## 2.4 — Comprobar que quedó bien

El instalador ya lo hace al final. Para volver a mirarlo después, o cuando el panel dice "sin
conexión" con la PC prendida:

```powershell
Get-ScheduledTask "Centonara Agente","Centonara Chrome","Centonara Actualizador" | Select-Object TaskName, State
```

`Centonara Agente` tiene que decir **Running** (las otras dos dicen Ready cuando no están
corriendo en ese momento, y está bien). Y lo que decide de verdad, la señal de vida que el
agente escribe cada 30 segundos:

```powershell
Get-Content ~\.centonara\estado\vivo.json
```

Si `cuando` es de hace más de dos minutos, el agente no está corriendo aunque la tarea figure.
Para levantarlo: `Start-ScheduledTask "Centonara Agente"`.

> ⚠️ **No arrancar el agente a mano** con `python -m agente.main` mientras exista la tarea:
> queda atado a la ventana de PowerShell y, si la tarea ya corre, hay dos agentes con el mismo
> token. Si hay dudas de cuántos hay, reinstalar desde cero (2.6) los mata a todos.

## 2.5 — Una PC que ya funciona: agregarle sólo la actualización automática

Para una máquina instalada a mano y andando, **no se reinstala nada**. Se le agrega únicamente
la tarea del actualizador, que desde ahí la mantiene en la versión que fija el panel:

```powershell
irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.ps1 -OutFile "$env:TEMP\instalar.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\instalar.ps1" -SoloActualizador
```

Si el proyecto está en otra carpeta, agregar `-Repo "C:\la\carpeta"` al final. Registra la
tarea, se pone en la versión del panel, y termina. No toca el `.env`, ni cómo arranca el agente,
ni Chrome.

## 2.6 — Reinstalar desde cero

Cuando una PC falla y sigue fallando después de volver a correr el instalador, conviene dejar de
arreglarla encima: el instalador conserva el `.env`, el entorno y lo que sea que esté roto. Y en
Windows hay un motivo más: cuando llega una versión nueva, el agente se relanza por su cuenta y
la tarea deja de ser su dueña; si después alguien vuelve a correr el instalador o arranca la
tarea, quedan **dos agentes con el mismo token**.

**Conviene cuando:** la máquina figura sin conexión y el agente no arranca aunque se lo
reinicie; hay más de un agente corriendo; el instalador dice NO QUEDÓ AL DÍA dos veces seguidas
por lo mismo; o se cambió de vendedor o de cuenta en esa computadora.

**1. Desinstalar.** Pide escribir `SI` antes de tocar nada e imprime el identificador de la
máquina:

```powershell
irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/desinstalar.ps1 -OutFile "$env:TEMP\desinstalar.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\desinstalar.ps1"
```

Para y borra las tres tareas, mata todo agente que esté corriendo (también los relanzados) y el
navegador de envío, y borra el proyecto, el estado y los logs. **Conserva** la sesión de
WhatsApp del navegador de envío (no hay que volver a escanear ese QR), el login de Claude Code, y
el Chrome del vendedor, que no se toca nunca. Con `-Todo` al final borra también la sesión del
navegador de envío: para cuando la PC cambia de vendedor o de línea.

**2. Instalar de nuevo:** el comando de 2.2, tal cual. Va a pedir el identificador y el token; si
el token no está anotado, en el panel: Máquinas → la máquina → ⋯ → **Rotar token**, y usar el
nuevo. Tiene que terminar en **QUEDÓ AL DÍA** e **INSTALACIÓN COMPLETA**.

**3. En el panel** no hay que dar de alta nada: la máquina sigue existiendo y vuelve sola a
"conectada". Si estaba a mitad de una corrida, cancelarla desde el inicio **antes** de
desinstalar. Si estaba pausada o desactivada, sigue estándolo.

---

# El día a día, una vez andando

Igual que en Mac, con una diferencia que conviene saber: cuando el actualizador deja una versión
nueva, **el agente se cierra solo y vuelve a levantarse al minuto**. Es normal verlo "sin
conexión" un minuto en el panel después de una actualización.

**Tres cosas vencen cada tanto** y hay que rehacerlas. No son fallas, y ninguna necesita
reinstalar:

| Qué vence | Cómo se ve | Cómo se arregla |
|---|---|---|
| La sesión de WhatsApp del vendedor | Chrome pide el QR | Escanearlo de nuevo |
| La sesión del navegador de envío | El panel avisa *"venció la sesión del motor"* | El comando de vincular de 2.3 |
| La sesión de Claude Code | La corrida falla con *"la sesión de Claude Code venció"* u *"OAuth session expired"* | En PowerShell: `claude`, iniciar sesión (o `/login`), `/exit`. Después, cancelar la corrida frenada en el panel y volver a disparar |

---

# Si algo no anda

| Lo que se ve | Qué es | Qué hacer |
|---|---|---|
| *"La expresión de asignación no es válida"* en la línea 37 | Se pegó el comando viejo, `irm … \| iex` | El comando de 2.2 tal cual |
| El instalador se detiene en [2/8] pidiendo iniciar sesión | Claude Code no tiene sesión en esta PC. Es lo normal en una máquina nueva | `claude` → iniciar sesión → `/exit` → el mismo comando de nuevo |
| *"Failed to download binary … está siendo utilizado en otro proceso"* | El antivirus escaneó el binario de Claude Code justo cuando el instalador lo quería mover | Volver a pegar el instalador. Si insiste: `Remove-Item "$HOME\.claude\downloads" -Recurse -Force`, cerrar la ventana, abrir otra, de nuevo el instalador |
| Termina en **NO QUEDÓ AL DÍA**: el agente no dio señal de vida | Las tareas quedaron, pero el agente se cae al arrancar | `Get-Content $env:LOCALAPPDATA\Centonara\logs\agente.log -Tail 40`. Si no se entiende, 2.6 |
| La máquina figura "sin conexión" y está prendida | El agente no manda latidos, o la PC se suspendió | 2.4. Si la tarea dice Ready y la señal es vieja, `Start-ScheduledTask`. Si se suspende, el comando de energía de 2.2 |
| Hay dos agentes corriendo | Un agente relanzado tras una actualización, más otro que arrancó la tarea o alguien a mano | 2.6: el desinstalador los mata a todos |
| La tarjeta dice **atrasada** | El actualizador no pudo | `Get-Content $env:LOCALAPPDATA\Centonara\logs\actualizador.log -Tail 40` dice por qué |
| Una alerta dice que la máquina *falla todo lo que toma* | Sus últimos trabajos fallaron, con el motivo en la alerta | Si habla de Chrome o del deviceId: abrir Chrome con el perfil de WhatsApp y usar la extensión una vez. Si habla de la sesión de Claude: la tabla de arriba |
| `Claude in Chrome requires permission` | Falta el permiso de la extensión (2.1, punto 4) | Ícono de Claude → configuración → permisos de sitios |
| Una corrida queda "en curso" para siempre | Una máquina de la corrida está apagada y su trabajo espera | **Cancelar corrida** en el panel, **antes** de la hora de la programada: si a esa hora hay una en curso, la de ese día se saltea |

---

# Apéndice para quien mantiene el sistema

**Qué quedó instalado:** el proyecto en `~\centonara-seguimientos`; tres tareas en el
Programador de tareas (`Centonara Agente`, `Centonara Chrome`, `Centonara Actualizador`), que
corren como el usuario y en su sesión; una copia del actualizador en `~\.centonara\bin\`; y las
herramientas `uv` y `claude` en `~\.local\bin` / `%LOCALAPPDATA%\Programs`. Los logs, en
`%LOCALAPPDATA%\Centonara\logs\` (en UTF-8). El agente escribe su señal de vida en
`~\.centonara\estado\vivo.json`. La sesión del navegador de envío, en
`%LOCALAPPDATA%\Centonara\Chrome`.

**Cómo se reinicia el agente cuando hay versión nueva (D46).** El actualizador escribe
`agente\VERSION`; el agente lo ve entre dos jobs, lanza una copia de sí mismo desacoplada (con
la salida en `%LOCALAPPDATA%\Centonara\logs\agente.log`) y se va. Si no pudiera lanzarlo, sale
con código 75 y la tarea —si existe— lo reintenta al minuto. Si el nuevo no vuelve a dar
señales de vida, el actualizador restaura el árbol anterior. ⚠️ Desde ese momento el agente
**no cuelga de la tarea**: `Stop-ScheduledTask` no lo detiene. Es lo que arregla el sprint 3
del plan; hasta entonces, el desinstalador (2.6) es la forma segura de matarlo.

**Actualizar a mano, sin esperar la hora:**

```powershell
powershell -ExecutionPolicy Bypass -File ~\centonara-seguimientos\agente\instalador\actualizar.ps1
```

**Qué versión tiene instalada:** `Get-Content ~\centonara-seguimientos\agente\VERSION`.

**Volver a una versión anterior:** desde el panel, Ajustes → Sistema → *Versión del agente* →
pegar el commit. Todas las máquinas —Mac y Windows— van a ése en menos de una hora, sin tocar
ninguna.

**Sobre el BOM de los `.ps1`.** `instalar.ps1`, `actualizar.ps1` y `desinstalar.ps1` empiezan
con la marca UTF-8 (`EF BB BF`) a propósito: sin ella, Windows PowerShell 5.1 lee el archivo
como ANSI y todos los acentos de los mensajes salen rotos. Con `-File` la marca no molesta; con
`irm | iex` sí, y por eso ese comando no se usa. Un test del agente vigila que la marca esté.
