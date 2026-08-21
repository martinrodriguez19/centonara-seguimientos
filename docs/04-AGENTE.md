# 04 — El agente (macOS) y el entorno local

> El componente que corre en la Mac de cada vendedor. Es el que toca el mundo real, así que es el
> que más cuidado necesita.
>
> **Todo lo que decía la versión anterior sobre Windows —Task Scheduler, `%PROGRAMDATA%`, servicios
> de Windows, Inno Setup— no aplica.** El parque es macOS.

---

## 1. Qué es

Un programa Python que:

1. Arranca solo cuando el vendedor inicia sesión en la Mac
2. Le pregunta al backend cada 10 segundos si hay trabajo
3. Ejecuta ese trabajo contra el Chrome de esa máquina
4. Reporta el resultado
5. Muestra un ícono en la barra de menú

El vendedor **no abre una terminal ni ejecuta nada**. Prende la computadora, loguea, y el sistema
ya funciona.

---

## 2. Arranque automático en macOS: `launchd`

macOS no tiene Task Scheduler. Lo equivalente es un **LaunchAgent**: un `.plist` en
`~/Library/LaunchAgents/`, que corre **en la sesión del usuario**.

Esa última parte no es un detalle. Chrome, la extensión y el native messaging viven en la sesión
interactiva del usuario. Un LaunchDaemon (el equivalente a un servicio de sistema, en
`/Library/LaunchDaemons/`) corre fuera de esa sesión y **no ve ese Chrome**. Es el mismo problema
que en Windows, con otros nombres. Si alguien propone un LaunchDaemon, la respuesta es no.

```xml
<!-- ~/Library/LaunchAgents/com.centonara.agente.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
  <key>Label</key>            <string>com.centonara.agente</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/centonara/venv/bin/python</string>
    <string>-m</string>
    <string>agente.main</string>
  </array>
  <key>WorkingDirectory</key> <string>/opt/centonara/agente</string>
  <key>RunAtLoad</key>        <true/>
  <key>KeepAlive</key>        <true/>   <!-- si muere, launchd lo vuelve a levantar -->
  <key>StandardOutPath</key>  <string>/opt/centonara/logs/agente.log</string>
  <key>StandardErrorPath</key><string>/opt/centonara/logs/agente.err</string>
</dict>
</plist>
```

Se carga con `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.centonara.agente.plist`.

### Nada de PyInstaller, al menos por ahora

La versión anterior planeaba empaquetar con PyInstaller y distribuir un ejecutable con
autoactualización que valida hash SHA-256. En macOS eso trae un problema que no existe en Windows:
**Gatekeeper**. Un binario sin firmar y sin notarizar exige que el usuario lo abra a mano la
primera vez, y —peor— cada vez que la autoactualización reemplace el archivo, vuelve a quedar en
cuarentena. Firmar y notarizar requiere una cuenta de Apple Developer y un paso de build extra.

Con pocas máquinas de una misma oficina, el camino más corto es mejor:

```
/opt/centonara/
├── agente/          ← un git clone del repositorio
├── venv/            ← entorno virtual con las dependencias
├── config.json      ← lo escribe el instalador: token, máquina, backend
└── logs/
```

Actualizar es `git pull && launchctl kickstart -k gui/$(id -u)/com.centonara.agente`, y eso se
puede hacer como un job `ACTUALIZAR` que el propio agente ejecuta cuando el panel lo pide.

Se revisa el día que haya suficientes máquinas como para que eso moleste.

### Permisos de macOS que hay que conceder una vez

macOS pide permisos que Windows no. Se conceden en Ajustes del Sistema › Privacidad y seguridad, y
**el instalador tiene que verificarlos y decir cuál falta**, no fallar en silencio:

| Permiso | Para qué | Se pide desde |
|---|---|---|
| Automatización | que el proceso controle Chrome | primera ejecución |
| Acceso total al disco | leer el perfil de Chrome, según cómo conectemos | Ajustes |
| Ítem de inicio | que el LaunchAgent corra al loguear | Ajustes › General › Ítems de inicio |

