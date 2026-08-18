# Sistema de seguimiento comercial por WhatsApp

**Versión 1.0 · Agosto 2026 · MVP validado end-to-end**

Sistema que lee los chats recientes de WhatsApp de cada vendedor y genera borradores
de mensajes de seguimiento contextualizados, con revisión humana antes de usarlos.

---

## Estado

| | |
|---|---|
| **Validado** | Generación de borradores en 1 máquina Windows 11 |
| **Resultado** | 5 chats leídos, 5 borradores de calidad utilizable |
| **No incluye** | Envío automático (ver `04-proximas-fases/`) |
| **Escala probada** | 1 máquina. Diseñado para 8 |

---

## Contenido

### `01-documentacion/`
- **`DOCUMENTACION-TECNICA.md`** — el documento madre. Arquitectura, requisitos,
  comandos exactos, API del agente, historial de fallas con causa raíz, costos
  medidos. **Empezar por acá.**
- `README.md` — arranque rápido

### `02-instalacion/`
- `GUIA-descargas-cliente.md` — para mandar al cliente **antes** de la visita
- `SOP-instalacion.md` — 12 pasos por máquina + tabla de diagnóstico (técnico)
- `SOP-cliente-operacion.md` — rutina diaria (para quien opera el sistema)
- `SOP-vendedor.md` — qué hace el sistema, en lenguaje no técnico

### `03-codigo/`
- `agent.py` — servidor HTTP que ejecuta Claude Code. Solo stdlib
- `prompt.txt` — la tarea, con placeholders
- `CLAUDE.md` — plantilla de contexto. **Completar los `>>>` con datos reales**
- `iniciar-agente.bat` — arranque automático
- `n8n-workflow-mvp.json` — workflow importable

### `04-proximas-fases/`
- `SPEC-fase2-envio.md` — especificación para agregar envío automatizado
- `BRIEF-whatsapp-coexistence.md` — migración a WhatsApp Cloud API

---

## Arquitectura

```
n8n (orquestador, 1 máquina)
  │ HTTP POST /run
  ▼
agent.py en cada PC (puerto 8787)
  │
  └─> claude -p --chrome
        └─> extensión Claude in Chrome
              └─> web.whatsapp.com (solo lectura)
```

El disparo ocurre **dentro** de cada máquina: Claude Code se comunica con la
extensión local vía native messaging. Cada PC maneja su propio Chrome, fijado por
`deviceId`.

---

## Antes de instalar

**Placeholders a completar.** Los archivos tienen marcadores `>>>` y valores de
ejemplo (`cambiar-esto`, IPs `192.168.0.10x`, `poner-el-token-compartido`). No hay
credenciales reales en este paquete.

**Generar un token nuevo:**
```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Requisitos que no son obvios:**
- Plan Anthropic Pro/Max/Team. **API key no sirve** — desactiva la integración de Chrome
- Windows nativo, **no WSL**
- Node.js solo en la máquina de n8n, v22.22+
- Dos capas de permisos independientes: `settings.json` (CLI) y permiso de sitio
  (extensión, manual)

---

## Advertencias

**El `CLAUDE.md` tiene que ser verdadero.** Es el contexto que hace que el sistema
funcione. Si dice que el vendedor está al tanto y no lo está, el problema no es el
archivo.

**El `SOP-vendedor.md` afirma que el sistema no envía mensajes.** Si se implementa la
Fase 2, hay que actualizarlo y volver a comunicarlo antes de activar el envío.

**Sin persistencia ni alertas.** Los resultados viven en la ejecución de n8n. Si una
máquina falla, nadie avisa.

**Solo red interna.** El agente escucha en `0.0.0.0` con token compartido sobre HTTP.
No exponer a internet.

**Costo pendiente de medir.** Fase 1 midió operaciones sueltas (USD 0.086–0.265 con
Opus). Falta medir una corrida completa con Sonnet antes de escalar a 8 máquinas.
