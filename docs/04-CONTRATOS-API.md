# 04 — Contratos de API

> Base: `https://api.seguimiento.{dominio}` · Todo JSON · Todo UTC en ISO 8601.
> FastAPI genera el OpenAPI en `/docs`. **Este documento es la fuente de verdad; si el código se
> desvía, el que está mal es el código.**

---

## 1. Autenticación

Hay **dos** mecanismos distintos, con superficies separadas a propósito.

| Superficie | Prefijo | Mecanismo | Quién |
|---|---|---|---|
| Agentes | `/api/agent/*` | `X-Agent-Token` (bearer opaco, uno por máquina) | los 8 agentes |
| Panel | `/api/*` | Cookie de sesión (Auth.js) → JWT verificado por FastAPI | usuarios |

**Un token de agente no puede llamar endpoints del panel, y viceversa.** No es un detalle de
implementación: un agente comprometido no debe poder cambiar la configuración ni leer el historial
de otros vendedores.

Los tokens se guardan hasheados con Argon2id. Se rotan desde el panel; la rotación invalida el
anterior de inmediato.

---

## 2. API del agente

### 2.1 Registro

```http
POST /api/agent/registrar
X-Agent-Token: {token}

{ "machine_id": "PC-1", "version_agente": "2.1.0",
  "claude_version": "2.4.1", "device_id": "chrome-device-abc123" }
```

```json
{ "ok": true, "config": { "poll_intervalo_s": 10, "version_disponible": "2.1.0" } }
```

### 2.2 Pedir trabajo (long-poll)

```http
GET /api/agent/jobs/next
X-Agent-Token: {token}
```

El servidor **retiene la conexión hasta 25 segundos**. El cliente debe usar timeout de 30 s.

`200` — hay trabajo:
```json
{
  "job_id": "66c1...",
  "tipo": "ENVIAR",
  "payload": {
    "mensaje_id": "66c2...",
    "contacto_id": "+5491144405036",
    "contacto_nombre": "Rocío",
    "texto": "Hola Rocío, quería consultarte...",
    "modo": "real"
  },
  "timeout_s": 120
}
```

`204` — no hay nada. El agente vuelve a llamar.

`423 Locked` — pausa global activa. El agente espera 60 s antes de reintentar.

> **`payload` nunca contiene texto de prompt.** Viajan datos acotados y validados, nunca
> instrucciones. Es el mismo principio de `ALLOWED_VARS` del MVP, y se mantiene: un backend
> comprometido no debe poder hacer que el agente ejecute algo arbitrario.

### 2.3 Reportar resultado

```http
POST /api/agent/jobs/{job_id}/result
X-Agent-Token: {token}

{
  "ok": true,
  "data": { "enviado": true, "confirmado": true, "timestamp": "2026-08-17T16:03:12Z" },
  "raw": "<salida cruda completa>",
  "stderr": "",
  "duracion_ms": 8420,
  "costo_usd": 0.0
}
```

**`raw` y `stderr` son obligatorios siempre, también cuando `ok` es `true`.** Están ahí para el día
que algo salga mal y haya que entender qué pasó sin poder reproducirlo.

Caso de aborto por identidad — el más importante del sistema:

```json
{
  "ok": false,
  "data": { "enviado": false, "motivo_codigo": "CONTACTO_NO_COINCIDE",
            "esperado": "+5491144405036", "encontrado": "+5491133302020" },
  "raw": "...", "stderr": "", "duracion_ms": 3100
}
```

### 2.4 Heartbeat

```http
POST /api/agent/heartbeat
{ "estado": "ok",
  "diagnostico": { "chrome_ok": true, "whatsapp_sesion_ok": true,
                   "permiso_mcp_ok": true, "permiso_sitio_ok": true } }
```

Cada 30 s. Si el backend no recibe heartbeat por 60 s, la máquina pasa a `offline` en el panel.

### 2.5 Códigos de motivo estandarizados

