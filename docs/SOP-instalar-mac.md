# SOP — Instalar el agente en una Mac

> Se corre una vez por máquina. Media hora la primera vez, diez minutos después.
>
> **Antes de empezar, dos cosas que este sistema todavía no hace**, para que
> nadie las espere:
>
> - **No envía mensajes.** Falta el adaptador de Playwright (`whatsapp_web.py`,
>   fase 4). El agente lee los chats y redacta borradores; el envío se rechaza
>   con un motivo explícito. Lo que se puede probar de punta a punta es
>   **botón → leer WhatsApp → triage → borradores en el panel**.
> - **El vendedor no tiene ícono en la barra de menú** para pausar su máquina
>   (fase 5). Se pausa desde el panel.

---

## Antes de empezar — lo que hay que tener a mano

| | |
|---|---|
| Cuenta de Claude | **Una por máquina**, del Enterprise del cliente (D2). Una API key **no sirve**: desactiva la integración con Chrome |
| Chrome | Con la extensión Claude in Chrome instalada |
| WhatsApp Web | Con la sesión de **esa** línea iniciada, sin QR pendiente |
| La contraseña del panel | Para la parte 1 |

Y confirmar con el administrador de la organización que la extensión esté
**habilitada por política**. Si está restringida, no funciona en ninguna máquina
y no se arregla desde el código.

---

# Parte 1 — En el panel

Cuatro pasos. Se hacen desde cualquier navegador y **no necesitan la Mac
delante**: conviene hacerlos enteros antes de sentarse a la máquina.

## Paso 1 — Entrar al panel

**https://frontend-produccion.onrender.com**, con la contraseña del panel.

Si no entra, lo único que puede faltar es `PANEL_PASSWORD` en el servicio
`backend-produccion` de Render. Es la única variable que se carga a mano:
`SESION_SECRET` lo genera Render solo (`generateValue: true` en el blueprint).

## Paso 2 — ⚠️ Decir a quién puede escribirle

**Configuración → destinos permitidos.** Cargar los números de prueba, y sólo
esos.

En una base nueva esta lista **arranca vacía**, y vacía significa **a nadie**
(regla R4). No es un descuido del sistema: es su estado de fábrica, y es lo que
hace imposible que un cliente real reciba algo por accidente.

Pero tiene una consecuencia que confunde la primera vez: **si se saltea este
paso, la corrida lee los chats y no redacta ninguno.** Se ve como si no hubiera
funcionado, y en realidad funcionó exactamente como debía. El log lo cuenta:
`no_permitidos`.

Se guardan normalizados a E.164, así que se pueden escribir con espacios y
guiones.

En la misma pantalla, **tope por corrida = 3** mientras se esté probando.

## Paso 3 — Dar de alta la máquina

Panel → **Dar de alta una máquina**:

- **Identificador** — minúsculas, números y guiones. `mac-rocio`, no
  `Mac de Rocío`. Es lo que se ve en logs y URLs, y el formulario lo rechaza si
  no lo es.
- **Nombre del vendedor** — acá sí, con mayúsculas y acentos.
- **Línea de WhatsApp** — opcional.

⚠️ **El token se muestra una sola vez.** Se guarda hasheado y no se puede
recuperar; si se pierde hay que rotarlo y reconfigurar la máquina.

La máquina **nace inactiva**. Instalar no es activar.

## Paso 4 — Anotar la URL del backend

La que va a ir en el `.env` de la Mac:

```
https://backend-produccion-7yqr.onrender.com
```

⚠️ **Lleva sufijo.** `backend-produccion.onrender.com`, sin él, **es la
aplicación de otra persona**: los subdominios de Render son globales, el nombre
estaba tomado y Render asignó otro. Apuntar ahí mandaría credenciales a un
servidor ajeno.

Se comprueba en dos segundos:

```bash
curl https://backend-produccion-7yqr.onrender.com/health
```

Tiene que devolver `{"ok":true,"mongo":true,"entorno":"produccion"}`.

> **Alternativa para desarrollo:** una máquina de la misma red, con el backend
> escuchando en `0.0.0.0` y el puerto abierto en el firewall
> (`http://192.168.x.x:8000`). Sirve para probar sin depender del despliegue.

---

# Parte 2 — En la Mac

Diez pasos, del 5 al 14. Cada uno dice qué correr y qué tenés que ver.

---

