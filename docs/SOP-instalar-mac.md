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

Se hace desde cualquier navegador y **no necesita la Mac delante**. Conviene
hacerla entera antes de sentarse a la máquina.

## 1.1 · Entrar

**https://frontend-produccion.onrender.com**, con la contraseña del panel.

Si no entra, lo único que puede faltar es `PANEL_PASSWORD` en el servicio
`backend-produccion` de Render. Es la única variable que se carga a mano:
`SESION_SECRET` lo genera Render solo (`generateValue: true` en el blueprint).

## 1.2 · ⚠️ A quién puede escribirle — el paso que no se puede saltear

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

## 1.3 · Dar de alta la máquina

Panel → **Dar de alta una máquina**:

- **Identificador** — minúsculas, números y guiones. `mac-rocio`, no
  `Mac de Rocío`. Es lo que se ve en logs y URLs, y el formulario lo rechaza si
  no lo es.
- **Nombre del vendedor** — acá sí, con mayúsculas y acentos.
- **Línea de WhatsApp** — opcional.

⚠️ **El token se muestra una sola vez.** Se guarda hasheado y no se puede
recuperar; si se pierde hay que rotarlo y reconfigurar la máquina.

La máquina **nace inactiva**. Instalar no es activar.

## 1.4 · La URL del backend

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

