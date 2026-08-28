# 02 — Arquitectura, datos y contratos

> Requiere [`01-PROYECTO.md`](01-PROYECTO.md). Este documento reemplaza a los tres viejos
> (arquitectura, modelo de datos y contratos de API): eran tres archivos para un sistema que
> entra en uno.

---

## 1. Vista general

```
   ┌─────────────────── RENDER ────────────────────┐
   │                                               │
   │   ┌──────────┐        ┌──────────────────┐    │        ┌──────────────┐
   │   │ Next.js  │───────▶│  FastAPI         │────┼───────▶│ MongoDB      │
   │   │ panel    │        │  + APScheduler   │    │        │ Atlas        │
   │   └──────────┘        │  jobs · reglas   │    │        └──────────────┘
   │                       │  cola · registro │    │
   │                       └──────────────────┘    │
   │   ┌──────────────┐                            │
   │   │ cron backup  │  1 vez por día             │
   │   └──────────────┘                            │
   └───────────────────────┬───────────────────────┘
                           │  Cloudflare (DNS + proxy)
                           │
        GET  /api/agente/jobs/proximo    ← cada 10 s, saliente
        POST /api/agente/jobs/{id}/resultado
                           │
     ┌───────────┬─────────┴─────────┬───────────┐
  ┌──▼───┐   ┌───▼──┐            ┌───▼──┐    ┌───▼──┐
  │ Mac 1│   │ Mac 2│    ...     │ Mac N│    │ Mac N│   ← agente + Chrome + WhatsApp Web
  └──────┘   └──────┘            └──────┘    └──────┘
```

**Tres servicios en Render, no ocho.** Ninguna Mac abre puertos: todo sale hacia afuera.

## 2. Las cinco decisiones que definen esto

### 2.1 El agente pregunta, el servidor no empuja

El MVP hacía al revés: n8n mandaba un POST a una IP fija de la LAN. Eso exige IP fija, regla de
firewall y misma red.

Ahora cada Mac hace `GET /api/agente/jobs/proximo` cada 10 segundos. Si no hay trabajo, `204`.

Qué gana: cero configuración de red por máquina, funciona desde cualquier lado, si la Mac está
apagada el job espera en vez de fallar, y **la consulta misma es el latido**: el servidor sabe
quién está prendido.

*Descartado:* WebSocket y long-poll de 25 s. Con pocas máquinas consultando cada 10 segundos, un
`GET` normal alcanza — y evita depender de que Render y Cloudflare sostengan conexiones largas,
que era una incógnita sin verificar del plan viejo.

### 2.2 La unidad de trabajo es el ítem, no la corrida

El MVP hacía todo en una invocación. Si fallaba en el chat 4 de 5, se perdían los 5.

| Job | Entrada | Salida | Motor |
|---|---|---|---|
| `LISTAR` | `n_chats` | chats con resumen | Claude + navegador |
| `REDACTAR` | 1 chat | 1 borrador | Claude, **sin navegador** |
| `ENVIAR` | 1 mensaje | enviado / fallido | Playwright, sin modelo |
| `DIAGNOSTICO` | — | los 9 chequeos | código |

Cada uno tiene su timeout y su registro. Un fallo en el mensaje 12 no toca a los otros 19.

**`REDACTAR` no necesita el navegador.** Una vez que `LISTAR` extrajo el contexto, redactar es una
llamada de texto plano. Separarlos saca el paso más frecuente del circuito caro.

### 2.3 El envío es código, no modelo

La decisión menos obvia y la más importante. Un modelo es excelente leyendo una conversación y
redactando. Es mal candidato para abrir el chat correcto y apretar enviar.

| | Modelo mirando la pantalla | Código con selectores |
|---|---|---|
| Abrir el chat correcto | interpreta una captura | busca el identificador y **compara el header** |
| Escribir el texto exacto | puede reformular | pega literal |
| Costo por mensaje | alto | prácticamente cero |
| Cuando falla | de forma silenciosa o creativa | excepción clara |

