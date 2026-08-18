# 02 — Arquitectura

> Requiere haber leído `01-CONTEXTO.md`.

---

## 1. Vista general

```
                        INTERNET  (sólo conexiones salientes desde las PCs)
                                      │
   ┌──────────────────────────────────┼──────────────────────────────────┐
   │  RENDER  (servicios administrados)                                  │
   │                                  │                                  │
   │   ┌──────────┐   ┌───────────────▼────────────┐   ┌─────────────┐   │
   │   │ Next.js  │──▶│      FastAPI (core)        │──▶│  MongoDB    │   │
   │   │ panel    │   │  auth · jobs · guardrails  │   │             │   │
   │   └──────────┘   │  máquina de estados        │   └─────────────┘   │
   │                  │  triage · auditoría        │                     │
   │                  └────┬──────────────────┬────┘                     │
   │                  ┌────▼─────┐      ┌─────▼────┐                     │
   │                  │   n8n    │      │  Worker  │                     │
   │                  │ horarios │      │ APScheduler                    │
   │                  │ avisos   │      │ jitter   │                     │
   │                  └──────────┘      └──────────┘                     │
   │                          ▲                                          │
   │              TLS y dominio: los resuelve Render                     │
   └──────────────────────────┼──────────────────────────────────────────┘
                              │
                     Cloudflare (DNS, proxy, escudo)
                              │
              GET  /api/agent/jobs/next     (long-poll cada ~10 s)
              POST /api/agent/jobs/{id}/result
                              │
     ┌──────────┬─────────────┼─────────────┬──────────┐
     │          │             │             │          │
 ┌───▼───┐  ┌───▼───┐     ┌───▼───┐     ┌───▼───┐
 │ PC-1  │  │ PC-2  │ ... │ PC-7  │     │ PC-8  │   ← agente + Chrome + WhatsApp Web
 └───────┘  └───────┘     └───────┘     └───────┘
```

**Ninguna PC de vendedor abre puertos ni recibe conexiones.** Todo sale hacia afuera.

## 2. Las cinco decisiones que definen la arquitectura

### 2.1 El agente consulta, el servidor no empuja

**El MVP hacía al revés:** n8n mandaba un POST a `http://192.168.0.101:8787`. Eso exige IP fija,
regla de firewall y que todo esté en la misma red. Con 8 vendedores —algunos en la oficina, otros
con notebook desde casa— es inmantenible.

**En la v2 el agente pregunta.** Cada ~10 segundos hace `GET /api/agent/jobs/next`. El servidor
retiene la conexión hasta 25 segundos (long-polling) y devuelve un job o un `204 No Content`.

Qué gana:

- Cero configuración de red por máquina. No hay firewall que tocar
- Funciona desde cualquier red, sin VPN
- Si la PC está apagada, el job queda encolado en vez de fallar
- El poll **es** el heartbeat: el servidor sabe en tiempo real qué agentes están vivos

*Alternativa descartada:* WebSocket. Más eficiente, más piezas móviles. Para 8 clientes que
consultan cada 10 segundos, long-poll HTTP sobra.

### 2.2 La unidad de trabajo es el ítem, no la corrida

**El MVP hacía todo en una sola invocación del modelo.** Si fallaba en el chat 4 de 5, se perdían
los 5.

**En la v2 cada paso es un job independiente:**

| Job | Entrada | Salida | Motor |
|---|---|---|---|
| `LISTAR_CHATS` | `n_chats` | chats con resumen y antigüedad | Modelo + navegador |
| `REDACTAR` | 1 chat | 1 borrador | Modelo, **sin navegador** |
| `ENVIAR` | 1 mensaje | enviado / fallido | Código determinístico |

Cada uno tiene su propio timeout, sus reintentos y su registro. Un fallo en el mensaje 12 no toca
a los otros 19.

**Detalle que baja el costo mucho:** `REDACTAR` no necesita el navegador. Una vez que
`LISTAR_CHATS` extrajo el contexto, redactar es una llamada de texto plano. Separarlos saca el
paso más frecuente del circuito caro.

### 2.3 El envío es código, no modelo

**Esta es la decisión menos obvia y la más importante.**

Un modelo de lenguaje es excelente leyendo una conversación y redactando una respuesta. Es un mal
candidato para abrir el chat correcto y apretar enviar.

| | Modelo mirando la pantalla | Código con selectores |
|---|---|---|
| Abrir el chat correcto | interpreta una captura | busca por número exacto y **compara el header** |
| Escribir el texto exacto | puede reformular | pega literal |
| Costo por mensaje | alto | prácticamente cero |
| Reproducible | no | sí |
| Cuando falla | de forma silenciosa o creativa | excepción clara |

El riesgo número uno del proyecto —escribir en el chat equivocado— se mitiga muchísimo mejor con
una aserción de código que con una instrucción en un prompt.

```python
# Esto es una garantía. Una instrucción en un prompt es una intención.
header = page.locator('[data-testid="conversation-header"]').inner_text()
if normalizar(header) != normalizar(contacto_esperado):
    raise ContactoNoCoincide(esperado=contacto_esperado, encontrado=header)
```

**Contrapartida honesta:** los selectores de WhatsApp Web cambian sin aviso y hay que mantenerlos.
Se mitiga con dos cosas: el paso de verificación **falla cerrado** (si no encuentra el header,
aborta y no escribe nada), y un smoke test diario que detecta el cambio antes que un envío real.

