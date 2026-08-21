# 07 — El agente

> El componente que corre en la PC de cada vendedor. Es el que toca el mundo real, así que es el
> que más cuidado necesita.

---

## 1. Qué es

Un ejecutable de Python (empaquetado con PyInstaller) que:

1. Arranca solo cuando el vendedor inicia sesión en Windows
2. Le pregunta al backend cada 10 segundos si hay trabajo
3. Ejecuta ese trabajo contra el Chrome de esa máquina
4. Reporta el resultado
5. Muestra un ícono en la bandeja del sistema

El vendedor **no abre una terminal, no ejecuta un `.bat`, no escribe nada**. Prende la
computadora, loguea, y el sistema ya funciona.

---

## 2. Arranque automático — el detalle que hay que entender

### No puede ser un Servicio de Windows

Chrome, la extensión y el native messaging viven en la **sesión interactiva del usuario**. Un
servicio corriendo como `SYSTEM` en la sesión 0 no ve ese Chrome. Esto no se puede sortear con
configuración: es cómo funciona el aislamiento de sesiones de Windows.

Si alguien propone usar NSSM o `sc create`, la respuesta es que ya se evaluó y no sirve.

### La solución: Task Scheduler

```
Trigger:    At log on  →  usuario específico
Action:     "C:\Program Files\SeguimientoAgente\agente.exe"
Conditions: (desmarcar "Start only if on AC power")
Settings:   Allow task to be run on demand
            If the task fails, restart every 1 minute, up to 3 times
            Run only when user is logged on
            Hidden
```

Lo configura el instalador. No es un paso manual del SOP.

---

## 3. Ciclo de vida

```
ARRANQUE
  ├─ leer configuración local (%PROGRAMDATA%\SeguimientoAgente\config.json)
  ├─ POST /api/agent/registrar
  ├─ autodiagnóstico completo
  ├─ si hay versión nueva → autoactualizar y reiniciar
  └─ mostrar ícono en la bandeja

BUCLE (para siempre)
  ├─ GET /api/agent/jobs/next        (long-poll, 25 s)
  │    ├─ 204 → volver a preguntar
  │    ├─ 423 → pausa global, esperar 60 s
  │    └─ 200 → ejecutar el job
  ├─ POST /api/agent/jobs/{id}/result
  └─ cada 30 s: POST /api/agent/heartbeat

APAGADO
  └─ si hay un job en curso: abortarlo y reportarlo como FALLIDO
     (nunca dejar un envío a medias sin reportar)
```

---

## 4. Autodiagnóstico

Se ejecuta al arrancar, cada hora, y **siempre antes de un job de envío**. Cada chequeo
corresponde a un problema que ya ocurrió en el MVP.

| Chequeo | Qué verifica | Problema del MVP que previene |
|---|---|---|
| `claude_bin_ok` | `CLAUDE_BIN` apunta a un ejecutable válido | #2 — `shutil.which("claude")` devolvía `None` |
| `permiso_mcp_ok` | `~/.claude/settings.json` tiene `mcp__claude-in-chrome` en `allow` | #3 — headless auto-deniega acciones |
| `permiso_sitio_ok` | La extensión tiene permiso para `web.whatsapp.com` | #4 — capa distinta de la #3 |
| `device_id_ok` | `deviceId` está fijado | #5 — "dos navegadores conectados" |
| `chrome_ok` | Chrome corriendo y accesible | — |
| `whatsapp_sesion_ok` | Sesión activa, no pide QR | — |
| `claude_md_ok` | Existe `CLAUDE.md` en la carpeta del agente | #7 — el modelo se niega sin contexto verificable |

**Si algún chequeo falla, el agente no toma jobs de envío** y reporta `degradado`. El panel lo
muestra en rojo con el chequeo específico que falló, no un "error" genérico.

Los siete problemas del historial del MVP dejan de ser un HTTP 502 mudo y pasan a ser un mensaje
claro en una pantalla.

---

## 5. Ejecución de `LISTAR_CHATS`

Es el único job que sigue usando `claude -p --chrome`. Se conserva el enfoque del MVP porque está
validado.

```python
proc = subprocess.run(
    [CLAUDE_BIN, "-p", "--chrome", "--output-format", "json"],
    input=prompt,              # ⚠ por stdin, NUNCA como argumento
    capture_output=True,
    text=True,
    encoding="utf-8",          # ⚠ sin esto Windows usa cp1252 y rompe los acentos
    errors="replace",
    timeout=TIMEOUT,
    cwd=str(CARPETA_AGENTE),   # para que encuentre CLAUDE.md
)
```

> **Los dos comentarios de arriba no son opcionales.** En el MVP, pasar el prompt como argumento
> hacía que `cmd.exe` cortara el comando en el primer salto de línea ("Tu mensaje se cortó"), y sin
> `encoding="utf-8"` los acentos se rompían. Es el problema #6 del historial.

---

## 6. Ejecución de `ENVIAR` — Playwright

**Este código no existe hasta el Sprint 4** (regla R7).

### Secuencia obligatoria