```python
# Esto es una garantía. Una instrucción en un prompt es una intención.
encontrado = await resolver_identificador_del_chat_abierto(page)
if encontrado != contacto_id:
    raise ContactoNoCoincide(esperado=contacto_id, encontrado=encontrado)
```

**Contrapartida honesta:** los selectores de WhatsApp Web cambian sin aviso. Se mitiga con dos
cosas: la verificación **falla cerrada** (si no encuentra el header, aborta sin escribir) y un
chequeo de selectores que corre antes de cada corrida.

### 2.4 Todo lo que importa vive en FastAPI

Regla: *lo que, si falla, hace salir un mensaje que no debía salir, vive en código versionado y
con tests.*

No hay n8n. Los horarios que hacen falta —vencer borradores viejos, espaciar envíos— los maneja
APScheduler **dentro del mismo proceso de FastAPI**. Con una sola instancia no hace falta más, y
un proceso menos es un proceso menos que mantener.

### 2.5 El sistema se enciende con una lista, no con una variable

En vez de "el código de envío no existe hasta la fase 4", el sistema tiene una **lista de destinos
permitidos** en `configuracion`. El agente sólo escribe a números que estén en esa lista.

- Mientras se construye, la lista tiene los números de prueba. Nada más puede recibir un mensaje.
- Para el piloto, se agregan los contactos que aceptaron.
- Para producción, se cambia a `["*"]`, que es un acto deliberado, registrado y reversible.

Es mejor garantía que "el archivo no existe", porque sobrevive a la fase de construcción y sigue
siendo útil el día que haya que acotar el sistema de nuevo.

---

## 3. Modelo de datos

MongoDB. Nombres en español, para que coincidan con lo que dice el cliente en una reunión.

### 3.1 Estados de un mensaje

```
  BORRADOR ──▶ EN_ESPERA ──▶ ENVIANDO ──▶ ENVIADO
      │             ▲  │          │
      │             │  │          └──(falla, quedan intentos)──▶ EN_ESPERA
      ▼             │  ▼
  RETENIDO ─(libera)┘  └──────────────────▶ DESCARTADO
      │                                          ▲
      └──────────(veto / vence / rechaza)────────┘
```

**Seis estados.** El plan anterior tenía doce; la diferencia eran matices que se representan mejor
con un campo `motivo`.

| Estado | Significado | Terminal |
|---|---|---|
| `BORRADOR` | El modelo lo redactó, todavía no pasó las reglas | no |
| `RETENIDO` | Una señal de riesgo lo apartó. Necesita decisión humana | no |
| `EN_ESPERA` | Validado. Sale cuando le toque | no |
| `ENVIANDO` | Un agente lo tomó | no |
| `ENVIADO` | Salió y se confirmó en el hilo | **sí** |
| `DESCARTADO` | No sale nunca. `motivo`: `rechazado` · `vetado` · `vencido` · `fallido` · `sin_confirmar` | **sí** |

**Cuatro reglas duras, con tests:**

1. Sólo `EN_ESPERA` puede pasar a `ENVIANDO`. Sin atajos, en un único método.
2. Un borrador vence a las 24 h de generado. Un borrador del martes no sale el viernes.
3. `ENVIADO` requiere confirmación visual en el hilo. Sin confirmación, `DESCARTADO` con
   `motivo: "sin_confirmar"` y alerta. Nunca se asume que salió.
   ⚠️ Ojo con lo que eso significa: el mensaje **puede haber salido igual**. `sin_confirmar` es "no
   sabemos", no "no salió" — por eso alerta en vez de reintentar.
4. `DESCARTADO` es terminal. No hay forma programática de resucitarlo: si hay que mandar ese
   mensaje, se genera uno nuevo.

### 3.2 Colecciones

Seis: `vendedores`, `corridas`, `mensajes`, `jobs`, `auditoria`, `configuracion`.

