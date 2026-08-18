# 03 — Modelo de datos

> Requiere `02-ARQUITECTURA.md`. Base de datos: **MongoDB 7**.
> Nombres de colecciones y campos en español, para que coincidan con el vocabulario del negocio y
> con lo que dice el cliente en una reunión.

---

## 1. Máquina de estados del mensaje

Esta es la pieza central del sistema. Todo lo demás la sirve.

```
                                    ┌──▶ RETENIDO ──(humano libera)──┐
                                    │        │                        │
                                    │        └──(24 h)──▶ VENCIDO     │
                                    │                                 │
  BORRADOR ──▶ VALIDADO ──▶ TRIAGE ─┤                                 ├──▶ ENCOLADO
                   │                │                                 │        │
                   │                └──▶ EN_ESPERA ──(13:00)──────────┘        │
                   ▼                          │                                │
               RECHAZADO                      ▼                                ▼
             (guardrail)                   VETADO                          ENVIANDO
                                          (humano)                             │
                                                              ┌────────────────┼────────────┐
                                                              ▼                ▼            ▼
                                                          ENVIADO   ENVIADO_SIN_CONFIRMAR  FALLIDO
```

### Definición de cada estado

| Estado | Significado | Quién lo produce | Terminal |
|---|---|---|---|
| `BORRADOR` | El modelo lo redactó, todavía no se validó | job `REDACTAR` | no |
| `VALIDADO` | Pasó todos los guardrails de `05` | backend | no |
| `RECHAZADO` | Violó un guardrail. **Nunca puede salir** | backend | **sí** |
| `RETENIDO` | El triage encendió una señal de riesgo | backend | no |
| `EN_ESPERA` | Sale a las 13:00 salvo que alguien lo frene | backend | no |
| `VETADO` | Un humano lo frenó | panel | **sí** |
| `VENCIDO` | Nadie resolvió un retenido, o pasaron 24 h desde su generación | backend | **sí** |
| `ENCOLADO` | Tiene un job `ENVIAR` esperando en la cola | backend | no |
| `ENVIANDO` | Un agente lo tomó | agente | no |
| `ENVIADO` | Salió y se confirmó en el hilo | agente | **sí** |
| `ENVIADO_SIN_CONFIRMAR` | Se apretó enviar pero no se pudo confirmar. **Dispara alerta** | agente | **sí** |
| `FALLIDO` | No salió | agente | no (reintentable) |

### Reglas duras — implementadas en código, con tests

1. **Sólo `ENCOLADO` puede pasar a `ENVIANDO`.** No hay atajo desde ningún otro estado. Esta
   transición se implementa en un único método y ese método tiene su propio test.
2. **Un mensaje vence a las 24 h desde su generación.** Un borrador del martes no sale el viernes
   con contexto viejo: es una forma silenciosa de escribir algo que ya no aplica.
3. **`ENVIADO` requiere confirmación visual del hilo.** Sin confirmación va a
   `ENVIADO_SIN_CONFIRMAR` y alerta. Nunca se asume que salió.
4. **Los `RETENIDOS` que nadie resuelve van a `VENCIDO`, no a `ENCOLADO`.** Liberarlos por defecto
   invertiría el sentido del triage: son justamente los casos donde un error cuesta caro.
5. **`RECHAZADO`, `VETADO` y `VENCIDO` son terminales.** No hay forma programática de resucitarlos.
   Si hay que mandar ese mensaje, se genera uno nuevo.

---

## 2. Colecciones

### 2.1 `vendedores`

```javascript
{
  _id: ObjectId,
  nombre: "Rocío Fernández",
  email: "rocio@cliente.com",          // login por magic link
  rol: "vendedor",                      // vendedor | supervisor | admin
  machine_id: "PC-1",
  telefono_linea: "+5491144405036",     // E.164, la línea desde la que sale
  activo: true,
  pausado_hasta: null,                  // ISODate | null
  tope_diario: 20,
  ventana_horaria: { inicio: "09:00", fin: "19:00", dias: [1,2,3,4,5] },
  hora_envio: "13:00",
  acepto_condiciones_en: ISODate,       // ver 05 §6 — bloqueante para el Sprint 5
  creado_en: ISODate
}
```

`acepto_condiciones_en` no es burocracia: si es `null`, el backend **rechaza** encolar envíos para
ese vendedor. Salen mensajes en su nombre; tiene que constar que lo sabe.

### 2.2 `maquinas`

```javascript
{
  _id: "PC-1",
  vendedor_id: ObjectId,
  device_id: "chrome-device-abc123",    // fijar por máquina, ver 07
  token_hash: "argon2id$...",           // nunca el token en claro
  token_rotado_en: ISODate,
  ultimo_heartbeat: ISODate,
  estado: "online",                     // online | offline | degradado
  version_agente: "2.1.0",
  claude_version: "2.4.1",
  diagnostico: {
    chrome_ok: true,
    whatsapp_sesion_ok: true,
    permiso_mcp_ok: true,
    permiso_sitio_ok: true,
    verificado_en: ISODate
  }
}
```

