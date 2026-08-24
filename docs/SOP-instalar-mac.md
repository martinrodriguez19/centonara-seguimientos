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

## 2.1 · Las herramientas

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

## 2.2 · Correr el instalador

```bash
bash agente/instalador/instalar-mac.sh
```

Verifica las herramientas, crea el entorno, escribe el LaunchAgent con **rutas
absolutas** y corre el diagnóstico. No arranca nada.

Lo de las rutas absolutas no es cosmético: `launchd` no tiene el PATH de una
terminal, y `claude` a secas se resuelve a nada. Es el problema #2 del MVP, el
que hace que ande a mano y falle cuando arranca solo.

## 2.3 · Completar el `.env`

```bash
cp .env.example .env
```

Cuatro valores:

```
AGENTE_BACKEND_URL=   # §1.4
AGENTE_TOKEN=         # el que mostró el panel en §1.3
AGENTE_MACHINE_ID=    # el MISMO identificador de §1.3
AGENTE_DEVICE_ID=     # §2.4
```

`CLAUDE_BIN` lo resolvió el instalador y lo dejó en el LaunchAgent.

⚠️ Los comentarios de las variables vacías van **en la línea de arriba**. Al
lado de un valor vacío, `dotenv` toma el `# ...` como el valor, y el diagnóstico
da un OK falso.

## 2.4 · El `deviceId` de ese Chrome

Es el identificador que la extensión se asigna a sí misma. Sin él, con más de un
Chrome conectado a la cuenta, el modo headless no sabe a cuál ir.

```bash
grep -ao 'bridgeDeviceId.\{0,60\}' \
  ~/Library/Application\ Support/Google/Chrome/*/Local\ Extension\ Settings/fcoeoabgfenejglbffodgkkbkcdhcgfn/*.log
```

Sale el UUID a continuación de la clave. Ese valor va en `AGENTE_DEVICE_ID`.

**No sirve** listar los navegadores conectados a la cuenta: devuelve nombres
genéricos que no dicen cuál es cuál.

## 2.5 · ⚠️ Un solo perfil de Chrome, con las dos cosas

Este paso no estaba en el plan original y es el que rompe todo si se saltea.

**`LISTAR` usa la extensión. `ENVIAR` usa el navegador por CDP. Las dos van
contra el mismo Chrome**, así que el perfil que use el vendedor tiene que tener:

1. La extensión Claude in Chrome instalada
2. La sesión de WhatsApp Business iniciada

En la máquina donde se probó esto **estaban en perfiles distintos** —la extensión
en uno, la sesión en otro— y ninguna de las dos partes habría funcionado. Se ve
así:

```bash
# Perfiles con la extensión
ls -d ~/Library/Application\ Support/Google/Chrome/*/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn
```

```bash
# Perfiles con datos de WhatsApp Web
ls -d ~/Library/Application\ Support/Google/Chrome/*/IndexedDB/*whatsapp*
```

**Tiene que salir el mismo perfil en las dos.** Si no, instalá la extensión en el
perfil donde está WhatsApp, o iniciá WhatsApp en el perfil donde está la
extensión. Anotá cuál es: va en el arranque de Chrome, más abajo.

## 2.6 · Cómo tiene que arrancar Chrome

Para que Playwright pueda escribir el mensaje, Chrome necesita tres flags.
Desde Chrome 136 el puerto de depuración **se ignora en silencio** si no se pasa
`--user-data-dir` explícito: arranca, acepta el flag, y no abre el puerto.

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome" \
  --profile-directory="Default"
```

Reemplazá `Default` por el perfil de §2.5.

Se comprueba así, y tiene que devolver un JSON:

```bash
curl http://localhost:9222/json/version
```

⚠️ **Chrome tiene que estar cerrado del todo antes.** Si ya hay una instancia
corriendo, el comando le pide a esa que abra una ventana y el puerto no se
habilita.

## 2.7 · Los permisos, que son dos capas ⚠️

Este es el paso que más se olvida, porque uno de los dos **ya viene dado** y
parece que está todo.

| Capa | Quién la da | Estado habitual |
|---|---|---|
| Permiso de host de Chrome | Chrome, al instalar la extensión | ya viene: `<all_urls>` |
| **Lista de sitios de la extensión** | La extensión, a pedido | **falta** |

La que hay que dar: **ícono de Claude → configuración → permisos de sitios →
habilitar `web.whatsapp.com`.**

Sin eso el error es `Claude in Chrome requires permission`, **lo emite el
navegador y no el CLI**, así que no aparece en ningún log del agente.

Y el permiso MCP para headless, si el instalador lo marcó en rojo:

```bash
mkdir -p ~/.claude && echo '{"permissions":{"allow":["mcp__claude-in-chrome"]}}' > ~/.claude/settings.json
```

## 2.8 · Comprobar antes de arrancar

```bash
./agente/.venv/bin/python -m agente.main --diagnostico
```

Los cinco que se verifican leyendo archivos tienen que estar en verde.

Y después el único que comprueba los dos de §2.7:

```bash
./agente/.venv/bin/python -m agente.main --sonda
```

```
[OK ] permiso_sitio    la extensión puede entrar a web.whatsapp.com
[OK ] whatsapp_sesion  sesión iniciada, N chats a la vista
```

Abre WhatsApp Web una vez, cuenta los chats y no lee ninguno. Cuesta alrededor
de USD 0,50 y tarda un par de minutos: por eso no está adentro del diagnóstico.

Si falla, distingue los tres casos, que se arreglan distinto:

| Motivo | Qué hacer |
|---|---|
| `sin_permiso` | Falta §2.7 |
| `sesion_no_iniciada` | WhatsApp Web pide QR |
| `browser_no_disponible` | El `deviceId` de §2.4 no es el de este Chrome |

## 2.9 · Arrancar

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.centonara.agente.plist
```

```bash
launchctl print gui/$(id -u)/com.centonara.agente | head -20
```

A partir de acá **arranca solo cada vez que el vendedor inicia sesión**, y si el
proceso muere `launchd` lo vuelve a levantar.

Los logs, en `~/Library/Logs/centonara/`. Para pararlo:

```bash
launchctl bootout gui/$(id -u)/com.centonara.agente
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
