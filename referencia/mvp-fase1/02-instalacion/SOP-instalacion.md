# SOP — Instalación del sistema de templates de seguimiento

**Versión:** 1.0 · **Fecha:** 05/08/2026 · **Estado:** MVP validado en 1 máquina (Windows 11)

Procedimiento para instalar el sistema en cada computadora de vendedor.
Tiempo estimado: **25–40 min por máquina** la primera vez, ~15 min a partir de la tercera.

---

## 0. Antes de tocar una computadora

### 0.1 Requisitos de cuenta

| Ítem | Detalle |
|---|---|
| Plan Anthropic | Pro, Max, Team o Enterprise. **El plan gratuito no sirve.** |
| Autenticación | Login con cuenta (`/login`). **Con API key la integración de Chrome queda desactivada**, aunque se pase `--chrome`. |
| Licencias | Una por máquina. Definir con el cliente si van 8 cuentas individuales o un plan Team. |

### 0.2 Acuerdo con los vendedores — hacer ANTES de instalar

El sistema lee conversaciones de WhatsApp que incluyen mensajes de clientes. Antes
de la primera instalación, dejar por escrito:

- [ ] Cada vendedor sabe que el sistema lee su lista de chats de trabajo
- [ ] Está definido si la línea es personal o comercial (si es personal, revisar si corresponde)
- [ ] Está definido qué se guarda y por cuánto tiempo (hoy: solo resumen de una línea + borrador)
- [ ] El cliente tiene o está armando una política de privacidad que lo contemple

Esto no es burocracia: es el contenido del `CLAUDE.md` que se instala en cada
máquina, y si está vacío el sistema puede frenar por falta de contexto.

### 0.3 Kit a llevar

- `agent.py`, `prompt.txt`, `CLAUDE.md` (en un pendrive o repo accesible)
- Este SOP
- Token compartido ya generado: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Planilla de registro (ver sección 6)

---

## 1. Instalación por máquina

> Los ejemplos son Windows/PowerShell. Para Mac/Linux, los equivalentes están al final de cada paso.

### Paso 1 — Python

```powershell
python --version
```

Si no responde: instalar desde python.org.
**Marcar "Add python.exe to PATH" en la primera pantalla del instalador.**

- Si al escribir `python` se abre la Microsoft Store: Configuración → Aplicaciones →
  Alias de ejecución → desactivar `python.exe` y `python3.exe`.
- En Windows el comando es `python`, no `python3`.
- Mac/Linux: `python3 --version`, y si falta, `brew install python` / `sudo apt install python3`.

### Paso 2 — Claude Code

```powershell
npm install -g @anthropic-ai/claude-code
claude --version
```

Sin Node instalado, usar el instalador nativo (macOS/Linux: `curl -fsSL https://claude.ai/install.sh | bash`;
Windows: instalador de la página oficial).

**Anotar la ruta del binario** — se necesita más adelante:

```powershell
where claude
# típico: C:\Users\<usuario>\AppData\Roaming\npm\claude.CMD
```

> **Windows nativo, no WSL.** La integración con Chrome no funciona en WSL.

### Paso 3 — Login

```powershell
claude
```

Abre el navegador para autenticarse. Login con la cuenta del plan. Verificar:

```powershell
claude -p "decime solamente OK" --output-format json
```

Debe devolver `"result":"OK"`.

### Paso 4 — Extensión Claude in Chrome

1. Instalar desde Chrome Web Store (v1.0.36 o superior)
2. Dejar Chrome abierto
3. Primera conexión interactiva:

```powershell
claude --chrome
```

Aceptar el diálogo inicial (Enter). Dentro de la sesión, escribir `/chrome` y
verificar: **Status: Enabled** y **Extension: Installed**.

Si dice "Not detected": reiniciar Chrome (el native messaging host se lee al arrancar),
después `/chrome` → Reconnect extension.

### Paso 5 — Permiso de sitio en la extensión ⚠️

**Paso manual, no hay comando.** Ícono de Claude en la barra de Chrome →
configuración → permisos de sitios → habilitar `web.whatsapp.com`.

Omitir este paso produce: `Claude in Chrome requires permission`.

### Paso 6 — Permisos del CLI para modo headless

Sin esto, el modo `-p` se auto-deniega las acciones de navegador
(aparece en `permission_denials`).