`estado` se deriva: `online` si `ultimo_heartbeat` < 60 s, `degradado` si algún flag de
`diagnostico` es `false`, `offline` en otro caso.

### 2.3 `corridas`

```javascript
{
  _id: "20260817-generacion",           // {fecha}-{tipo}
  fecha: "2026-08-17",
  tipo: "generacion",                   // generacion | envio
  modo: "real",                         // prueba | real
  disparada_por: "cron" ,               // cron | ObjectId de usuario
  estado: "completada",                 // pendiente | en_curso | completada | abortada
  canario: { enviados: 3, ok: 3, liberado_en: ISODate },
  contadores: { generados: 18, validados: 17, retenidos: 3, enviados: 14, fallidos: 0 },
  costo_usd: 2.41,
  iniciada_en: ISODate,
  terminada_en: ISODate
}
```

### 2.4 `chats`

```javascript
{
  _id: ObjectId,
  run_id: "20260817-generacion",
  vendedor_id: ObjectId,
  contacto_nombre: "Rocío",             // como figura en WhatsApp
  contacto_id: "+5491144405036",        // E.164 normalizado — ver §4
  ultimo_mensaje_resumen: "Preguntó por el precio del modelo X",  // ⚠ UNA línea, ver 05 §5
  ultimo_lo_mando: "cliente",           // cliente | vendedor
  antiguedad_dias: 6,
  creado_en: ISODate                    // TTL 90 días
}
```

**No se guarda el texto completo de la conversación del cliente.** Sólo este resumen de una línea.
Es una decisión de privacidad, documentada en `05` §5 y en `10-DECISIONES.md` (D1).

### 2.5 `mensajes` — el corazón del sistema

```javascript
{
  _id: ObjectId,
  run_id: "20260817-generacion",
  vendedor_id: ObjectId,
  machine_id: "PC-1",
  chat_id: ObjectId,

  contacto_nombre: "Rocío",
  contacto_id: "+5491144405036",

  texto_generado: "Hola Rocío, quería...",   // lo que produjo el modelo
  texto_final: "Hola Rocío, quería...",      // lo que realmente sale (editable)
  editado_por: null,                          // ObjectId | null
  editado_en: null,

  estado: "EN_ESPERA",
  triage: {
    senales: [],                              // ver 05 §3
    riesgo: "bajo"                            // bajo | alto
  },

  sale_a_las: ISODate,                        // 13:00 del día
  vence_en: ISODate,                          // generacion + 24 h
  vetado_por: null,
  motivo_veto: null,

  enviado_en: null,
  confirmado: false,
  intentos: 0,
  motivo_fallo: null,

  idempotency_key: "sha256:...",              // hash(run_id + contacto_id + texto_final)
  creado_en: ISODate
}
```

### 2.6 `jobs`

```javascript
{
  _id: ObjectId,
  tipo: "ENVIAR",                       // DIAGNOSTICO | LISTAR_CHATS | REDACTAR | ENVIAR
  machine_id: "PC-1",
  payload: { mensaje_id: ObjectId },    // nunca texto de prompt, ver 05 §7
  estado: "pendiente",                  // pendiente | tomado | hecho | fallido
  disponible_desde: ISODate,            // así se implementa el jitter
  tomado_en: null,
  intentos: 0,
  max_intentos: 2,
  resultado: {
    ok: null,
    data: null,
    raw: null,                          // SIEMPRE presente, ver 05 §8
    stderr: null,
    duracion_ms: null,
    costo_usd: null
  },
  creado_en: ISODate
}
```

**La cola es MongoDB, no Redis.** Con 160 jobs por día, un `findOneAndUpdate` atómico alcanza y
sobra. Menos piezas móviles que mantener. Ver `10-DECISIONES.md`.

Cómo un agente toma un job (operación atómica, sin condición de carrera):

```python
job = await db.jobs.find_one_and_update(
    {"machine_id": machine_id,
     "estado": "pendiente",
     "disponible_desde": {"$lte": datetime.utcnow()}},
    {"$set": {"estado": "tomado", "tomado_en": datetime.utcnow()},
     "$inc": {"intentos": 1}},
    sort=[("disponible_desde", 1)],
    return_document=ReturnDocument.AFTER,
)
```

### 2.7 `auditoria` — append only

```javascript
{
  _id: ObjectId,
  timestamp: ISODate,
  actor: ObjectId | "sistema",
  actor_nombre: "Juan (dueño)",
  accion: "mensaje.vetado",             // ver catálogo abajo
  entidad_tipo: "mensaje",
  entidad_id: ObjectId,
  antes: { estado: "EN_ESPERA" },
  despues: { estado: "VETADO", motivo: "el cliente ya compró" },
  ip: "190.x.x.x"
}
```