Ninguno de estos aparece en el historial del MVP porque el MVP era Windows. **Es la lista que hay
que descubrir en F5.1**, la primera vez que el agente corra en una Mac. Hasta entonces el
diagnóstico reporta `n/a` para estos chequeos y el agente funciona igual en Windows.

---

## 3. Ciclo de vida

```
ARRANQUE
  ├─ leer /opt/centonara/config.json
  ├─ POST /api/agente/registrar
  ├─ diagnóstico completo
  └─ mostrar ícono en la barra de menú

BUCLE (para siempre)
  ├─ GET /api/agente/jobs/proximo
  │    ├─ 204 → esperar 10 s y volver a preguntar
  │    ├─ 423 → pausa global, esperar 60 s
  │    └─ 200 → ejecutar el job
  ├─ POST /api/agente/jobs/{id}/resultado
  └─ cada 30 s: POST /api/agente/latido

APAGADO
  └─ si hay un job en curso: abortarlo y reportarlo como fallido
     (nunca dejar un envío a medias sin reportar)
```

---

## 4. Diagnóstico

Se ejecuta al arrancar, cada hora, y **siempre antes de un job de envío**. Cada chequeo
corresponde a un problema que ya ocurrió, o que macOS agrega.

| Chequeo | Qué verifica | Origen |
|---|---|---|
| `claude_bin` | `CLAUDE_BIN` apunta a un ejecutable válido | MVP #2: `which("claude")` devolvía `None` |
| `permiso_mcp` | `~/.claude/settings.json` tiene `mcp__claude-in-chrome` en `allow` | MVP #3: headless auto-deniega |
| `permiso_sitio` | La extensión tiene permiso para `web.whatsapp.com` | MVP #4: capa distinta de la anterior |
| `device_id` | El `deviceId` del Chrome de esta Mac está fijado | MVP #5: "dos navegadores conectados" |
| `chrome` | Chrome corriendo y accesible | — |
| `whatsapp_sesion` | Sesión activa, no pide QR | — |
| `claude_md` | Existe `CLAUDE.md` en la carpeta del agente | MVP #7: sin contexto verificable el modelo se niega |
| `permisos_macos` | Automatización concedida | **nuevo en macOS** |
| `selectores` | Los selectores de WhatsApp Web siguen respondiendo | evita `SELECTOR_ROTO` a mitad de corrida |

**Si algún chequeo falla, el agente no toma jobs de envío** y se reporta degradado. El panel
muestra qué chequeo específico falló, no un "error" genérico. Esa es la diferencia entre el MVP,
donde los siete problemas eran un HTTP 502 mudo, y esto.

### Dos problemas del MVP que desaparecen en Mac

- **"Tu mensaje se cortó"**: era `cmd.exe` cortando el comando en el primer salto de línea. En
  macOS no existe. **Igual el prompt va por stdin**, porque es lo correcto y porque el código es
  compartido.
- **Acentos rotos**: era `cp1252`. macOS usa UTF-8. **Igual se fija `encoding="utf-8"`**, por lo
  mismo.

---

## 5. Ejecución de `LISTAR`

El único job que usa `claude -p --chrome`. Se conserva el enfoque del MVP porque está validado.

```python
proc = subprocess.run(
    [CLAUDE_BIN, "-p", "--chrome", "--output-format", "json"],
    input=prompt,              # por stdin, NUNCA como argumento
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=TIMEOUT,
    cwd=str(CARPETA_AGENTE),   # para que encuentre CLAUDE.md
)
```

El prompt es **fijo y vive en disco** (`agente/prompts/prompt-listar.txt`). El backend manda
variables acotadas (`n_chats`, `run_id`) que se sustituyen acá. El agente nunca ejecuta texto que
vino por la red.

Una salida que no parsea se reporta como fallo **con el `raw` completo**, sin reventar el agente.

---

## 6. Ejecución de `REDACTAR`

Sin navegador. Llamada de texto plano con el contexto que ya extrajo `LISTAR`.
`agente/prompts/prompt-redactar.txt`, un job por chat.

Criterio verificable: redactar 20 borradores no abre ninguna pestaña. Es donde está el ahorro de
costo del proyecto.

