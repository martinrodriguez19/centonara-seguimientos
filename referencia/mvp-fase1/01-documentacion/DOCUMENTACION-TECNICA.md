# Documentación técnica del proyecto

**Sistema de generación de borradores de seguimiento sobre WhatsApp**
Versión 1.0 · 05/08/2026 · MVP validado end-to-end en 1 máquina

Este documento registra **todo** lo que se construyó, cómo funciona, qué falló y
por qué, y hacia dónde sigue. Está pensado para que alguien que no participó pueda
retomar el proyecto sin preguntar nada.

---

# 1. Resumen ejecutivo

**Problema:** 8 vendedores necesitan escribir mensajes de seguimiento a clientes
todos los días. Escribirlos de cero consume tiempo y la calidad es despareja.

**Solución construida:** un sistema que lee los chats recientes de WhatsApp de cada
vendedor y genera borradores de seguimiento contextualizados, con revisión humana
antes de usarlos. **No envía nada automáticamente.**

**Estado:** MVP funcionando en 1 máquina Windows. Genera 5 borradores por corrida
con calidad utilizable.

**Decisión abierta:** el MVP usa automatización de navegador (Claude in Chrome).
Funciona, pero tiene alto costo operativo. La ruta recomendada para producción es
WhatsApp Cloud API con Coexistence. Ver sección 8.

---

# 2. Arquitectura del MVP

```
┌─────────────────────────────────────────────────┐
│  n8n  (1 sola máquina, orquestador)             │
│  cron o disparo manual                          │
└────────────┬────────────────────────────────────┘
             │  HTTP POST /run  (paralelo, token en header)
     ┌───────┴────────┬────────────────┐
     ▼                ▼                ▼
┌─────────┐     ┌─────────┐     ┌─────────┐
│  PC-1   │     │  PC-2   │ ... │  PC-8   │
│         │     │         │     │         │
│ agent.py (Python, stdlib, puerto 8787)  │
│    │                                     │
│    └─> claude -p --chrome (Claude Code)  │
│              │                           │
│              └─> extensión Claude in Chrome
│                       │                  │
│                       └─> web.whatsapp.com (SOLO LECTURA)
└─────────────────────────────────────────┘
```

## 2.1 Por qué esta arquitectura

**El problema original:** se necesitaba operar 8 navegadores en paralelo. La
extensión de Claude in Chrome, cuando hay varios navegadores conectados a la misma
cuenta, rutea las peticiones de forma no determinística ("competing consumer"): el
dispositivo que toma la petición primero gana.

**La solución:** no disparar desde la nube, sino **dentro de cada máquina**. Claude
Code se comunica con la extensión local vía *native messaging host*, un canal local
del sistema operativo. Si el proceso corre en la PC-1, maneja el Chrome de la PC-1.

**El detalle que faltaba:** aun corriendo local, si hay varios Chrome asociados a la
misma cuenta de Anthropic, Claude pregunta cuál usar. En modo headless no hay quien
responda. Se resuelve fijando el `deviceId` de cada máquina en el prompt.

## 2.2 Componentes

| Componente | Qué hace | Dónde corre |
|---|---|---|
| `n8n` | orquesta, dispara, consolida resultados | 1 máquina |
| `agent.py` | servidor HTTP que ejecuta Claude Code | cada máquina |
| `prompt.txt` | la tarea, con placeholders | cada máquina |
| `CLAUDE.md` | contexto del proyecto | cada máquina |
| Claude Code | ejecuta la tarea, maneja el navegador | cada máquina |
| Extensión Chrome | acceso al navegador | cada máquina |

---

# 3. Requisitos verificados

| Requisito | Detalle | Fuente |
|---|---|---|
| Plan Anthropic | Pro, Max, Team o Enterprise. **Gratuito no sirve** | verificado en uso |
| Autenticación | Login con cuenta. **Con API key la integración de Chrome queda desactivada** aunque se pase `--chrome` | docs oficiales |
| SO | Windows 10 (1809+) o 11, 64 bits / macOS / Linux | docs oficiales |
| **No WSL** | la integración de Chrome no funciona bajo WSL | docs oficiales |
| Node.js | **solo en la máquina de n8n**, v22.22+ | error de n8n en instalación |
| Python | en cada máquina de vendedor | requerido por `agent.py` |
| Chrome | con extensión Claude v1.0.36+ | docs oficiales |
| RAM | 4 GB mínimo, 8 GB recomendado (por Chrome) | criterio operativo |

**Claude Code no requiere Node** si se usa el instalador nativo. Solo el método npm
lo necesita.

---