**El modelo se queda donde aporta:** leer conversaciones y redactar seguimiento contextualizado.

### 2.4 La lógica de negocio vive en FastAPI, no en n8n

**Regla:** *todo lo que, si falla, hace salir un mensaje que no debía salir, vive en código
versionado y con tests.*

| En FastAPI | En n8n |
|---|---|
| Topes por corrida y por día | Horarios de disparo |
| Anti-duplicados | Notificaciones y alertas |
| Ventana horaria y jitter | Reportes diarios |
| Validación de placeholders | Escalamientos |
| Triage | Integraciones con el CRM |
| Máquina de estados | Exportes |
| Autorización | |

n8n se queda porque es visible y el cliente puede tocarlo; ese es su valor. Pero **deja de ser el
cerebro**. Un tope que vive en un nodo de n8n lo desconecta cualquiera con acceso al editor.

### 2.5 El canal está detrás de una interfaz

```
ChannelAdapter (interfaz)
├── WhatsAppWebAdapter      ← hoy: Chrome + Playwright
└── WhatsAppCloudAdapter    ← futuro: API oficial de WhatsApp Business
```

Definirlo ahora cuesta poco. Hace que el día que haya que migrar a la API oficial sea cambiar una
implementación, no reescribir el producto.

## 3. El ciclo de un día

```
08:00  n8n dispara la corrida     (o el dueño aprieta el botón)
       │
       ├─▶ backend crea la corrida y encola 1 LISTAR_CHATS por vendedor activo
       │
08:05  agentes toman sus jobs y leen WhatsApp Web
       │
       ├─▶ backend recibe los chats, encola 1 REDACTAR por chat
       │
08:20  borradores listos → pasan por GUARDRAILS
       │                    │
       │                    ├─ falla alguno → RECHAZADO (nunca sale)
       │                    └─ pasa        → TRIAGE
       │                                     │
       │                                     ├─ señal de riesgo → RETENIDO
       │                                     └─ limpio          → EN_ESPERA
       │
       ⏳ ventana de veto: el dueño puede entrar y frenar. Si no entra, no pasa nada.
       │
13:00  ENCOLADO → los agentes toman jobs ENVIAR de a uno
       │
       ├─▶ canario: salen los 3 primeros, se espera 10 min
       ├─▶ si los 3 salieron bien, se libera el resto
       └─▶ entre envío y envío, pausa aleatoria de 45–180 s
       │
14:30  todo enviado. Registro completo en auditoría
       │
Día siguiente: pantalla de revisión posterior con lo que salió
```

## 4. Componentes

### 4.1 Backend (FastAPI)

Un monolito bien organizado. **No microservicios**: son 160 mensajes por día.

```
backend/
├── app/
│   ├── api/
│   │   ├── agent.py          # endpoints que consume el agente
│   │   ├── panel.py          # endpoints que consume el front
│   │   └── deps.py           # autenticación, autorización
│   ├── core/
│   │   ├── guardrails.py     # ⚠️ los límites. Ver 05
│   │   ├── triage.py         # clasificador de riesgo
│   │   ├── estados.py        # máquina de estados
│   │   └── programador.py    # jitter, ventanas, canario
│   ├── modelos/              # esquemas Pydantic
│   ├── repositorios/         # acceso a Mongo
│   └── servicios/
│       ├── corridas.py
│       ├── mensajes.py
│       └── auditoria.py
└── tests/
    └── guardrails/           # ⚠️ los tests que no pueden faltar
```

### 4.2 Panel (Next.js)

```
panel/
├── app/
│   ├── (auth)/login/
│   ├── panel/                # estado de máquinas, botón, kill switch
│   ├── sala-de-salida/       # retenidos + en espera con cuenta regresiva
│   ├── revision/             # lo que salió ayer
│   ├── historial/
│   ├── configuracion/
│   └── vendedores/
└── components/
```

### 4.3 Agente (Python → .exe)

Ver `07-EL-AGENTE.md`.

### 4.4 n8n

Tres workflows, nada más:

1. Cron 08:00 → `POST /api/corridas`
2. Cron 12:45 → si hay retenidos, avisar al dueño
3. Webhook desde el backend → alertas (canario fallido, agente caído, cliente molesto)

## 5. Seguridad de la comunicación

- **TLS en todo.** Render emite y renueva los certificados solo
- **Un token por máquina**, rotable y revocable individualmente. Nunca un token compartido: si se
  filtra uno, se revoca esa máquina y nada más
- **El backend nunca manda texto de prompt al agente.** Se mantiene el principio del MVP: viajan
  variables acotadas y validadas, no instrucciones. Un backend comprometido no debe poder hacer
  que el agente ejecute algo arbitrario
- Rate limiting en los endpoints del agente
- MongoDB no expuesto a internet
- Secretos en variables de entorno, nunca en archivos versionados

## 6. Qué NO hacemos y por qué

| No hacemos | Por qué |
|---|---|
| Microservicios | 8 usuarios. Un monolito organizado es lo correcto |
| Redis / Celery | Mongo como cola alcanza para 160 jobs diarios |
| Kubernetes | Render con servicios administrados |
| Que el modelo decida a quién escribirle | El modelo redacta; el código decide y envía |
| Lógica de negocio en n8n | Ver 2.4 |
| Construir Coexistence ahora | Fuera de alcance. Pero el adapter queda listo |
| Multi-tenancy | Un solo cliente. Se revisa si aparece un segundo |