```javascript
// vendedores — una fila por Mac. Alta y baja desde el panel.
{
  _id: ObjectId,
  nombre: "Rocío Fernández",
  maquina: "mac-rocio",              // identificador único, lo elige el admin
  telefono_linea: "+5491144405036",  // E.164, la línea desde la que sale
  token_hash: "...",                 // el token que usa su agente
  activo: true,
  pausado_hasta: null,               // ISODate | null
  tope_diario: 20,
  acepto_condiciones_en: ISODate,    // null = no se le encolan envíos
  ultimo_latido: ISODate,
  diagnostico: { claude_bin: "ok", permiso_mcp: "ok" },
  creado_en: ISODate
}

// corridas
{
  _id: ObjectId,
  disparada_por: "martin@cliente.com",
  modo: "prueba" | "real",
  estado: "generando" | "revision" | "enviando" | "terminada" | "frenada",
  n_chats: 20,
  maquinas: ["mac-rocio", "mac-juan"],
  costo_usd: 0.42,
  creada_en: ISODate,
  terminada_en: ISODate
}

// mensajes
{
  _id: ObjectId,
  corrida_id: ObjectId,
  maquina: "mac-rocio",
  contacto_id: "+5491155667788",     // E.164. Es lo que se compara antes de escribir
  contacto_nombre: "Ferretería Sur",
  resumen_ultimo: "preguntó por chapa galvanizada",   // UNA línea. Se borra a los 90 días
  quien_hablo_ultimo: "contacto" | "vendedor",
  antiguedad_dias: 6,
  texto: "Hola Marcelo, quedamos en...",
  estado: "EN_ESPERA",
  motivo: null,
  senales: ["PALABRA_CONFLICTO"],    // por qué se retuvo, si se retuvo
  clave_idempotencia: "sha256(...)",
  sale_a_las: ISODate,               // con jitter aplicado
  intentos: 0,
  editado_por: null,
  creado_en: ISODate
}

// jobs — la cola
{
  _id: ObjectId,
  tipo: "LISTAR" | "REDACTAR" | "ENVIAR" | "DIAGNOSTICO",
  maquina: "mac-rocio",
  corrida_id: ObjectId,
  payload: { },                      // SÓLO variables validadas. Nunca texto de prompt
  estado: "pendiente" | "tomado" | "listo" | "fallido",
  disponible_desde: ISODate,         // así se implementa el jitter, sin sleep
  intentos: 0,
  raw: "...", stderr: "...",         // SIEMPRE presentes, también en éxito
  costo_usd: 0.03,
  tomado_en: ISODate, terminado_en: ISODate
}

// auditoria — sólo insert. Sin update ni delete, a nivel de rol de MongoDB
{
  _id: ObjectId,
  cuando: ISODate,
  quien: "martin@cliente.com" | "mac-rocio" | "sistema",
  que: "mensaje_enviado" | "corrida_disparada" | "veto" | "kill_switch",
  mensaje_id: ObjectId,
  detalle: { }
}

// configuracion — UN solo documento
{
  _id: "unica",
  pausa_global: false,
  destinos_permitidos: ["+5491155667788"],   // ["*"] = todos. Ver 2.5
  n_chats_por_defecto: 20,
  tope_diario_maquina: 20,
  tope_por_corrida: 25,
  largo_maximo: 600,
  dias_anti_duplicado: 7,
  ventana: { inicio: "09:00", fin: "19:00", dias: [1,2,3,4,5] },
  pausa_entre_envios_s: [45, 180],
  palabras_conflicto: ["reclamo", "problema", "cancelar", "factura", "abogado"],
  actualizado_en: ISODate
}
```

**Índices que importan.** `jobs`: `{estado, maquina, disponible_desde}` — es la consulta de la
cola, corre cada 10 s por máquina. `mensajes`: `{clave_idempotencia}` **único**, que es lo que
impide que un reintento mande el mismo mensaje dos veces; `{contacto_id, creado_en}` para el
anti-duplicado; `{corrida_id, estado}` para el panel.