# 4. Instalación — comandos exactos

Todos verificados en Windows 11 / PowerShell durante la instalación de referencia.

## 4.1 Python

```powershell
python --version
```

Si falta: instalar desde python.org **marcando "Add python.exe to PATH"**.

- En Windows el comando es `python`, no `python3`
- Si se abre la Microsoft Store: Configuración → Aplicaciones → Alias de ejecución
  de aplicaciones → desactivar `python.exe` y `python3.exe`

## 4.2 Claude Code

Instalador nativo (recomendado, sin Node):

```powershell
irm https://claude.ai/install.ps1 | iex
```

Vía npm (si ya hay Node):

```powershell
npm install -g @anthropic-ai/claude-code
```

**Cerrar y reabrir PowerShell.** Verificar y anotar la ruta:

```powershell
claude --version
where claude
```

Rutas observadas:
- npm: `C:\Users\<usuario>\AppData\Roaming\npm\claude.CMD`
- nativo: `C:\Users\<usuario>\.local\bin\claude.exe`

## 4.3 Login

```powershell
claude
```

Login con la cuenta del plan. Verificar:

```powershell
claude -p "decime solamente OK" --output-format json
```

Debe devolver `"result":"OK"`.

## 4.4 Extensión y primera conexión

1. Instalar extensión Claude desde Chrome Web Store
2. Dejar Chrome abierto
3. `claude --chrome` → aceptar diálogo inicial
4. Dentro de la sesión: `/chrome` → verificar **Status: Enabled** / **Extension: Installed**

Si dice "Not detected": reiniciar Chrome (el native messaging host se lee al
arrancar), después `/chrome` → Reconnect extension.

## 4.5 Permiso de sitio en la extensión ⚠️ MANUAL

Ícono de Claude en Chrome → configuración → permisos de sitios → habilitar
`web.whatsapp.com`.

**No hay comando para esto.** Omitirlo produce: `Claude in Chrome requires permission`.

## 4.6 Permisos del CLI para headless

Sin esto, el modo `-p` auto-deniega las acciones de navegador.

```powershell
New-Item -ItemType Directory -Force -Path $env:USERPROFILE\.claude | Out-Null; '{"permissions":{"allow":["mcp__claude-in-chrome"]}}' | Out-File -Encoding utf8 $env:USERPROFILE\.claude\settings.json; Get-Content $env:USERPROFILE\.claude\settings.json
```

macOS/Linux:

```bash
mkdir -p ~/.claude && echo '{"permissions":{"allow":["mcp__claude-in-chrome"]}}' > ~/.claude/settings.json
```

⚠️ Pisa cualquier `settings.json` existente.

## 4.7 Obtener el deviceId ⚠️ CRÍTICO

```powershell
claude -p "abri example.com y decime solo el titulo" --chrome --output-format json
```

Con varios Chrome conectados, Claude lista los `deviceId` disponibles. Verificar el
correcto:

```powershell
claude -p "seleccioná el navegador con deviceId <ID>, abri example.com y decime solo el titulo" --chrome --output-format json
```

**La pestaña debe abrirse en la pantalla que se tiene adelante.** Si se abrió en otra
máquina, el ID está cruzado.

Los deviceId cambian si se reinstala la extensión. Registrarlos por máquina.

## 4.8 Archivos

