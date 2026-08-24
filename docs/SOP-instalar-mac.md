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

## 0. Lo que hay que tener a mano

| | |
|---|---|
| Cuenta de Claude | **Una por máquina**, del Enterprise del cliente (D2). Una API key **no sirve**: desactiva la integración con Chrome |
| Chrome | Con la extensión Claude in Chrome instalada |
| WhatsApp Web | Con la sesión de **esa** línea iniciada, sin QR pendiente |
| La URL del backend | Ver §2 |

Y confirmar con el administrador de la organización que la extensión esté
**habilitada por política**. Si está restringida, no funciona en ninguna máquina
y no se arregla desde el código.

---

## 1. Instalar las herramientas

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
npm install -g @anthropic-ai/claude-code
```

Y clonar el repositorio donde vaya a vivir:

```bash
git clone https://github.com/martinrodriguez19/centonara-seguimientos.git
cd centonara-seguimientos
```

---

## 2. Elegir contra qué backend va a trabajar

Dos opciones, y la diferencia importa.

**Producción** — es lo que va a usar el cliente:

```
AGENTE_BACKEND_URL=https://backend-produccion-7yqr.onrender.com
```

⚠️ La URL lleva sufijo. `backend-produccion.onrender.com` **es de otra
persona**: el nombre estaba tomado y Render asignó otro. Nunca usar la de
adelante.

**Una máquina de desarrollo en la misma red** — para probar sin depender del
despliegue:

```
AGENTE_BACKEND_URL=http://192.168.x.x:8000
```

Requiere que el backend escuche en `0.0.0.0` y que el firewall deje pasar el
puerto. Se comprueba desde la Mac con:

```bash
curl http://192.168.x.x:8000/health
```

Tiene que devolver `{"ok":true,"mongo":true,...}`. Si dice `mongo:false`, la base
de esa máquina no está levantada y el agente no va a poder hacer nada.

---

## 3. Dar de alta la máquina en el panel

En el panel, **Dar de alta una máquina**:

- **Identificador** — minúsculas, números y guiones. `mac-rocio`, no
  `Mac de Rocío`. Es lo que se ve en logs y URLs.
- **Nombre del vendedor** — acá sí va con mayúsculas y acentos.
- **Línea de WhatsApp** — opcional.

⚠️ **El token se muestra una sola vez.** Se guarda hasheado y no se puede
recuperar; si se pierde, se rota y hay que reconfigurar la máquina.

La máquina **nace inactiva**. Instalar no es activar.

---

## 4. Correr el instalador

```bash
bash agente/instalador/instalar-mac.sh
```

Verifica las herramientas, crea el entorno, escribe el LaunchAgent con **rutas
absolutas** y corre el diagnóstico. No arranca nada.

Lo de las rutas absolutas no es cosmético: `launchd` no tiene el PATH de una
terminal, y `claude` a secas se resuelve a `None`. Es el problema #2 del MVP, el
que hace que ande a mano y falle cuando arranca solo.

---

## 5. Completar el `.env`

```bash
cp .env.example .env
```

Cuatro valores:

```
AGENTE_BACKEND_URL=   # el de §2
AGENTE_TOKEN=         # el que mostró el panel en §3
AGENTE_MACHINE_ID=    # el MISMO identificador de §3
AGENTE_DEVICE_ID=     # el de §6
```

`CLAUDE_BIN` lo resolvió el instalador y lo dejó en el LaunchAgent.

⚠️ Los comentarios de las variables vacías van **en la línea de arriba**. Al
lado de un valor vacío, `dotenv` toma el `# ...` como el valor, y el diagnóstico
da un OK falso.

---

## 6. El `deviceId` de ese Chrome

Es el identificador que la extensión se asigna a sí misma. Sin él, con más de un
Chrome conectado a la cuenta, el modo headless no sabe a cuál ir.

```bash
grep -ao 'bridgeDeviceId.\{0,60\}' \
  ~/Library/Application\ Support/Google/Chrome/*/Local\ Extension\ Settings/fcoeoabgfenejglbffodgkkbkcdhcgfn/*.log
```

Sale el UUID a continuación de la clave. Ese valor va en `AGENTE_DEVICE_ID`.

**No sirve** listar los navegadores conectados a la cuenta: devuelve nombres
genéricos que no dicen cuál es cuál.

---

## 7. Los permisos, que son dos capas ⚠️

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

---

## 8. Comprobar antes de arrancar

```bash
./agente/.venv/bin/python -m agente.main --diagnostico
```

Los cinco que se pueden verificar leyendo archivos tienen que estar en verde.

Y después el único que comprueba los dos de §7:

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
| `sin_permiso` | Falta §7 |
| `sesion_no_iniciada` | WhatsApp Web pide QR |
| `browser_no_disponible` | El `deviceId` de §6 no es el de este Chrome |

---

## 9. Arrancar

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

## 10. Activarla, que es una decisión aparte

En el panel, la máquina aparece **inactiva**. Recién cuando se la activa empieza
a tomar trabajo.

Antes de activarla, la conversación de consentimiento con el vendedor, registrada
(F5.7). El sistema **envía mensajes desde su línea, con su nombre**: eso tiene
que estar dicho y aceptado, no supuesto.

⚠️ Y si todavía circula el SOP viejo que dice *"No envía ningún mensaje. Nunca"*,
retirarlo de Drive, de los mails y de lo impreso. Dejó de ser cierto.

---

## 11. La primera corrida

Con `destinos_permitidos` en los números de prueba y **sólo esos**:

1. En el panel, apretar el botón.
2. El agente toma el `LISTAR` y lee los chats recientes. Tarda unos minutos.
3. Se encola un `REDACTAR` **sólo** por los chats cuyo número esté en
   `destinos_permitidos`. Los demás se cuentan y no se pagan.
4. Los borradores aparecen en la pantalla de revisión.

Lo que **no** va a pasar todavía: que salga un mensaje. `ENVIAR` se rechaza con
`falta adaptadores/whatsapp_web.py`, que es lo correcto hasta la fase 4.

---

## Si algo no anda

| Síntoma | Causa |
|---|---|
| `OPENSSL_Uplink(...): no OPENSSL_Applink` | Un antivirus dejó `SSLKEYLOGFILE` en el entorno. El agente ya la descarta al arrancar; si aparece igual, es otro proceso |
| `Claude in Chrome requires permission` | §7, la capa de la extensión |
| `token_rechazado` en el log | El token no es el de esta máquina, o se rotó |
| El agente no toma trabajo | La máquina está inactiva o pausada (§10), o el kill switch está puesto |
| `browser_no_disponible` | El `deviceId` es de otro Chrome |
| Arranca a mano y falla con launchd | Una ruta relativa en algún lado. Todo absoluto |