---

## 7. Ejecución de `ENVIAR` — Playwright

### La secuencia, y su orden no se negocia

```python
async def enviar(contacto_id: str, contacto_nombre: str, texto: str, modo: str):
    # 0. El destino está en la lista permitida (R4). Si no: abortar
    if not destino_permitido(contacto_id):
        return Resultado(ok=False, codigo="DESTINO_NO_PERMITIDO")
    # 1-3. Abrir WhatsApp Web, buscar el contacto, abrir el chat
    # 4. LEER el header del chat abierto
    # 5. RESOLVER el número a E.164
    encontrado = await resolver_numero_del_chat_abierto(page)
    if encontrado is None:
        return Resultado(ok=False, codigo="NUMERO_NO_RESOLUBLE")
    # 6. COMPARAR — el paso más importante del sistema (R1)
    if encontrado != contacto_id:
        return Resultado(ok=False, codigo="CONTACTO_NO_COINCIDE",
                         esperado=contacto_id, encontrado=encontrado)
    # 7. El campo de escritura está vacío
    if await campo_tiene_texto(page):
        return Resultado(ok=False, codigo="CAMPO_NO_VACIO")
    # 8. Escribir el texto EXACTO: sin reformular, sin completar nada
    await escribir(page, texto)
    # 9. En modo prueba: reportar y salir SIN enviar
    if modo == "prueba":
        return Resultado(ok=True, simulado=True, texto_escrito=texto)
    # 10. Enviar
    await apretar_enviar(page)
    # 11. Confirmar que apareció en el hilo
    if not await confirmar_en_hilo(page, texto, timeout=15):
        return Resultado(ok=False, codigo="SIN_CONFIRMAR")
    return Resultado(ok=True)
```

Los pasos 0 y 6 son los que impiden el peor error posible. Tienen su propio test y su propia
revisión de código.

**Casos adversos que tienen que abortar correctamente:** dos contactos con el mismo nombre,
contacto sin nombre agendado (sólo número), un grupo, un número que no tiene WhatsApp, un chat
archivado.

### Selectores

Viven en **un solo archivo**, `agente/adaptadores/selectores.py`, con la fecha de última
verificación. Ningún selector puede aparecer fuera de ahí. Cuando WhatsApp Web cambie —va a
cambiar— se toca un solo lugar.

### Falla cerrada, siempre

Si un selector no aparece, el agente **aborta**. Nunca "sigue de largo por las dudas". Un
`except: pass` en este archivo es un incidente, no un bug.

---

## 8. Conexión al Chrome

Dos caminos posibles. **F4.2 decide con evidencia, no con opinión** — y se puede decidir en
Windows: lo que cambia en macOS es cómo se lanza Chrome con la bandera, no cuál estrategia es
mejor.

| | A — CDP sobre el Chrome del vendedor | B — Perfil dedicado de Playwright |
|---|---|---|
| Cómo | Chrome con `--remote-debugging-port=9222`, Playwright se conecta | Playwright maneja su propio perfil |
| Ventaja | El vendedor usa su Chrome de siempre. Un solo WhatsApp vinculado | Aislado, estable, predecible |
| Riesgo | Si cierra Chrome se pierde la sesión. Interfiere si está escribiendo | Un segundo Chrome y **un segundo QR** |
| En macOS | Hay que lanzar Chrome con la bandera, lo que implica tocar cómo lo abre el vendedor | Independiente de cómo el vendedor usa su Chrome |

**Recomendación inicial: B**, por el aislamiento. Pero tiene un costo que hay que decir en voz
alta: **es un segundo dispositivo vinculado a la línea del vendedor.** WhatsApp permite cuatro, así
que entra, pero ocupa un lugar y es una sesión más que puede caerse sin que nadie la vea. Por eso
`whatsapp_sesion` está en el diagnóstico.

Criterio de decisión: cuál de los dos sobrevive a que el vendedor cierre el navegador, reinicie la
Mac y trabaje normalmente durante media jornada.

---

## 9. Ícono en la barra de menú

Chico en esfuerzo, grande en soporte y en confianza del vendedor.