Usalos tal cual. El frontend los traduce a español para mostrar.

| Código | Significado | ¿Reintentable? |
|---|---|---|
| `CONTACTO_NO_COINCIDE` | El chat abierto no es el esperado | **no** |
| `CONTACTO_NO_ENCONTRADO` | No existe el chat | no |
| `NUMERO_NO_RESOLUBLE` | No se pudo obtener el E.164 | no |
| `CHAT_NO_ABRE` | Timeout al abrir | sí |
| `CAMPO_NO_VACIO` | Había texto escrito por el vendedor | no |
| `ENVIO_NO_CONFIRMADO` | Se apretó enviar, no aparece en el hilo | no |
| `WHATSAPP_SIN_SESION` | Sesión caída, hace falta QR | sí, tras avisar |
| `SELECTOR_ROTO` | Cambió el DOM de WhatsApp Web | **no — frena la corrida** |
| `CHROME_NO_DISPONIBLE` | Chrome cerrado o inaccesible | sí |
| `TIMEOUT` | Se excedió el tiempo del job | sí |

`SELECTOR_ROTO` es especial: **frena la corrida entera y alerta al equipo.** Si el DOM cambió,
todos los envíos siguientes tienen el mismo problema.

---

## 3. API del panel

### 3.1 El botón

```http
POST /api/corridas
{ "tipo": "generacion", "modo": "real", "vendedores": null }
```
`vendedores: null` = todos los activos. Devuelve al instante; el trabajo ocurre en la cola.

```json
{ "run_id": "20260817-generacion", "encolados": 8, "estado": "en_curso" }
```

```http
GET /api/corridas/{run_id}     → progreso en vivo para la barra
GET /api/corridas?fecha=       → historial
```

### 3.2 Sala de salida

```http
GET /api/mensajes?estado=RETENIDO,EN_ESPERA&vendedor={id}&run_id=
```

```json
{
  "total": 18,
  "mensajes": [{
    "id": "66c2...", "contacto_nombre": "Rocío", "vendedor": "Rocío F.",
    "ultimo_mensaje_resumen": "Preguntó por el precio del modelo X",
    "antiguedad_dias": 6,
    "texto_final": "Hola Rocío, quería...",
    "estado": "RETENIDO",
    "triage": { "riesgo": "alto", "senales": ["PALABRA_CONFLICTO"] },
    "sale_a_las": "2026-08-17T16:00:00Z"
  }]
}
```

```http
PATCH /api/mensajes/{id}            { "texto_final": "..." }
POST  /api/mensajes/vetar-lote      { "ids": [...], "motivo": "..." }
POST  /api/mensajes/liberar-lote    { "ids": [...] }
```

- `PATCH` sólo se acepta en `EN_ESPERA` o `RETENIDO`. En cualquier otro estado devuelve `409`.
- Editar recalcula `idempotency_key` y vuelve a pasar los guardrails. Un humano puede empeorar un
  mensaje: si mete un placeholder, se rechaza igual.
- `liberar-lote` sobre un `RETENIDO` lo pasa a `EN_ESPERA` y queda auditado con quién lo liberó.

### 3.3 Revisión posterior

```http
GET /api/revision-posterior?fecha=2026-08-16
```
Lo que salió ayer, con la señal de triage que tuvo cada uno. No frena nada: es el instrumento del
loop de mejora del prompt. Permite marcar un mensaje como "salió mal" para alimentar el ajuste.

```http
POST /api/mensajes/{id}/marcar-problema   { "categoria": "...", "nota": "..." }
```

### 3.4 Control del sistema

```http
POST /api/sistema/pausa      { "alcance": "global", "motivo": "..." }   ← KILL SWITCH
POST /api/sistema/reanudar   { "confirmacion": "REANUDAR" }
GET  /api/sistema/estado
```

El kill switch tiene efecto en menos de 10 segundos: los jobs pendientes dejan de entregarse
(`423`) y los agentes que ya tomaron uno lo abortan en su siguiente chequeo.

