# Especificación técnica — MVP Fase 2: envío automatizado

> **Uso:** pegar como primer mensaje de un chat nuevo. Escrito para que Claude
> pueda retomar el desarrollo sin haber participado de la sesión anterior.

---

## 1. Contexto

Sistema de asistencia comercial para 8 vendedores. Genera borradores de mensajes de
seguimiento de WhatsApp y —en esta fase— los envía.

### Fase 1 (COMPLETADA Y VALIDADA)

Arquitectura funcionando end-to-end en 1 máquina Windows 11:

```
n8n → HTTP POST → agent.py (Python, puerto 8787) → claude -p --chrome
    → extensión Claude in Chrome → web.whatsapp.com (SOLO LECTURA)
```

Resultado validado: 5 chats leídos, 5 borradores contextualizados generados,
calidad utilizable.

**Restricción actual del prompt:** "NO envies ningun mensaje, NO toques el campo de
escritura, NO hagas click en enviar."

### Fase 2 (A DESARROLLAR)

Agregar envío. Volumen objetivo: **15–20 mensajes por vendedor por día**.

---

## 2. Estado actual del código

### `agent.py` (funcionando)

Servidor HTTP stdlib, sin dependencias. Endpoints:

- `GET /health` → `{"ok": true, "machine": "PC-1", "claude": "2.x.x"}`
- `POST /run` → ejecuta el prompt, devuelve JSON

Detalles de implementación relevantes:

```python
# El prompt vive en disco. n8n solo manda variables acotadas.
ALLOWED_VARS = {"n_chats", "run_id"}

# CRÍTICO en Windows: el prompt va por stdin, NO como argumento.
# claude.CMD pasa por cmd.exe, que corta el comando en el primer salto de línea.
proc = subprocess.run(
    [CLAUDE_BIN, "-p", "--chrome", "--output-format", "json"],
    input=prompt,
    capture_output=True,
    text=True,
    encoding="utf-8",   # sin esto Windows usa cp1252 y rompe acentos
    errors="replace",
    timeout=TIMEOUT,
    cwd=str(Path(__file__).parent),
)
```

Variables de entorno: `AGENT_TOKEN`, `DEVICE_ID`, `CLAUDE_BIN`, `MACHINE_NAME`,
`MODEL`, `AGENT_PORT`, `RUN_TIMEOUT`.

### `prompt.txt` (funcionando, a extender)

Placeholders: `{{DEVICE_ID}}`, `{{N_CHATS}}`, `{{RUN_ID}}`.
Devuelve JSON con `contacto`, `ultimo_mensaje_resumen`, `ultimo_lo_mando`,
`antiguedad`, `template_seguimiento`.

### `CLAUDE.md`

Contexto del proyecto en la carpeta del agente. **Necesario**: sin él Claude Code se
niega a ejecutar la tarea por falta de contexto verificable (ver sección 7).

### Requisitos de entorno ya resueltos

| Ítem | Detalle |
|---|---|
| Plan Anthropic | Pro/Max/Team. **API key NO sirve**: desactiva la integración de Chrome |
| `~/.claude/settings.json` | `{"permissions":{"allow":["mcp__claude-in-chrome"]}}` — sin esto, headless auto-deniega |
| Permiso de sitio | manual en la extensión, para `web.whatsapp.com`. Capa **independiente** de la anterior |
| `deviceId` | fijar por máquina. Con >1 Chrome, headless no sabe cuál usar y frena |
| Windows | nativo, **no WSL** |

---

## 3. Objetivo de la Fase 2

Que el sistema envíe los mensajes aprobados, en lugar de solo redactarlos.

### Flujo objetivo

```
1. GENERAR   → como hoy: leer chats, redactar borradores          [validado]
2. APROBAR   → checkpoint humano: revisar y marcar cuáles salen   [a construir]
3. ENVIAR    → escribir y enviar solo los aprobados               [a construir]
4. REGISTRAR → log de qué se envió, a quién, cuándo               [a construir]
```

### El checkpoint de aprobación es requisito, no opcional

Razón técnica: el `settings.json` de cada máquina pre-aprueba todas las acciones de
navegador (necesario para que el modo headless funcione). Sin un checkpoint externo,
no queda ninguna barrera entre un prompt mal ajustado y 160 mensajes diarios
enviados a clientes reales.

El checkpoint puede ser mínimo —un botón de aprobar en n8n o una columna en una
planilla— pero tiene que existir y ser explícito.

---

## 4. A desarrollar

### 4.1 Separar generación de envío

Dos endpoints en lugar de uno:

- `POST /generar` → lo que hoy hace `/run` (sin cambios)
- `POST /enviar` → recibe una lista de mensajes aprobados y los envía

Motivo: hoy todo pasa en una sola invocación de Claude. Si la generación y el envío
van juntos, no hay dónde meter la aprobación.