```
🟢 Seguimiento — conectado
   ├─ Estado: OK
   ├─ WhatsApp: sesión activa
   ├─ Última corrida: hoy 13:04 — 17 enviados, 0 fallidos
   ├─ ─────────────
   ├─ Pausar por hoy
   ├─ Ver estado en el panel
   └─ Salir
```

Estados: 🟢 conectado · 🟡 degradado (algún chequeo falla) · 🔴 sin conexión · ⏸️ pausado.

"Pausar por hoy" le da al vendedor control real sobre algo que corre en su máquina. Se implementa
con `rumps`, que es la forma corta de hacer un ítem de barra de menú en Python.

---

## 10. Instalación en una Mac nueva

Objetivo: tres pasos.

1. Correr el instalador (`curl … | bash`, o un script del repositorio)
2. Pegar el token que generó el panel al dar de alta la máquina
3. Escanear el QR de WhatsApp Web

El instalador hace el resto: clona, crea el entorno virtual, escribe `config.json`, escribe
`~/.claude/settings.json` con el permiso MCP, fija el `deviceId`, instala el LaunchAgent, y corre
el diagnóstico **mostrando qué falta**, incluidos los permisos de macOS que hay que conceder a
mano.

### Requisitos por máquina

| Ítem | Detalle |
|---|---|
| Cuenta de Claude | **Una por máquina**, del Enterprise del cliente (D2). Una API key **no sirve**: desactiva la integración con Chrome |
| `~/.claude/settings.json` | `{"permissions":{"allow":["mcp__claude-in-chrome"]}}` |
| Permiso de sitio | Manual en la extensión, para `web.whatsapp.com`. **Capa independiente** de la anterior |
| `deviceId` | Fijo por máquina. Con más de un Chrome, headless no sabe cuál usar |
| Permisos de macOS | Automatización, e ítem de inicio |

Sobre las cuentas: el cliente tiene Claude Enterprise, así que no hay que comprar suscripciones
sueltas — hay que asignarle un asiento a cada vendedor. Lo que sí hay que confirmar con el
administrador de la organización es que **la extensión Claude in Chrome esté habilitada por
política**: si está restringida, el sistema no funciona en ninguna máquina y no es algo que se
arregle desde el código. Ver D2.

Una cuenta compartida entre varias máquinas no sirve: además del problema de términos de servicio,
las máquinas compiten por la misma cuota y se frenan entre ellas justo cuando corren todas juntas,
que es siempre.

---

## 11. Entorno local de desarrollo

El agente corre igual en Linux, macOS y Windows en **modo simulado**, que es como trabaja todo el
equipo hasta que hay una Mac de pruebas disponible.

```bash
cp .env.example .env
docker compose -f infra/docker-compose.dev.yml up -d   # MongoDB, con autenticación
cd backend && uv sync && uv run fastapi dev app/main.py
cd frontend && pnpm install && pnpm dev
cd agente && uv sync && uv run python -m agente.main --simulado
```

**Node 22 o superior, no negociable.** Es el problema #1 del historial del MVP.

El Compose local ya no levanta n8n ni Mailpit: no hay n8n, y no hay correo saliente.

**El Mongo local levanta con autenticación**, y crea solo el usuario `app` con su rol. No es
paranoia sobre un contenedor que escucha en localhost: el registro de auditoría es inmutable
gracias a un rol de MongoDB, y un servidor sin `--auth` no aplica roles. Sin eso, el test que
verifica la inmutabilidad pasaría en verde sin probar nada. Ver `RUNBOOK-auditoria.md`.

Para correr los tests que necesitan base:

```bash
cd backend
MONGO_URL_TESTS="mongodb://root:root-local@localhost:27017/?authSource=admin" uv run pytest -q
```

Sin esa variable, esos tests se saltean y el resto corre igual.

Los jobs `LISTAR`, `REDACTAR` y `ENVIAR` sólo se pueden ejecutar de verdad en una Mac con Chrome,
la extensión y una sesión de WhatsApp. En cualquier otro lado, el diagnóstico reporta `n/a` y el
agente no toma esos jobs.