**Tiene que poder apretarlo alguien del cliente sin llamar al equipo técnico.** Está visible en
todas las pantallas del panel.

### 3.5 Salud y métricas

```http
GET /api/salud       → estado de las 8 máquinas, con diagnóstico
GET /api/metricas?desde=&hasta=
```

```json
{
  "enviados": 142, "fallidos": 3, "vetados": 5, "retenidos": 12,
  "tasa_edicion": 0.18, "costo_usd": 11.40, "costo_por_mensaje": 0.08
}
```

`tasa_edicion` es la métrica de calidad del prompt: si el humano reescribe el 80%, el sistema no
está aportando valor.

#### `GET /health` — salud del proceso (T0.3)

```http
GET /health          ← sin autenticación, y fuera de `/api`
```

```json
{ "ok": true, "mongo": true, "entorno": "local" }
```

No confundir con `GET /api/salud`: aquél es el estado de las ocho máquinas, éste es el del proceso
del backend. Lo consultan el balanceador de Render y la página de estado del panel.

- `200` cuando todo responde; **`503` cuando Mongo no** — un chequeo de salud que contesta `200`
  con `ok: false` no lo mira nadie, y Render necesita el código de estado para sacar la instancia
  de rotación.
- Sin autenticación: quien lo consulta no tiene con qué autenticarse.
- `entorno` es el valor de `ENTORNO` (`local` | `staging` | `produccion`). Está para saber contra
  qué se está hablando.

### 3.6 Configuración y vendedores

```http
GET   /api/configuracion
PATCH /api/configuracion       { "ventana_veto_minutos": 0 }   ← auditado
GET   /api/vendedores
POST  /api/vendedores
PATCH /api/vendedores/{id}     { "pausado_hasta": "..." }
POST  /api/vendedores/{id}/rotar-token
GET   /api/exclusiones
POST  /api/exclusiones         { "contacto_id": "+549...", "motivo": "..." }
```

---

## 4. Permisos por rol

| Endpoint | vendedor | supervisor | admin |
|---|---|---|---|
| Ver mensajes propios | ✅ | ✅ | ✅ |
| Ver mensajes de otros | ❌ | ✅ | ✅ |
| Editar / vetar propios | ✅ | ✅ | ✅ |
| Liberar retenidos | ❌ | ✅ | ✅ |
| Disparar corrida | ❌ | ✅ | ✅ |
| Kill switch | ✅ | ✅ | ✅ |
| Cambiar configuración | ❌ | ❌ | ✅ |
| Rotar tokens | ❌ | ❌ | ✅ |
| Ver auditoría | ❌ | ✅ | ✅ |

**El kill switch lo puede apretar cualquiera, a propósito.** Frenar de más cuesta un día de
mensajes; frenar de menos cuesta un cliente.

---

## 5. Errores

Formato único en toda la API:

```json
{ "error": { "codigo": "GUARDRAIL_PLACEHOLDER",
             "mensaje": "El texto contiene un placeholder sin resolver: {nombre}",
             "detalle": { "encontrado": "{nombre}", "posicion": 5 } } }
```

| HTTP | Cuándo |
|---|---|
| `400` | Payload inválido |
| `401` | Token o sesión inválida |
| `403` | Sin permiso para ese recurso |
| `409` | Transición de estado no permitida |
| `422` | Violó un guardrail |
| `423` | Pausa global activa |
| `429` | Rate limit |

Rate limits: agentes 120 req/min por máquina; panel 60 req/min por usuario; `POST /api/corridas`
1 cada 5 minutos.

---

## 6. Versionado

Prefijo `/api/v1/` desde el día uno. El agente manda su versión en cada request; si el backend
requiere una versión mínima mayor, responde `426 Upgrade Required` y el agente se autoactualiza.
Con 8 máquinas distribuidas, no poder desplegar un cambio de contrato es un problema real.