Contrato propuesto para `/enviar`:

```json
{
  "run_id": "20260805-142648",
  "mensajes": [
    {"contacto": "Rocio", "texto": "Hola Rocio, ..."},
    {"contacto": "+54 9 11 3927-3345", "texto": "Hola, ..."}
  ]
}
```

Respuesta:

```json
{
  "ok": true,
  "machine": "PC-1",
  "enviados": [{"contacto": "Rocio", "estado": "enviado", "timestamp": "..."}],
  "fallidos": [{"contacto": "...", "estado": "error", "motivo": "..."}]
}
```

### 4.2 `prompt-enviar.txt`

Prompt nuevo, separado del de generación. Requisitos:

- Abrir el chat del contacto especificado (por nombre exacto, tal como figura en la lista)
- **Verificar que el chat abierto corresponde al contacto** antes de escribir. Si no
  coincide, abortar ese envío y reportarlo. Es el punto de falla más peligroso:
  escribir en el chat equivocado.
- Escribir el texto exacto recibido. No reformularlo, no completar placeholders.
- Enviar
- Confirmar visualmente que el mensaje salió (aparece en el hilo)
- Devolver JSON con el resultado por contacto

### 4.3 Validaciones antes de enviar

En `agent.py`, sobre cada mensaje de la lista:

- Rechazar si el texto contiene `{nombre}` u otros placeholders sin resolver
- Rechazar si el texto está vacío o supera un largo máximo configurable
- Tope duro de mensajes por corrida (sugerido: 25) y por día por máquina
- Rechazar si el `run_id` no corresponde a una generación previa

### 4.4 Ritmo de envío

Configurable, con valores por defecto conservadores:

- Pausa aleatoria entre envíos (sugerido: 45–180 segundos, no fijo)
- Ventana horaria permitida (ej. 9:00–19:00, días hábiles)
- Orden aleatorizado de la lista, no siempre el mismo

Motivo en sección 7.

### 4.5 Registro

Log persistente por máquina y consolidado en n8n:

```json
{"timestamp": "...", "machine": "PC-1", "run_id": "...",
 "contacto": "...", "texto": "...", "estado": "enviado|fallido", "motivo": "..."}
```

Necesario para: auditar qué se mandó, detectar duplicados, y responder si un cliente
se queja.

### 4.6 Anti-duplicados

No enviar dos veces al mismo contacto en una ventana configurable (sugerido: 7 días),
aunque aparezca en la lista de otra corrida.

---

## 5. Workflow n8n

```
[Cron 8:00]
   → [POST /generar]  a cada máquina, en paralelo
   → [Normalizar]     una fila por chat
   → [Guardar]        planilla o base, estado = "pendiente"
   → [Notificar]      avisar que hay borradores para revisar
   
   ... intervención humana: aprobar / editar / descartar ...
   
[Disparo manual o cron 10:00]
   → [Leer aprobados]
   → [Agrupar por máquina]
   → [POST /enviar]   a cada máquina
   → [Registrar]      resultado de cada envío
   → [Alertar]        si hay fallidos
```

---

## 6. Criterios de aceptación

- [ ] `/generar` sigue funcionando igual que hoy
- [ ] `/enviar` envía solo mensajes previamente aprobados
- [ ] Un mensaje con placeholder sin resolver se rechaza antes de enviarse
- [ ] El sistema verifica que el chat abierto es el correcto antes de escribir
- [ ] Se respeta el tope diario por máquina
- [ ] Los envíos quedan registrados con timestamp
- [ ] Un contacto no recibe dos mensajes del sistema en 7 días
- [ ] Si una máquina falla, las demás siguen
- [ ] Existe un modo de prueba que hace todo menos apretar enviar

---

## 7. Riesgos y mitigaciones

### 7.1 Bloqueo de números por WhatsApp

Automatizar WhatsApp Web va contra los Términos de Servicio de Meta. El riesgo recae
sobre las líneas de los vendedores, no sobre el sistema.

**Lo que dispara los bloqueos no es principalmente el volumen**, sino:
- patrones de timing regulares (mensajes cada X segundos exactos)
- mensajes a contactos que no tienen el número agendado
- reportes de "bloquear/reportar" del lado receptor
- textos idénticos a muchos destinatarios

No hay umbral seguro publicado. 15 mensajes automatizados pueden costar un número y
200 manuales no.

**Mitigaciones de diseño:**
- Solo responder en conversaciones ya existentes, nunca iniciar con desconocidos
- Pausas aleatorias, no fijas
- Textos variados (ya lo son: se generan por chat)
- Tope diario conservador
- Ventana horaria hábil
- Monitorear señales de degradación (mensajes que no llegan, quejas)