## 2.1 · Instalar las herramientas y traer el repositorio

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
npm install -g @anthropic-ai/claude-code
```

```bash
git clone https://github.com/martinrodriguez19/centonara-seguimientos.git
cd centonara-seguimientos
```

Todo lo que sigue se corre **desde esa carpeta**. Es la raíz del repositorio: se
reconoce porque adentro están `agente/`, `backend/` y `docs/`.

---

## 2.2 · ⚠️ Elegir el perfil de Chrome — antes que nada

Este paso va primero porque **el instalador lo necesita**, y porque si queda mal
no funciona nada de lo demás.

`LISTAR` lee los chats usando la extensión Claude in Chrome. `ENVIAR` escribe
usando ese mismo navegador por CDP. Las dos van contra **un solo perfil**, y ese
perfil tiene que tener las dos cosas:

1. La extensión Claude in Chrome instalada
2. La sesión de WhatsApp Business iniciada

**Paso a paso:**

**a.** Qué perfiles tienen la extensión:

```bash
ls -d ~/Library/Application\ Support/Google/Chrome/*/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn
```

**b.** Qué perfiles tienen datos de WhatsApp Web:

```bash
ls -d ~/Library/Application\ Support/Google/Chrome/*/IndexedDB/*whatsapp*
```

**c.** Comparar. De cada línea, lo que importa es el tramo del medio: `Default`,
`Profile 3`, `Profile 20`. **Tiene que ser el mismo en las dos listas.**

| Qué pasó | Qué hacer |
|---|---|
| Sale el mismo perfil en las dos | Anotalo. Es tu `CHROME_PERFIL_DIR` |
| Salen perfiles distintos | Abrí Chrome en el perfil que tiene WhatsApp e instalá ahí la extensión, o iniciá WhatsApp en el perfil que tiene la extensión |
| La lista (a) sale vacía | Falta instalar la extensión Claude in Chrome |
| La lista (b) sale vacía | Falta abrir `web.whatsapp.com` y escanear el QR |

> En la máquina donde se desarrolló esto **estaban separados**: la extensión en
> `Profile 37`, la sesión en `Profile 20`. Ninguna de las dos partes habría
> funcionado, y el síntoma no habría dicho por qué.

---

## 2.3 · Correr el instalador

Si el perfil de §2.2 es `Default`:

```bash
bash agente/instalador/instalar-mac.sh
```

Si es otro —por ejemplo `Profile 3`—, se le pasa así:

```bash
CHROME_PERFIL_DIR="Profile 3" bash agente/instalador/instalar-mac.sh
```

Qué hace: verifica las herramientas, crea el entorno del agente, escribe los dos
LaunchAgents —el del agente y el de Chrome— y corre el diagnóstico.

**No arranca nada, y no pide ninguna credencial.** Al final imprime las líneas
exactas que hay que poner en el `.env`, ya resueltas para esta máquina.

---

## 2.4 · El archivo `.env` — dónde está y qué va en cada línea

```bash
cp .env.example .env
```

**Dónde vive:** en la **raíz del repositorio**, al lado de `agente/` y
`backend/`. La ruta completa es `<carpeta-del-repo>/.env`.

> El agente también lee `<carpeta-del-repo>/agente/.env` si existe, y ése pisa al
> de la raíz. **Usá uno solo**, el de la raíz: dos archivos con la misma variable
> es la forma más rápida de perder una tarde.

**Nunca se sube al repositorio.** Ya está en `.gitignore`.

### De dónde sale cada dato

| Variable | De dónde sale | Ejemplo |
|---|---|---|
| `AGENTE_BACKEND_URL` | Fija, la misma para todas las máquinas | `https://backend-produccion-7yqr.onrender.com` |
| `AGENTE_TOKEN` | Lo mostró el panel al dar de alta la máquina (§1.3). **Se muestra una sola vez** | `sgc_xxxxxxxxxxxx` |
| `AGENTE_MACHINE_ID` | El identificador que vos elegiste en el panel (§1.3). Tiene que ser **idéntico** | `mac-rocio` |
| `AGENTE_DEVICE_ID` | Se saca de esta máquina, con el comando de §2.5 | `f83d5f3e-3278-46c6-8ccc-148e58805116` |
| `AGENTE_MODO` | Se deja en `simulado` hasta que todo lo demás esté verde | `simulado` |
| `CLAUDE_BIN` | Lo resolvió el instalador y lo imprimió al final | `/usr/local/bin/claude` |
| `CHROME_PERFIL_DIR` | El perfil de §2.2. **Tiene que coincidir con el que usó el instalador** | `Profile 3` |
| `CHROME_BIN` | Vacío. Se buscan las rutas habituales de macOS | |
| `CHROME_PERFIL` | Vacío. Es `~/Library/Application Support/Google/Chrome` | |
| `CHROME_PUERTO` | `9222`, salvo que ese puerto esté ocupado | `9222` |

⚠️ **`CHROME_PERFIL_DIR` aparece en dos lugares**: acá y en el LaunchAgent de
Chrome que escribió el instalador. Si difieren, normalmente gana el LaunchAgent
—porque Chrome ya está abierto— pero el día que el agente tenga que abrirlo él,
va a abrir el perfil equivocado y no va a encontrar la sesión de WhatsApp.
Manteneleos iguales: por eso el instalador imprime la línea.

⚠️ **Los comentarios van en la línea de ARRIBA del valor, nunca al lado.** Con el
valor vacío, `dotenv` toma el `# ...` como el valor. Eso hacía que el
diagnóstico diera un OK falso con el `deviceId` sin configurar.

### Cómo verificar que quedó bien leído

```bash
./agente/.venv/bin/python -m agente.main --diagnostico
```

Si algún valor salió con un `#` adelante, o vacío, se ve acá.

---

## 2.5 · El `deviceId` de este Chrome

Es el identificador que la extensión se asigna a sí misma en **esta** máquina.
Sin él, con más de un Chrome conectado a la misma cuenta de Claude, el modo
headless no sabe a cuál conectarse.

```bash
grep -ao 'bridgeDeviceId.\{0,60\}' \
  ~/Library/Application\ Support/Google/Chrome/*/Local\ Extension\ Settings/fcoeoabgfenejglbffodgkkbkcdhcgfn/*.log
```

Sale algo así:

```
bridgeDeviceId&"f83d5f3e-3278-46c6-8ccc-148e58805116"
```

El UUID —sin comillas, sin el `&`— va en `AGENTE_DEVICE_ID`.

**Si no sale nada:** la extensión nunca se usó en esta máquina. Abrí Chrome en el
perfil de §2.2, usá la extensión una vez, y volvé a correr el comando.

**No sirve** listar los navegadores conectados a la cuenta: devuelve nombres
genéricos —`Browser 1`, `Browser 2`— que no dicen cuál es cuál.

---

## 2.6 · Los permisos, que son dos capas ⚠️

Este es el paso que más se olvida, porque uno de los dos **ya viene dado** y
parece que está todo.

| Capa | Quién la da | Estado habitual |
|---|---|---|
| Permiso de host de Chrome | Chrome, al instalar la extensión | ya viene: `<all_urls>` |
| **Lista de sitios de la extensión** | La extensión, a pedido | **falta** |

**La que hay que dar:** ícono de Claude en la barra de Chrome → configuración →
permisos de sitios → habilitar **`web.whatsapp.com`**.

Sin eso el error es `Claude in Chrome requires permission`, **lo emite el
navegador y no el CLI**, así que no aparece en ningún log del agente.

Y el permiso para el modo headless, si el instalador lo marcó en rojo:

```bash
mkdir -p ~/.claude && echo '{"permissions":{"allow":["mcp__claude-in-chrome"]}}' > ~/.claude/settings.json
```

---

## 2.7 · Comprobar, antes de arrancar nada

**a.** Los chequeos que se leen de archivos:

```bash
./agente/.venv/bin/python -m agente.main --diagnostico
```

**b.** Los dos que sólo se saben abriendo la página:

```bash
./agente/.venv/bin/python -m agente.main --sonda
```

```
[OK ] permiso_sitio    la extensión puede entrar a web.whatsapp.com
[OK ] whatsapp_sesion  sesión iniciada, N chats a la vista
```

Abre WhatsApp Web una vez, cuenta los chats y **no lee ninguno**. Cuesta
alrededor de USD 0,50 y tarda un par de minutos: por eso no está adentro del
diagnóstico.

Si falla, distingue los tres casos, que se arreglan distinto:

| Motivo | Qué hacer |
|---|---|
| `sin_permiso` | Falta §2.6 |
| `sesion_no_iniciada` | WhatsApp Web pide QR |
| `browser_no_disponible` | El `deviceId` de §2.5 no es el de este Chrome |

> **`selectores` va a salir en rojo**, y está bien: los selectores de WhatsApp
> Web todavía no se verificaron contra una sesión real. Mientras siga así, el
> envío en modo real se rechaza. Es lo único que separa al sistema de poder
> escribir, y se resuelve la primera vez que se corra contra WhatsApp de verdad.

---

## 2.8 · Arrancar

Primero Chrome, después el agente:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.centonara.chrome.plist
```

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.centonara.agente.plist
```

Comprobar que Chrome levantó el puerto:

```bash
curl http://localhost:9222/json/version
```

Tiene que devolver un JSON con `"Browser": "Chrome/..."`. Si no contesta, casi
siempre es que Chrome ya estaba abierto: cerralo del todo y volvé a correr el
`bootstrap`.

Y el estado del agente:

```bash
launchctl print gui/$(id -u)/com.centonara.agente | head -20
```

**Desde acá arranca solo cada vez que el vendedor inicia sesión**, y si el
proceso muere `launchd` lo vuelve a levantar. Los logs quedan en
`~/Library/Logs/centonara/`.

Para parar las dos cosas:

```bash
launchctl bootout gui/$(id -u)/com.centonara.agente
launchctl bootout gui/$(id -u)/com.centonara.chrome
```

⚠️ Es un **LaunchAgent** y no un LaunchDaemon. Chrome, la extensión y el native
messaging viven en la sesión interactiva del usuario; un daemon corre fuera de
esa sesión y no ve ese Chrome (D16).

---

# Parte 3 — Activar y probar

## 3.1 · Activarla, que es una decisión aparte

En el panel, la máquina aparece **inactiva**. Recién cuando se la activa empieza
a tomar trabajo.

Antes de activarla, la conversación de consentimiento con el vendedor, registrada
(F5.7). El sistema **envía mensajes desde su línea, con su nombre**: eso tiene
que estar dicho y aceptado, no supuesto.

⚠️ Y si todavía circula el SOP viejo que dice *"No envía ningún mensaje. Nunca"*,
retirarlo de Drive, de los mails y de lo impreso. Dejó de ser cierto.

## 3.2 · La primera corrida

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
| `Claude in Chrome requires permission` | §2.7, la capa de la extensión |
| `token_rechazado` en el log | El token no es el de esta máquina, o se rotó |
| El agente no toma trabajo | La máquina está inactiva o pausada (§3.1), o el kill switch está puesto |
| `browser_no_disponible` | El `deviceId` es de otro Chrome |
| Arranca a mano y falla con launchd | Una ruta relativa en algún lado. Todo absoluto |
| WhatsApp Web pide QR de golpe, sin que nadie tocara nada | **La sesión expiró.** Pasa: dura días, no meses. Hay que volver a vincular |
| `curl localhost:9222` no contesta | Chrome estaba abierto al lanzarlo, o falta `--user-data-dir` |
| El panel muestra un error crudo | Reportarlo: los mensajes del panel se escriben para quien lo usa, no para quien lo programó |