Carpeta única (ej. `C:\claude-agent\`) con los tres juntos:

- `agent.py`
- `prompt.txt` — el agente lo busca al lado suyo
- `CLAUDE.md` — Claude Code lo lee del `cwd`

## 4.9 Arranque

```powershell
cd C:\claude-agent; $env:DEVICE_ID="<id>"; $env:CLAUDE_BIN="<ruta>"; $env:AGENT_TOKEN="<token>"; $env:MACHINE_NAME="PC-1"; $env:MODEL="claude-sonnet-5"; python agent.py
```

Salida esperada: `Agente 'PC-1' escuchando en 0.0.0.0:8787`

Automatizable con `iniciar-agente.bat` + acceso directo en `shell:startup`.

## 4.10 Firewall e IP

```powershell
New-NetFirewallRule -DisplayName "Claude Agent 8787" -Direction Inbound -LocalPort 8787 -Protocol TCP -Action Allow -Profile Private
ipconfig
```

**Reservar IP fija en el router.** Con DHCP las IPs cambian al reiniciar.

---

# 5. Variables de entorno

| Variable | Requerida | Default | Descripción |
|---|---|---|---|
| `AGENT_TOKEN` | sí | `cambiar-esto` | token compartido con n8n |
| `DEVICE_ID` | sí (con >1 Chrome) | vacío | deviceId del Chrome local |
| `CLAUDE_BIN` | en Windows | autodetect | ruta completa al binario |
| `MACHINE_NAME` | sí | hostname | identifica el origen en n8n |
| `MODEL` | no | default de cuenta | ej. `claude-sonnet-5` |
| `AGENT_PORT` | no | `8787` | puerto de escucha |
| `RUN_TIMEOUT` | no | `600` | segundos |

Generar token:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

# 6. API del agente

## GET /health

Sin autenticación.

```json
{"ok": true, "machine": "PC-1", "claude": "2.1.x"}
```

## POST /run

Header `X-Agent-Token` obligatorio.

Request:
```json
{"n_chats": 5, "run_id": "20260805-142648"}
```

**Solo se aceptan esas dos variables** (whitelist `ALLOWED_VARS`). El prompt vive
en disco y no viaja por la red: n8n no puede inyectar instrucciones arbitrarias a
un Claude con acceso a WhatsApp.

Respuesta OK (200):
```json
{
  "ok": true,
  "machine": "PC-1",
  "run_id": "20260805-142648",
  "data": {
    "run_id": "20260805-142648",
    "status": "ok",
    "chats": [
      {
        "contacto": "Rocio",
        "ultimo_mensaje_resumen": "Cuenta que organizo su mes para asistir",
        "ultimo_lo_mando": "contacto",
        "antiguedad": "2:14 p. m.",
        "template_seguimiento": "Hola Rocio, que bueno que ya organizaste..."
      }
    ]
  }
}
```

Códigos de error:

| Código | `error` | Causa |
|---|---|---|
| 401 | `unauthorized` | token incorrecto |
| 500 | `falta_prompt_txt` | `prompt.txt` no está junto a `agent.py` |
| 500 | `claude_no_encontrado` | binario fuera del PATH del proceso |
| 502 | `claude_exit_nonzero` | el CLI falló — ver `stderr` |
| 502 | `modelo_no_devolvio_json` | salida no parseable — ver `raw` |
| 504 | `timeout` | superó `RUN_TIMEOUT` |

**El campo `raw` contiene la respuesta literal del modelo. Leerlo siempre antes de
suponer la causa.**

---

# 7. Historial de fallas — cronología real

Los siete problemas encontrados, en orden. Todos van a reaparecer en cada
instalación nueva.

### 7.1 Node.js insuficiente para n8n
`Your Node.js version 22.16.0 is currently not supported. Please use >=22.22`
→ `nvm install 22`. Node solo hace falta en la máquina de n8n.

### 7.2 Binario `claude` no encontrado (HTTP 500)
`shutil.which("claude")` devolvía `None` aunque la terminal lo encontraba.
→ Pasar `CLAUDE_BIN` con la ruta completa. En Windows el `.CMD` de npm no siempre
se resuelve.

### 7.3 Permisos denegados en headless (HTTP 502)
```json
"permission_denials":[{"tool_name":"mcp__claude-in-chrome__tabs_context_mcp",
 "tool_input":{"createIfEmpty":true}}]
```
`createIfEmpty` modifica estado → pide confirmación → en `-p` se auto-deniega.
→ `settings.json` con `"allow": ["mcp__claude-in-chrome"]`.

### 7.4 Permiso de sitio de la extensión
`Claude in Chrome requires permission` — viene del navegador, no del CLI.
→ Manual, desde la extensión. **Capa de permisos distinta e independiente de 7.3.**

### 7.5 Ambigüedad de navegador
> hay dos navegadores Chrome conectados a tu cuenta y ninguno está seleccionado

En interactivo aparece un selector; en headless no hay quien responda.
→ Fijar `deviceId` en el prompt vía `{{DEVICE_ID}}`.

### 7.6 Prompt truncado en Windows ⚠️ el más difícil de diagnosticar
Síntoma: *"Tu mensaje se cortó: PASO 0 (obligatorio...)"* + acentos rotos
(`seleccionÃ¡`).

**Causa:** `claude.CMD` se ejecuta a través de `cmd.exe`, que **corta el comando en
el primer salto de línea**. Un prompt multilínea pasado como argumento llegaba
mutilado a la primera línea.

**Solución:** pasar el prompt por **stdin** y forzar UTF-8.

```python
proc = subprocess.run(
    [CLAUDE_BIN, "-p", "--chrome", "--output-format", "json"],
    input=prompt,          # ← por stdin, NO como argumento
    capture_output=True,
    text=True,
    encoding="utf-8",      # ← si no, Windows usa cp1252 y rompe acentos
    errors="replace",
    timeout=TIMEOUT,
    cwd=str(Path(__file__).parent),
)
```

### 7.7 Frenado por falta de contexto ⚠️ el más importante conceptualmente

Con el prompt llegando completo, Claude se negó a ejecutar. Señaló tres cosas:

1. El texto de la tarea afirmaba de sí mismo estar autorizado ("no preguntes", "ya
   está autorizada") — la forma típica de una inyección de prompt.
2. La tarea lee mensajes de **terceros** que no consintieron.
3. Nada en el contexto del proyecto establecía la tarea como legítima.

**Intento fallido:** agregar al prompt un párrafo de auto-autorización. Empeoró el
problema: es exactamente el patrón que dispara la desconfianza, y con razón — un
texto que se declara confiable a sí mismo no prueba nada.

**Solución correcta:** sacar ese párrafo del prompt y poner el contexto en un
`CLAUDE.md` en la carpeta del proyecto. Es el mecanismo previsto: contexto
persistente, escrito por el dueño de la máquina, verificable, fuera del pedido.

**Lección para el proyecto:** el `CLAUDE.md` tiene que ser **verdadero**. Si dice que
el vendedor está al tanto y no lo está, el problema no es el archivo — es el
proyecto. Ver sección 9.

---

# 8. Costos medidos

Medidos en la instalación de referencia, con Opus:

| Operación | Costo |
|---|---|
| Consulta trivial sin navegador | USD 0.086 |
| Apertura de pestaña simple | USD 0.258 |
| Test de navegador que ni completó | USD 0.265 |

**Proyección sin optimizar:** 8 vendedores × 22 días hábiles = 176 corridas/mes. Con
corridas completas más caras que estas pruebas, el orden de magnitud es de cientos
de dólares mensuales solo en inferencia.

**Mitigación aplicada:** variable `MODEL=claude-sonnet-5`. La tarea no requiere Opus.

**Pendiente:** medir una corrida completa real con Sonnet y proyectar antes de
escalar. Es la variable que decide si el enfoque de navegador es viable.

---

# 9. Consideraciones sobre datos de terceros

El sistema lee conversaciones que incluyen mensajes de clientes que no participaron
de la decisión de instalarlo. Esto no es un detalle legal accesorio: es lo que hizo
que el sistema se frenara en 7.7.

**Lo que quedó definido:**
- No se almacena el contenido de los chats, solo un resumen de una línea
- No se envía nada automáticamente
- Cada máquina tiene un `CLAUDE.md` que documenta de quién es la cuenta y quién
  autorizó
- Los vendedores reciben una guía (`SOP-vendedor.md`) que explica qué hace el
  sistema y cómo desactivarlo por su cuenta

**Lo que queda pendiente del lado del cliente:**
- Acuerdo escrito con cada vendedor antes de instalar
- Definición de si las líneas son personales o comerciales
- Política de privacidad que contemple el tratamiento

**Relevante para la decisión técnica:** la ruta de WhatsApp Cloud API (sección 10)
opera dentro del marco de consentimiento de Meta, con opt-in y plantillas aprobadas.
Es una razón de peso además de las operativas.

---

# 10. Ruta recomendada para producción

## 10.1 Por qué migrar

El MVP funciona pero cada capa que se destrabó reveló otra. En producción con 8
máquinas:

- 8 PCs prendidas con Chrome abierto todo el día
- 8 sesiones de WhatsApp Web que expiran
- 8 agentes que hay que relevantar tras cada reinicio
- deviceId que cambian al actualizar la extensión
- Costo de inferencia alto por lectura de pantalla
- Lectura de conversaciones ajenas vía scraping visual

## 10.2 WhatsApp Coexistence

Permite el mismo número en la **app de WhatsApp Business** y la **Cloud API**
simultáneamente. Los mensajes se espejan en tiempo real vía webhooks.

Datos verificados (05/08/2026):
- Lanzado por Meta en mayo 2025, disponible globalmente desde mayo 2026
- Conserva funciones nativas: llamadas, estados, grupos. Sin riesgo de baneo
- Importa hasta 6 meses de historial 1:1
- Mensajes desde la app siguen siendo gratis; los de API pagan pricing por conversación
- Throughput fijo de 20 mps para números en Coexistence
- Cambio de precios de Meta anunciado para 01/07/2026

**Requisitos:**
- App **WhatsApp Business** (no el WhatsApp común), v2.24.17+
- Número activo en esa app por al menos 7 días
- Business Portfolio con datos legales completos
- ⚠️ **El Business Portfolio no se puede cambiar después de registrar el número**
- ⚠️ **Un número puede estar conectado a un solo BSP/Tech Partner a la vez**

## 10.3 Dos caminos

**A) Vía BSP** — rápido para validar. El BSP ya es Tech Provider y presta el
Embedded Signup. Costo observado: ~€49/USD 59 por número/mes en 360dialog, más
tarifas de Meta. Para 8 números son ~€392/mes solo en fees de intermediario.

**B) Tech Provider propio** — requiere Embedded Signup con session logging, webhook
funcional y solicitud del estado ante Meta. Más trabajo inicial, sin fee por número.

**Recomendación:** validar con un BSP y un número. Si funciona, evaluar B para los 8.

## 10.4 Flujo de onboarding Coexistence

1. Iniciar Embedded Signup desde el panel del BSP
2. Elegir **"conectar app de WhatsApp Business existente"** (no "número nuevo")
3. Seleccionar Business Portfolio
4. Ingresar el número → se genera un QR
5. En el teléfono: mensaje del canal oficial de Facebook dentro de WhatsApp Business,
   con código y botón para escanear
6. Elegir si se comparte historial
7. Escanear el QR
8. Obtener WABA ID, phone number ID y token
9. Configurar webhook en el panel del BSP
10. Probar con un mensaje entrante

Duración: 5–15 min el signup, 4–6 hs la sincronización del historial en background.

⚠️ **No usar "Add phone number" desde WhatsApp → API Setup en una app de Meta.** Ese
es el flujo estándar y **saca el número de la app de WhatsApp Business**.

## 10.5 Arquitectura destino

```
WhatsApp (teléfono del vendedor, uso normal)
   ↕ espejado en tiempo real
Cloud API / BSP
   │ webhook
   ▼
n8n Cloud  →  API de Anthropic  →  base de datos  →  panel de revisión
```

Sin máquinas prendidas, sin navegadores, sin agentes, sin deviceId.

---

# 11. Inventario de archivos

| Archivo | Destino | Descripción |
|---|---|---|
| `agent.py` | cada PC | servidor HTTP + ejecución de Claude Code |
| `prompt.txt` | cada PC | la tarea, con `{{DEVICE_ID}}`, `{{N_CHATS}}`, `{{RUN_ID}}` |
| `CLAUDE.md` | cada PC | plantilla de contexto — **completar con datos reales** |
| `iniciar-agente.bat` | cada PC | arranque automático vía `shell:startup` |
| `n8n-workflow-mvp.json` | n8n | workflow importable, 2 máquinas en paralelo |
| `SOP-instalacion.md` | soporte | 12 pasos por máquina + diagnóstico |
| `SOP-cliente-operacion.md` | cliente | rutina diaria y resolución de fallas |
| `SOP-vendedor.md` | vendedores | qué hace el sistema, en lenguaje no técnico |
| `GUIA-descargas-cliente.md` | cliente | descargas previas a la visita |
| `BRIEF-whatsapp-coexistence.md` | — | brief para retomar la migración a API |
| `README.md` | — | arranque rápido del MVP |

---

# 12. Deuda técnica y pendientes

**Seguridad**
- El token viaja en texto plano por HTTP en la LAN. Sin TLS.
- El token queda escrito en el `.bat` de cada máquina.
- El agente escucha en `0.0.0.0`. Apto para red interna, **no exponer a internet**.

**Operación**
- Sin persistencia: los resultados viven en la ejecución de n8n
- Sin reintentos automáticos
- Sin alertas ante máquina caída
- Sin rotación del `agente.log`

**Producto**
- Distribución de borradores manual
- Sin registro de qué borradores se usaron (no hay feedback para mejorar el prompt)
- Sin control de costo por máquina

**Priorización sugerida**
1. Decidir MVP-navegador vs. Cloud API antes de invertir en lo demás
2. Si sigue el navegador: arranque automático + persistencia + alertas
3. Si migra a API: nada de lo anterior hace falta

---

# 13. Cronología

| Fecha | Hito |
|---|---|
| 05/08/2026 | Diseño de arquitectura y sprint plan |
| 05/08/2026 | MVP construido: agent.py, prompt, workflow n8n |
| 05/08/2026 | 7 problemas diagnosticados y resueltos |
| 05/08/2026 | **Primera corrida exitosa: 5 chats, 5 borradores, calidad utilizable** |
| 05/08/2026 | Documentación: 3 SOPs + guía de descargas |
| 05/08/2026 | Investigación de Coexistence y decisión de evaluar migración |

---

*Documento generado el 05/08/2026. Los datos de Meta y precios de BSP tienen fecha
de verificación: confirmar antes de tomar decisiones comerciales.*