**Retención del resumen: un `$unset` programado, no un TTL.** Un índice TTL de Mongo borra el
*documento entero*, no un campo. Acá hay que borrar el resumen de la conversación del cliente —dato
de un tercero— y **conservar** el texto que nosotros mandamos, que es dato propio y es la defensa
ante un reclamo. Son dos retenciones distintas sobre el mismo documento, y el TTL no sabe hacer
eso. Lo resuelve una tarea diaria de APScheduler (`purgar_resumenes`).

Donde el TTL **sí** sirve es en `jobs`: el índice va sobre `terminado_en`, que un job vivo no
tiene, así que los terminados se borran solos al mes y la cola no se vacía sola.

---

## 4. Contratos de API

### 4.1 Endpoints del agente

Autenticación: `Authorization: Bearer <token de la máquina>`.

| Método | Ruta | Qué hace |
|---|---|---|
| `POST` | `/api/agente/registrar` | Se presenta al arrancar. Manda versión y diagnóstico |
| `GET` | `/api/agente/jobs/proximo` | Devuelve un job o `204`. `423` si hay pausa global |
| `POST` | `/api/agente/jobs/{id}/resultado` | Reporta. **Siempre con `raw` y `stderr`** |
| `POST` | `/api/agente/latido` | Cada 30 s. Estado y diagnóstico |

**El payload nunca lleva texto de prompt.** Viajan variables acotadas y validadas por Pydantic. Un
backend comprometido no debe poder hacer que el agente ejecute algo arbitrario — es el principio
de `ALLOWED_VARS` del MVP, ahora con esquemas.

```jsonc
// GET /api/agente/jobs/proximo → 200
{
  "id": "6712...",
  "tipo": "ENVIAR",
  "payload": {
    "mensaje_id": "6713...",
    "contacto_id": "+5491155667788",
    "contacto_nombre": "Ferretería Sur",
    "texto": "Hola Marcelo, quedamos en...",
    "modo": "prueba"
  }
}
```

```jsonc
// POST /api/agente/jobs/{id}/resultado
{
  "ok": false,
  "codigo": "CONTACTO_NO_COINCIDE",
  "detalle": { "esperado": "+5491155667788", "encontrado": "+5491133445566" },
  "raw": "...", "stderr": "...", "costo_usd": 0.0
}
```

**Códigos de motivo del envío:**

| Código | Reintenta | Qué pasó |
|---|---|---|
| `CONTACTO_NO_COINCIDE` | **nunca** | El header del chat no es el contacto esperado |
| `NUMERO_NO_RESOLUBLE` | **nunca** | No se pudo leer un E.164 del chat abierto |
| `DESTINO_NO_PERMITIDO` | **nunca** | El número no está en `destinos_permitidos` |
| `CAMPO_NO_VACIO` | sí | Había texto escrito en el chat. Alguien está usándolo |
| `CHAT_NO_ABRE` | sí | No se pudo abrir |
| `SELECTOR_ROTO` | **frena la corrida** | El DOM cambió. Todos los siguientes fallan igual |
| `SIN_CONFIRMAR` | **nunca** | Se apretó enviar y no apareció en el hilo. Alerta |
| `SESION_CAIDA` | sí | WhatsApp Web pide QR — **con el QR a la vista**, no antes de navegar |
| `TIMEOUT` | sí (tope 2) | La página no terminó de cargar (`PaginaNoCargo`): red lenta, Chrome recién abierto |

Reintentar un envío que abortó por identidad incorrecta es la forma exacta de convertir un aborto
correcto en un error real. Por eso la columna del medio no es decorativa.

Dos matices que salieron de la corrida fallida del 27/08: el motor **navega primero y pregunta
por la sesión después** (el orden inverso daba `SESION_CAIDA` con la sesión sana, sobre la
página sin navegar), y el chat se busca **por nombre** con fallback al número (D34) — la
identidad la sigue decidiendo la comparación por número del paso 6. Y desde D35 el canario
frena **por máquina**, no la corrida entera: el kill switch global queda para `SELECTOR_ROTO`
y el botón del panel.

### 4.2 Endpoints del panel