**Esta colección no acepta `update` ni `delete`.** Se configura con un rol de MongoDB que sólo
permite `insert` y `find`. Es lo que te salva cuando un cliente se queja tres meses después.

Acciones a auditar como mínimo: `corrida.iniciada`, `mensaje.editado`, `mensaje.vetado`,
`mensaje.liberado`, `mensaje.enviado`, `config.cambiada`, `sistema.pausado`, `sistema.reanudado`,
`vendedor.pausado`, `token.rotado`.

Los cambios de configuración se auditan igual que los mensajes: saber en qué modo estaba el
sistema es indispensable para reconstruir un incidente.

### 2.8 `contactos_bloqueados`

```javascript
{
  _id: ObjectId,
  contacto_id: "+5491144405036",
  motivo: "pidió no recibir seguimientos",
  origen: "manual",                     // manual | respuesta_negativa | automatico
  creado_por: ObjectId | "sistema",
  creado_en: ISODate
}
```

Un contacto acá **no recibe nada, nunca**, sin importar qué diga la corrida. Se verifica en el
backend al validar y otra vez en el agente antes de escribir.

### 2.9 `configuracion`

Documento único, versionado en `auditoria` ante cada cambio.

```javascript
{
  _id: "global",
  ventana_veto_minutos: 300,            // 08:00 → 13:00. 0 = full auto
  triage_activo: true,
  hora_generacion: "08:00",
  hora_envio: "13:00",
  tope_por_corrida: 25,
  tope_diario_maquina: 20,
  tope_diario_global: 160,
  antiduplicado_dias: 7,
  jitter_segundos: { min: 45, max: 180 },
  canario: { cantidad: 3, espera_minutos: 10 },
  largo_maximo_mensaje: 600,
  vencimiento_horas: 24,
  presupuesto_diario_usd: 15,
  pausa_global: { activa: false, motivo: null, desde: null }
}
```

---

## 3. Índices

```javascript
// Anti-duplicados de 7 días en O(1) — el más importante
db.mensajes.createIndex({ contacto_id: 1, enviado_en: -1 })

// Un reintento nunca envía dos veces
db.mensajes.createIndex({ idempotency_key: 1 }, { unique: true })

// El poll del agente tiene que ser barato: corre 8 veces cada 10 s
db.jobs.createIndex({ machine_id: 1, estado: 1, disponible_desde: 1 })

// Sala de salida
db.mensajes.createIndex({ estado: 1, sale_a_las: 1 })
db.mensajes.createIndex({ run_id: 1, estado: 1 })

// Auditoría
db.auditoria.createIndex({ timestamp: -1 })
db.auditoria.createIndex({ entidad_id: 1, timestamp: -1 })

// Exclusiones
db.contactos_bloqueados.createIndex({ contacto_id: 1 }, { unique: true })

// TTL — privacidad (D1)
db.chats.createIndex({ creado_en: 1 }, { expireAfterSeconds: 7776000 })   // 90 días
db.jobs.createIndex({ creado_en: 1 }, { expireAfterSeconds: 2592000 })    // 30 días
```

**`mensajes` y `auditoria` no tienen TTL.** Son el registro que defiende al cliente ante un
reclamo, y son datos propios, no del tercero.

---

## 4. Normalización de contactos — leer con atención

El MVP mezclaba `"Rocio"` y `"+54 9 11 4440-5036"` como identificadores. **Eso rompe el
anti-duplicados**: el mismo contacto con dos nombres se escapa y recibe dos mensajes.

Regla del sistema:

- **`contacto_id` es siempre E.164** (`+5491144405036`). Es la clave para duplicados, exclusiones
  y verificación de identidad.
- **`contacto_nombre` es sólo para mostrar.** Nunca se usa para decidir nada.
- Cuando WhatsApp Web muestra un nombre agendado y no el número, **el número se resuelve al abrir
  el chat**, en el paso de verificación. Si no se puede resolver, el envío se **aborta**.

Función única de normalización en `core/contactos.py`, con tests para los formatos argentinos
(`11 4440-5036`, `+54 11 4440 5036`, `0111544405036`, `+549 11 4440-5036`). No la reimplementes en
otro lado.

---

## 5. Qué NO se guarda

| Dato | Se guarda | Por qué |
|---|---|---|
| Texto completo de mensajes del cliente | **No** | Privacidad. No hace falta para el producto |
| Resumen de una línea del último mensaje | Sí, TTL 90 días | Necesario para redactar y para el triage |
| Texto que enviamos nosotros | Sí, indefinido | Es dato propio y es la defensa ante un reclamo |
| Adjuntos, imágenes, audios | **No** | Fuera de alcance |
| Agenda de contactos del vendedor | **No** | Sólo los contactos que aparecen en una corrida |
| Token del agente en claro | **No** | Sólo el hash |

Si alguien necesita guardar algo que no está en esta tabla, es una decisión de producto: se
discute y se agrega a `10-DECISIONES.md` antes de implementarse.