```powershell
New-Item -ItemType Directory -Force -Path $env:USERPROFILE\.claude | Out-Null; '{"permissions":{"allow":["mcp__claude-in-chrome"]}}' | Out-File -Encoding utf8 $env:USERPROFILE\.claude\settings.json; Get-Content $env:USERPROFILE\.claude\settings.json
```

Mac/Linux:
```bash
mkdir -p ~/.claude && echo '{"permissions":{"allow":["mcp__claude-in-chrome"]}}' > ~/.claude/settings.json
```

> ⚠️ Si ya existía un `settings.json`, esto lo pisa. Revisar antes.

### Paso 7 — WhatsApp Web

Con el vendedor presente: abrir `web.whatsapp.com` en ese Chrome y escanear el QR.
La sesión queda persistente en el perfil del navegador.

### Paso 8 — Obtener el deviceId ⚠️ crítico

Con varios Chrome conectados a la misma cuenta, el modo headless no sabe cuál usar
y frena. Hay que fijarlo.

```powershell
claude -p "abri example.com y decime solo el titulo" --chrome --output-format json
```

Si hay ambigüedad, Claude lista los navegadores conectados con sus `deviceId`.
Anotar el de esta máquina y **verificarlo**:

```powershell
claude -p "seleccioná el navegador con deviceId <ID>, abri example.com y decime solo el titulo" --chrome --output-format json
```

La pestaña tiene que abrirse **en la pantalla que se tiene adelante**. Si se abrió
en otra máquina, el ID está cruzado.

> Los deviceId cambian si se reinstala la extensión o se resetea la conexión.
> Registrarlos en la planilla de la sección 6.

### Paso 9 — Archivos

Crear `C:\claude-agent\` (o `~/claude-agent/`) con los tres archivos **juntos**:

- `agent.py`
- `prompt.txt`
- `CLAUDE.md` ← completar los campos `>>>` con los datos reales de esa máquina y ese vendedor

El agente busca `prompt.txt` al lado suyo, y Claude Code lee `CLAUDE.md` de la
carpeta de trabajo. Si están separados, no funciona.

### Paso 10 — Levantar el agente

```powershell
cd C:\claude-agent; $env:DEVICE_ID="<id-de-esta-maquina>"; $env:CLAUDE_BIN="C:\Users\<usuario>\AppData\Roaming\npm\claude.CMD"; $env:AGENT_TOKEN="<token-compartido>"; $env:MACHINE_NAME="PC-1"; $env:MODEL="claude-sonnet-5"; python agent.py
```

Mac/Linux:
```bash
cd ~/claude-agent && DEVICE_ID="<id>" AGENT_TOKEN="<token>" MACHINE_NAME="PC-1" MODEL="claude-sonnet-5" python3 agent.py
```

La ventana queda ocupada mostrando logs. **No cerrarla.**

- `MACHINE_NAME` distinto en cada máquina (PC-1, PC-2, …): es lo que identifica el origen en n8n.
- `MODEL`: sin esta variable corre con el modelo por defecto de la cuenta, que puede ser
  3–4× más caro para esta tarea.
- Las variables `$env:` viven solo en esa ventana.

### Paso 11 — Firewall

Windows va a mostrar un cartel la primera vez. Permitir en **redes privadas**.
Si no apareció:

```powershell
New-NetFirewallRule -DisplayName "Claude Agent 8787" -Direction Inbound -LocalPort 8787 -Protocol TCP -Action Allow -Profile Private
```

### Paso 12 — IP de la máquina

```powershell
ipconfig    # anotar la IPv4 del adaptador en uso
```

**Reservar IP fija para cada PC desde el panel del router.** Con DHCP las IPs
cambian al reiniciar y el workflow deja de encontrar la máquina.

---

## 2. Verificación

Los tres tests, en orden. No avanzar si uno falla.

**A — Agente vivo (desde la misma máquina):**
```powershell
curl.exe -s http://localhost:8787/health
```
Esperado: `{"ok": true, "machine": "PC-1", "claude": "2.x.x"}`

**B — Corrida completa (desde la misma máquina):**
```powershell
'{"n_chats":5,"run_id":"test"}' | Out-File -Encoding ascii body.json; curl.exe -s -X POST http://localhost:8787/run -H "X-Agent-Token: <token>" -H "Content-Type: application/json" -d "@body.json"
```
Esperado: JSON con 5 chats y sus templates. Tarda 1–4 minutos.

**C — Alcance de red (desde la máquina donde corre n8n):**
```powershell
curl.exe -s http://<ip-de-la-pc>:8787/health
```
Si A funciona y C no: firewall.

---

## 3. Configuración de n8n (una sola vez, no por máquina)

1. Node.js 22.22+ (`nvm install 22`) o Docker
2. `npx n8n` → `http://localhost:5678`
3. Importar `n8n-workflow-mvp.json` (menú ⋮ → Import from File)
4. Por cada máquina, un nodo HTTP Request:
   - URL: `http://<ip>:8787/run`
   - Header `X-Agent-Token`: el token compartido
   - Timeout: 660000 ms