Autenticación: cookie de sesión firmada, emitida contra una contraseña única (`PANEL_PASSWORD`).
Sin correo saliente, sin magic links, sin proveedor externo.

| Método | Ruta | Qué hace |
|---|---|---|
| `POST` | `/api/sesion` | Login con la contraseña. Devuelve la cookie |
| `GET` | `/api/estado` | Máquinas, diagnóstico, corrida en curso, contador del día |
| `POST` | `/api/corridas` | **El botón.** Dispara. Devuelve al instante y encola |
| `GET` | `/api/corridas/{id}` | Progreso y borradores |
| `PATCH` | `/api/mensajes/{id}` | Editar el texto. Revalida todo |
| `POST` | `/api/mensajes/{id}/veto` | `DESCARTADO`, motivo `vetado` |
| `POST` | `/api/mensajes/{id}/liberar` | `RETENIDO` → `EN_ESPERA` |
| `POST` | `/api/corridas/{id}/enviar` | **Sólo el envío real** pasa por acá (D36): pasa los `EN_ESPERA` a la cola, con jitter. Los borradores se encadenan solos al terminar cada `REDACTAR` |
| `POST` | `/api/sistema/pausa` | **Kill switch.** Los jobs dejan de entregarse |
| `GET` | `/api/historial` | Buscable por contacto |
| `POST` `PATCH` `DELETE` | `/api/vendedores` | Alta, baja y edición de máquinas |
| `GET` `PATCH` | `/api/configuracion` | Topes, palabras, destinos permitidos |

**Editar revalida.** Un humano también puede empeorar un mensaje: si escribe `{nombre}` a mano, se
rechaza igual que si lo hubiera escrito el modelo. `PATCH` sólo se acepta en `EN_ESPERA` o
`RETENIDO`; cualquier otro estado devuelve `409`.

### 4.3 Errores

Formato único en toda la API:

```jsonc
{ "error": "GUARDRAIL_PLACEHOLDER", "detalle": "el texto contiene {nombre} sin resolver" }
```

`401` sin sesión o token · `403` sin permiso · `409` estado incompatible · `423` pausa global ·
`422` validación de Pydantic.

---

## 5. Seguridad de la comunicación

Calibrada a lo que esto es: una herramienta interna de una empresa que vende materiales.

- **TLS en todo.** Lo resuelven Render y Cloudflare.
- **Un token por máquina**, generado al dar de alta, guardado hasheado. Se revoca borrando la
  máquina del panel. No hay procedimiento de rotación documentado porque rotar es regenerar.
- **Una contraseña para el panel**, en variable de entorno.
- **El backend nunca manda texto de prompt al agente.**
- Secretos en variables de entorno, nunca versionados. Hay un chequeo de CI que lo verifica.
- MongoDB Atlas con TLS y **un usuario cuyo rol no otorga `update` ni `remove` sobre
  `auditoria`** (`app/core/permisos.py`). Es lo que hace inmutable al registro; ver R5 y
  `docs/RUNBOOK-auditoria.md` para aplicarlo en Atlas.

Lo que **no** hacemos, a propósito: rotación programada de credenciales, proyectos separados de
Atlas, límite de peticiones por IP, escudo anti-DDoS. Nadie está atacando esto, y cada una de esas
medidas cuesta tiempo que rinde más en otro lado.

## 6. Qué NO hacemos y por qué

| No hacemos | Por qué |
|---|---|
| Staging | No hay usuarios. Producción es el lugar donde se prueba |
| n8n | Hacía tres crons. APScheduler los hace dentro del backend |
| Microservicios, Kubernetes, Redis | Es una herramienta para un equipo comercial chico |
| Long-poll de 25 s | Un `GET` cada 10 s alcanza y no depende de conexiones largas |
| Auth.js, magic links, correo saliente | Una contraseña. Entran una o dos personas |
| `ChannelAdapter` para la API oficial | Fuera de alcance sin fecha. Se define el día que haga falta |
| Que el modelo decida a quién escribirle | Nunca. El modelo redacta; el código decide y envía |