## Paso 5 — Instalar las herramientas

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
npm install -g @anthropic-ai/claude-code
```

---

## Paso 6 — Traer el proyecto

```bash
git clone https://github.com/martinrodriguez19/centonara-seguimientos.git
cd centonara-seguimientos
```

**Todo lo que sigue se corre desde esa carpeta.** Si en algún momento algo falla
con "no such file", casi siempre es que saliste de ahí. Para volver:

```bash
cd ~/centonara-seguimientos
```

---

## Paso 7 — Preparar el Chrome del vendedor

Abrí Chrome —el que usa el vendedor todos los días— y asegurate de que tenga
estas dos cosas **en el mismo perfil**:

1. La extensión **Claude in Chrome** instalada
2. **WhatsApp Business** abierto en `web.whatsapp.com`, con la sesión iniciada

Después, **usá la extensión una vez** (abrila y pedile cualquier cosa). Eso hace
que se registre en esta máquina, y el paso 9 lo va a necesitar.

> Si la Mac tiene un solo perfil de Chrome, no hay nada que elegir. Si tiene
> varios, el paso 9 te va a decir cuál quedó bien.

---

## Paso 8 — Preparar el entorno del agente

```bash
uv sync --directory agente
```

Tarda un minuto la primera vez.

---

## Paso 9 — Averiguar los datos de esta máquina

Este comando mira la Mac y te dice todo lo que necesita saber el agente:

```bash
uv run --directory agente python -m agente.main --datos
```

**Lo que vas a ver:**

```
PERFILES DE CHROME EN ESTA MÁQUINA
  /Users/vendedor/Library/Application Support/Google/Chrome

  Default        extensión + WhatsApp  <-- este
  Profile 1      nada

PONÉ ESTO EN EL .env
  /Users/vendedor/centonara-seguimientos/.env

AGENTE_BACKEND_URL=https://backend-produccion-7yqr.onrender.com
AGENTE_MODO=simulado
CLAUDE_BIN=/usr/local/bin/claude
CHROME_PERFIL_DIR=Default
CHROME_PUERTO=9222
AGENTE_DEVICE_ID=f83d5f3e-3278-46c6-8ccc-148e58805116
AGENTE_MACHINE_ID=
   ^ el identificador que pusiste en el panel al dar de alta la máquina
AGENTE_TOKEN=
   ^ el que mostró el panel en ese momento. Se muestra UNA sola vez.