```python
async def enviar(contacto_id: str, contacto_nombre: str, texto: str, modo: str):
    # 1. Abrir WhatsApp Web (sesión ya iniciada)
    # 2. Buscar el contacto por identificador
    # 3. Abrir el chat
    # 4. LEER el header del chat abierto
    # 5. RESOLVER el número a E.164
    encontrado = await resolver_numero_del_chat_abierto(page)
    if encontrado is None:
        return Resultado(ok=False, codigo="NUMERO_NO_RESOLUBLE")
    # 6. COMPARAR — el paso más importante del sistema
    if encontrado != contacto_id:
        return Resultado(ok=False, codigo="CONTACTO_NO_COINCIDE",
                         esperado=contacto_id, encontrado=encontrado)
    # 7. Verificar que el campo de escritura está vacío
    if await campo_tiene_texto(page):
        return Resultado(ok=False, codigo="CAMPO_NO_VACIO")
    # 8. Escribir el texto EXACTO
    await escribir(page, texto)          # sin reformular, sin completar nada
    # 9. En modo prueba: reportar y salir SIN enviar
    if modo == "prueba":
        return Resultado(ok=True, simulado=True, texto_escrito=texto)
    # 10. Enviar
    await apretar_enviar(page)
    # 11. Confirmar que aparece en el hilo
    if not await confirmar_en_hilo(page, texto, timeout=15):
        return Resultado(ok=False, codigo="ENVIO_NO_CONFIRMADO")
    return Resultado(ok=True)
```

El paso 6 es el que impide el peor error posible del sistema. Tiene su propio test y su propia
revisión de código obligatoria por dos personas.

### Selectores

Viven en **un solo archivo**, `agente/adaptadores/selectores.py`, con la fecha de última
verificación. Cuando WhatsApp Web cambie —va a cambiar—, se toca un solo lugar.

Un job `SMOKE_TEST` corre todos los días a las 07:00 y verifica que los selectores siguen
funcionando. Si fallan, el equipo se entera **antes** de la corrida de las 13:00, no después.

### Falla cerrada, siempre

Si un selector no aparece, el agente **aborta**. Nunca "sigue de largo por las dudas". Un
`except: pass` en este archivo es un incidente, no un bug.

---

## 7. Conexión al Chrome — decisión del Sprint 4

Dos caminos posibles. **El Sprint 4 arranca con un spike de 2 días para elegir.**

| | A — CDP sobre el Chrome del vendedor | B — Perfil persistente dedicado |
|---|---|---|
| Cómo | Chrome con `--remote-debugging-port=9222`, Playwright se conecta | Playwright maneja su propio perfil |
| Ventaja | El vendedor usa su Chrome de siempre | Aislado, estable, predecible |
| Riesgo | Si cierra Chrome, se pierde la sesión | Un segundo Chrome abierto, un segundo QR |
| Interferencia | El vendedor puede estar escribiendo en el mismo chat | Ninguna |

**Recomendación inicial: B.** Aísla el sistema del comportamiento del vendedor, y el riesgo de que
alguien esté escribiendo en el mismo chat en el que vamos a escribir nosotros es real.

Criterio de decisión del spike: cuál de los dos sobrevive a que el vendedor cierre el navegador,
reinicie la máquina y trabaje normalmente durante 4 horas.

---

## 8. Ícono en la bandeja

Pequeño en esfuerzo, grande en soporte y en confianza del vendedor.

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

Estados del ícono: 🟢 conectado · 🟡 degradado (algún chequeo falla) · 🔴 sin conexión ·
⏸️ pausado.

"Pausar por hoy" le da al vendedor control real y visible sobre algo que corre en su máquina. El
SOP le promete transparencia; esto la hace real.

---

## 9. Autoactualización

Al arrancar y a las 03:00, el agente consulta su versión contra el backend. Si hay una nueva:
descarga, **valida el hash SHA-256**, reemplaza el ejecutable y se reinicia.

Con 8 máquinas distribuidas, actualizar a mano no es opción. La validación del hash tampoco es
opcional: es un ejecutable que se instala solo en la máquina de otra persona.

---

## 10. Instalación en una máquina nueva

El SOP del MVP tenía 12 pasos. El objetivo es **3**:

1. Ejecutar el instalador
2. Pegar el token que le pasó el administrador
3. Escanear el QR de WhatsApp Web

El instalador hace todo lo demás: instala el ejecutable, crea la tarea programada, escribe
`settings.json` con el permiso MCP, fija el `deviceId`, verifica la versión de Chrome, y corre el
autodiagnóstico mostrando qué falta.

### Requisitos de entorno, ya resueltos en el MVP

| Ítem | Detalle |
|---|---|
| Plan Anthropic | **8 asientos individuales, uno por máquina** (decisión D2). Una API key **no sirve**: desactiva la integración con Chrome |
| `~/.claude/settings.json` | `{"permissions":{"allow":["mcp__claude-in-chrome"]}}` — sin esto, headless auto-deniega |
| Permiso de sitio | Manual en la extensión, para `web.whatsapp.com`. **Capa independiente** de la anterior |
| `deviceId` | Fijo por máquina. Con más de un Chrome, headless no sabe cuál usar |
| Windows | **Nativo, no WSL** |

Sobre los 8 asientos: una sola cuenta compartida entre 8 equipos tiene un problema de términos de
servicio y otro de límites de uso. Se compra un asiento por máquina.