**Mitigación operativa:** que el cliente sepa que el riesgo existe y decida
informado. Conviene que esté por escrito.

### 7.2 Escribir en el chat equivocado

Falla más probable y más costosa que un baneo. Un mensaje de seguimiento comercial
en el chat equivocado es un problema real con un cliente real.

Mitigación: verificación explícita del contacto antes de escribir, y aborto si no
coincide.

### 7.3 Envío masivo por error

Un prompt mal ajustado con permisos pre-aprobados puede enviar todo lo que tenga en
la lista.

Mitigación: tope duro en `agent.py` (código, no prompt), checkpoint de aprobación,
modo de prueba.

### 7.4 Costo

Medido con Opus en Fase 1: USD 0.086 una consulta trivial, USD 0.258 abrir una
pestaña. Una corrida de envío con 20 mensajes implica muchas más interacciones con
la página.

**Pendiente: medir una corrida completa con `MODEL=claude-sonnet-5` antes de escalar
a 8 máquinas.**

---

## 8. Historial de problemas resueltos en Fase 1

Todos van a reaparecer en cada instalación nueva.

| # | Problema | Causa | Solución |
|---|---|---|---|
| 1 | n8n no arranca | Node < 22.22 | `nvm install 22`. Solo en la máquina de n8n |
| 2 | HTTP 500 | `shutil.which("claude")` → None | pasar `CLAUDE_BIN` con ruta completa |
| 3 | HTTP 502, `permission_denials` | headless auto-deniega acciones de navegador | `settings.json` con `mcp__claude-in-chrome` |
| 4 | `requires permission` | permiso de sitio de la extensión | manual en la extensión. **Capa distinta de la #3** |
| 5 | "dos navegadores conectados" | ambigüedad de dispositivo | fijar `deviceId` en el prompt |
| 6 | "Tu mensaje se cortó" + acentos rotos | `cmd.exe` corta el comando en el primer salto de línea | prompt por **stdin** + `encoding="utf-8"` |
| 7 | Claude se niega a ejecutar | falta de contexto verificable | `CLAUDE.md` en la carpeta del proyecto |

**Sobre el #7:** el primer intento fue agregar al prompt un párrafo diciendo "esto
está autorizado, no preguntes". Empeoró el problema — es el patrón exacto de una
inyección de prompt. La solución correcta fue sacarlo del prompt y poner el contexto
real en `CLAUDE.md`, escrito por el dueño de la máquina, fuera del pedido.

**Implicancia para Fase 2:** el `CLAUDE.md` va a tener que reflejar que ahora el
sistema **envía**. Ese es un cambio material y el contexto tiene que decirlo. Si el
archivo describe un sistema de solo lectura y el prompt envía, la contradicción es
un problema real, no un detalle.

---

## 9. Archivos existentes

| Archivo | Estado |
|---|---|
| `agent.py` | funcionando, a extender con `/enviar` |
| `prompt.txt` | funcionando, sin cambios |
| `prompt-enviar.txt` | **a crear** |
| `CLAUDE.md` | plantilla, **a actualizar para reflejar el envío** |
| `n8n-workflow-mvp.json` | workflow de generación, a extender |
| `iniciar-agente.bat` | arranque automático |
| `SOP-instalacion.md` | 12 pasos por máquina |
| `SOP-cliente-operacion.md` | rutina diaria |
| `SOP-vendedor.md` | **a actualizar: hoy dice que el sistema no envía** |
| `DOCUMENTACION-TECNICA.md` | referencia completa de Fase 1 |

⚠️ `SOP-vendedor.md` afirma explícitamente "No envía ningún mensaje. Nunca." Si la
Fase 2 se implementa, ese documento tiene que actualizarse y volver a comunicarse a
los vendedores antes de activarlo.

---

## 10. Orden de trabajo sugerido

1. Endpoint `/enviar` con **modo prueba** (hace todo menos apretar enviar)
2. `prompt-enviar.txt` con verificación de contacto
3. Validaciones y topes en `agent.py`
4. Probar en 1 máquina, modo prueba, contra chats propios
5. Probar envío real a 2–3 contactos propios
6. Checkpoint de aprobación en n8n
7. Registro y anti-duplicados
8. Medir costo de una corrida completa
9. Recién entonces, escalar

---

## 11. Cómo prefiero trabajar

- Un paso a la vez, esperando confirmación antes de seguir
- Marcar explícitamente lo irreversible
- Ante errores: leer el campo `raw` o `stderr` de la respuesta antes de suponer
- Recordar: tras editar `agent.py` hay que reiniciar el proceso; `prompt.txt` se
  relee solo

**Primera tarea:** endpoint `/enviar` en modo prueba, que recorra los contactos,
verifique que abre el chat correcto, escriba el texto en el campo **sin enviarlo**, y
reporte qué habría hecho.