```

**Copiá ese bloque**, desde `AGENTE_BACKEND_URL` hasta el final. Lo vas a pegar
en el paso 10.

> **Si falta Claude Code** —que es lo más probable en una Mac recién entregada—
> te lo va a decir arriba de todo, con el comando para instalarlo:
>
> ```
> FALTA CLAUDE CODE
>   No se encontró el ejecutable `claude` en esta máquina.
>
>   Qué hacer:
>     npm install -g @anthropic-ai/claude-code
> ```
>
> El resto de los datos se imprime igual, así que podés ir armando el `.env`
> mientras se instala. Después volvés a correr el comando y completás la línea
> de `CLAUDE_BIN`, que va a salir resuelta.
>
> Ojo con una cosa: la línea va a decir `CLAUDE_BIN=` **vacía**, y abajo una
> explicación que empieza con `^`. Esa explicación **no se pega**.

**Si en vez de eso dice `NO SE PUEDE SEGUIR TODAVÍA`**, te va a explicar qué
falta y qué hacer. Los tres casos posibles:

| Lo que dice | Qué hacer |
|---|---|
| La extensión está en un perfil y WhatsApp en otro | Abrí el Chrome del perfil que tiene WhatsApp e instalá ahí la extensión |
| Ningún perfil tiene WhatsApp | Abrí `web.whatsapp.com` en el perfil que tiene la extensión y escaneá el QR |
| Ningún perfil tiene la extensión | Instalá Claude in Chrome |
| `AGENTE_DEVICE_ID=` sale vacío | La extensión está pero no se usó nunca. Usala una vez y volvé a correr esto |
| `FALTA CLAUDE CODE` arriba de todo | Corré `npm install -g @anthropic-ai/claude-code` y volvé a correr esto |

Arreglás lo que diga y **volvés a correr el mismo comando**.

---

## Paso 10 — Crear el archivo `.env`

```bash
cp .env.example .env
```

Abrilo:

```bash
open -e .env
```

Y pegá el bloque del paso 9, **reemplazando** las líneas que ya estén con esos
mismos nombres.

**Después completá las dos que quedaron vacías.** Las dos salen del panel, de
cuando diste de alta esta máquina:

- **`AGENTE_MACHINE_ID`** — el identificador que escribiste vos, tipo
  `mac-rocio`. Tiene que ser **idéntico**, letra por letra.
- **`AGENTE_TOKEN`** — el que el panel mostró una sola vez, empieza con `sgc_`.

> Si perdiste el token: en el panel, en la máquina, hay un botón para **rotarlo**.
> Genera uno nuevo y el anterior deja de servir.

**Dos cosas que rompen el archivo sin avisar:**

- Las líneas que empiezan con `^` en la salida del paso 9 **son explicaciones, no
  se pegan.**
- Un comentario **al lado** de un valor vacío se convierte en el valor. Si
  querés anotar algo, ponelo en la línea de arriba.

---

## Paso 11 — Correr el instalador

Fijate qué decía `CHROME_PERFIL_DIR` en el paso 9 y usalo acá.

Si decía `Default`:

```bash
bash agente/instalador/instalar-mac.sh
```

Si decía otra cosa, por ejemplo `Profile 3`:

```bash
CHROME_PERFIL_DIR="Profile 3" bash agente/instalador/instalar-mac.sh
```

Deja preparado el arranque automático del agente y de Chrome, y corre el
diagnóstico. **No arranca nada todavía.**

---

## Paso 12 — Dar el permiso de sitio ⚠️

Son **dos permisos distintos** con nombres parecidos. Uno ya está resuelto; el
otro es el único paso de toda la guía que no se puede hacer desde la terminal.

| Permiso | Quién lo pone |
|---|---|
| `mcp__claude-in-chrome`, para el modo headless | **El instalador, en el paso 11.** No hay nada que hacer |
| La lista de sitios **de la extensión** | A mano, acá |

> Si en algún lado encontrás un `echo '{...}' > ~/.claude/settings.json`, **no lo
> corras**. Sobrescribe el archivo entero, y a alguien que ya usaba Claude Code
> le borra su configuración. El instalador lo escribe respetando lo que hubiera.

### Lo que hay que hacer

**a.** Arrancá el Chrome del sistema, que ya quedó configurado con el perfil
correcto y el puerto:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.centonara.chrome.plist
```

> Se hace acá y no más adelante a propósito. Abrir Chrome con `open --args` no
> sirve: si ya hay una instancia corriendo, macOS **ignora los argumentos** y la
> ventana sale con el perfil equivocado. El LaunchAgent lo abre bien, y es
> además como va a arrancar todos los días.
>
> Si Chrome ya estaba abierto, cerralo del todo antes —todas las ventanas— y
> volvé a correr el comando.

**b.** Comprobá que quedó bien:

```bash
curl http://localhost:9222/json/version
```

Tiene que devolver un JSON con `"Browser": "Chrome/..."`. Si no contesta nada,
Chrome estaba abierto cuando corriste (a): cerralo y repetí.

**c.** En esa ventana de Chrome, entrá a `web.whatsapp.com`. Si pide QR,
escanealo con la línea del vendedor.

**d.** Con esa pestaña adelante: **ícono de Claude en la barra → configuración →
permisos de sitios → habilitar `web.whatsapp.com`.**

### Dos cosas que confunden acá

**El menú de Chrome no es este permiso.** Si entrás por ahí vas a ver "Acceso al
sitio: todos los sitios". Eso ya está bien y **no es lo que falta**: el de Chrome
viene dado, el de la extensión hay que darlo.

**Sin este, el error es `Claude in Chrome requires permission`** — lo tira el
navegador, no el CLI, así que **no aparece en ningún log del agente**. Si lo ves,
es esto.

### Por qué este no se automatiza

Es una puerta de consentimiento: la extensión pide que una persona autorice, a
propósito, que un programa opere sobre WhatsApp. Vive adentro del almacenamiento
de la extensión, no en un archivo de configuración.

Se podría forzar escribiendo ahí. **No se hace**: sería saltear un control de
seguridad, y se rompería en la próxima versión de la extensión.

Lo que sí se puede es **verificarlo sin adivinar**, y eso es el paso siguiente.

---

## Paso 13 — Comprobar que todo quedó bien

Primero lo que se lee de archivos:

```bash
uv run --directory agente python -m agente.main --diagnostico
```

Después lo que sólo se sabe abriendo la página:

```bash
uv run --directory agente python -m agente.main --sonda
```

Tiene que decir:

```
[OK ] permiso_sitio    la extensión puede entrar a web.whatsapp.com
[OK ] whatsapp_sesion  sesión iniciada, N chats a la vista
```

Abre WhatsApp Web una vez, cuenta los chats y **no lee ninguno**. Tarda un par de
minutos y cuesta alrededor de USD 0,50.

Si falla:

| Motivo | Qué hacer |
|---|---|
| `sin_permiso` | Falta el paso 12 |
| `sesion_no_iniciada` | WhatsApp Web está pidiendo el QR. Escanealo |
| `browser_no_disponible` | El `AGENTE_DEVICE_ID` del `.env` no es el de este Chrome. Volvé a correr `--datos` |

> **`selectores` va a salir en rojo, y está bien.** Los selectores de WhatsApp
> Web todavía no se verificaron contra una sesión real, así que el envío está
> bloqueado a propósito. La lectura y la redacción funcionan igual.

---

## Paso 14 — Arrancar el agente

Chrome ya está corriendo desde el paso 12. Falta el agente:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.centonara.agente.plist
```

Ver que esté vivo:

```bash
launchctl print gui/$(id -u)/com.centonara.agente | head -20
```

**Desde acá arranca solo cada vez que el vendedor inicia sesión.** Los logs
quedan en `~/Library/Logs/centonara/`.

Para parar las dos cosas:

```bash
launchctl bootout gui/$(id -u)/com.centonara.agente
launchctl bootout gui/$(id -u)/com.centonara.chrome
```

---

# Parte 3 — Activar y probar

## Paso 15 — Activar la máquina, que es una decisión aparte

En el panel, la máquina aparece **inactiva**. Recién cuando se la activa empieza
a tomar trabajo.

Antes de activarla, la conversación de consentimiento con el vendedor, registrada
(F5.7). El sistema **envía mensajes desde su línea, con su nombre**: eso tiene
que estar dicho y aceptado, no supuesto.

⚠️ Y si todavía circula el SOP viejo que dice *"No envía ningún mensaje. Nunca"*,
retirarlo de Drive, de los mails y de lo impreso. Dejó de ser cierto.

## Paso 16 — La primera corrida

1. En el panel, apretar el botón.
2. El agente toma el `LISTAR` y lee los chats recientes. Tarda unos minutos.
3. Se encola un `REDACTAR` **sólo** por los chats cuyo número esté en
   `destinos_permitidos`. Los demás se cuentan y no se pagan.
4. Los borradores aparecen en la pantalla de revisión.

Lo que **no** va a pasar todavía: que salga un mensaje. `ENVIAR` se rechaza con
`falta adaptadores/whatsapp_web.py`, que es lo correcto hasta la fase 4.

Dos resultados que parecen fallas y no lo son:

- **Ningún borrador**, porque ninguno de los chats recientes es de los números
  autorizados. Es R4 haciendo su trabajo.
- **Borradores retenidos y vacíos**, con la señal `SIN_CONTEXTO`. El modelo no
  encontró con qué escribir y se negó a inventar, que es la respuesta que el
  prompt le pide. Se escriben a mano desde el panel, o se descartan.

---

## Si algo no anda

| Síntoma | Causa |
|---|---|
| `OPENSSL_Uplink(...): no OPENSSL_Applink` | Un antivirus dejó `SSLKEYLOGFILE` en el entorno. El agente ya la descarta al arrancar; si aparece igual, es otro proceso |
| `Claude in Chrome requires permission` | Falta el paso 12: el permiso de sitio de la extensión |
| `token_rechazado` en el log | El token no es el de esta máquina, o se rotó |
| El agente no toma trabajo | La máquina está inactiva o pausada (paso 15), o el kill switch está puesto |
| `browser_no_disponible` | El `deviceId` es de otro Chrome |
| Arranca a mano y falla con launchd | Una ruta relativa en algún lado. Todo absoluto |
| WhatsApp Web pide QR de golpe, sin que nadie tocara nada | **La sesión expiró.** Pasa: dura días, no meses. Hay que volver a vincular |
| `curl localhost:9222` no contesta | Chrome estaba abierto al lanzarlo, o falta `--user-data-dir` |
| El panel muestra un error crudo | Reportarlo: los mensajes del panel se escriben para quien lo usa, no para quien lo programó |