5. Ejecutar con **Test workflow** (el toggle "Active" es solo para triggers automáticos)

Docker en Linux: agregar `--add-host=host.docker.internal:host-gateway` y usar esa
URL para llegar a la máquina que hospeda n8n.

---

## 4. Diagnóstico

Todos estos aparecieron en la instalación de referencia.

| Síntoma | Causa | Solución |
|---|---|---|
| `python no se encuentra` | falta Python o falta el PATH | Paso 1. En Windows es `python`, no `python3` |
| HTTP 500 `claude_no_encontrado` | el proceso no ve el binario | pasar `CLAUDE_BIN` con la ruta completa al `.CMD` |
| HTTP 500 `falta_prompt_txt` | archivos separados | los tres en la misma carpeta |
| HTTP 401 | token distinto entre agente y n8n | mismo string en ambos lados |
| HTTP 502 `permission_denials` no vacío | falta `settings.json` | Paso 6 |
| `Claude in Chrome requires permission` | falta permiso de sitio | Paso 5 (manual, en la extensión) |
| "hay dos navegadores conectados" | falta fijar deviceId | Paso 8 |
| "Tu mensaje se cortó" + acentos rotos | `agent.py` viejo en memoria | Ctrl+C y relevantar. **Editar `agent.py` exige reinicio; `prompt.txt` no** |
| El modelo devuelve texto en vez de JSON | falta contexto o encontró algo inesperado | leer el campo `raw`: casi siempre lo explica |
| Timeout | la corrida superó 10 min | subir `RUN_TIMEOUT` |

**Regla general:** el campo `raw` de la respuesta contiene la respuesta literal del
modelo. Leerlo antes de suponer.

---

## 5. Operación diaria

**Hoy (MVP):** el agente se levanta a mano en cada máquina y hay que dejar la
terminal abierta. Si se cierra o se reinicia la PC, hay que volver a levantarlo.

**Pendiente de automatizar:** servicio de Windows o Task Scheduler con `-WindowStyle Hidden`
para que arranque solo con la sesión. Es el primer ítem de la próxima fase.

**Costos.** Medidos en la instalación de referencia con Opus:

| Operación | Costo aprox. |
|---|---|
| Consulta trivial sin navegador | USD 0.086 |
| Apertura de pestaña simple | USD 0.26 |
| Corrida completa de 5 chats | medir y registrar |

Con 8 vendedores × 22 días hábiles son ~176 corridas mensuales. **Medir una corrida
real con `claude-sonnet-5` y proyectar antes de escalar.** Es la variable que decide
si el enfoque de navegador se sostiene o conviene migrar a la API de WhatsApp Business.

**Límites conocidos del MVP:**
- No envía mensajes, solo redacta
- Sin persistencia: los resultados quedan en la ejecución de n8n
- Sin reintentos ni alertas
- El agente escucha en la LAN con token compartido: apto para red interna, no para exponer a internet

---

## 6. Planilla de registro

Completar una fila por máquina:

| Campo | PC-1 | PC-2 | PC-3 | … |
|---|---|---|---|---|
| Vendedor | | | | |
| SO y versión | | | | |
| IP (fija) | | | | |
| MACHINE_NAME | | | | |
| deviceId | | | | |
| Ruta de `claude` | | | | |
| Cuenta Anthropic | | | | |
| WhatsApp: línea | | | | |
| Acuerdo firmado | | | | |
| Fecha instalación | | | | |
| Test A / B / C | | | | |

---

## 7. Próxima fase

1. Arranque automático del agente (servicio / Task Scheduler)
2. Persistencia de resultados (Sheets o Postgres)
3. Panel de revisión y aprobación
4. Alertas ante fallo de una máquina
5. Evaluación: navegador vs. API de WhatsApp Business
6. Objetivo declarado: que el cliente no necesite abrir una terminal
