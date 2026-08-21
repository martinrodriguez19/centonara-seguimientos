# 01 — El proyecto

> Empezá acá. Si sólo vas a leer un documento, que sea éste.

---

## 1. Qué hacemos

Nuestro cliente vende materiales. Su equipo comercial atiende por WhatsApp, y el problema es
viejo: **las conversaciones se enfrían**. Un cliente pregunta el lunes, el vendedor responde, y
ahí queda. A los quince días esa venta no existe — no porque el cliente haya dicho que no, sino
porque nadie insistió.

El sistema hace esto:

1. El dueño entra a una página y **aprieta un botón**
2. En cada Mac del equipo, Claude abre WhatsApp Web y **lee los chats recientes**
3. Por cada chat, **redacta un seguimiento** que retoma lo que efectivamente se habló
4. El dueño puede mirar los borradores y frenar los que quiera
5. **Se envían**, espaciados, desde la línea del propio vendedor

El valor está en el punto 3. No es un "hola, ¿seguís interesado?" masivo — es un mensaje que hace
referencia a la conversación real. Eso es lo que un modelo hace bien y una plantilla no.

**Volumen: 15 a 20 mensajes por vendedor por corrida.** Con 5 vendedores, unos 100 por día.

## 2. Cuándo corre

Cuando el dueño lo dispara. En la práctica, alrededor del mediodía: los vendedores dejan la
computadora prendida durante el almuerzo y el trabajo pasa ahí.

No hay corrida automática. El sistema no se despierta solo. **Si nadie aprieta el botón, no pasa
nada** — y eso es una característica, no una limitación: el dueño sabe siempre por qué salieron
mensajes hoy.

## 3. Lo que el sistema NO es

- **No es un chatbot.** Manda un mensaje y termina. Si el cliente responde, sigue el vendedor.
- **No es envío masivo.** Cada mensaje es distinto y va a una conversación que ya existía.
- **No contacta desconocidos.** Sólo chats abiertos, con gente que ya habló con el vendedor.
- **No usa la API oficial de WhatsApp.** Usa WhatsApp Web, el mismo que usa una persona.

## 4. Cómo se ve desde afuera

**El dueño** entra a una página, ve las máquinas prendidas, aprieta un botón. A los pocos minutos
tiene los borradores. Puede frenar los que no le gusten. Aprieta enviar y salen espaciados.

**El vendedor** deja la Mac prendida. Un ícono en la barra de menú le dice que el sistema está
funcionando y le permite pausarlo cuando no quiere que salga nada.

**El cliente final** recibe un mensaje de su vendedor de siempre, desde el número de siempre.

## 5. Por qué hay que tener cuidado

Los mensajes salen **desde la línea personal del vendedor, en su nombre**. Del otro lado hay
clientes reales.

| Error | Consecuencia |
|---|---|
| Mensaje al contacto equivocado | Un cliente recibe algo destinado a otro, con datos de un tercero |
| Mensaje inapropiado al contacto correcto | Ej.: "¿avanzamos con el pedido?" a alguien que ayer puso un reclamo |
| Demasiados mensajes, o con patrón robótico | WhatsApp bloquea la línea. El vendedor pierde su herramienta de trabajo |

Todo el diseño está organizado alrededor de que estos tres no pasen. **No es ciberseguridad —
nadie está atacando el sistema. Es corrección: que el sistema no le arruine el día a nadie.**

## 6. De dónde venimos: el MVP

Existe una Fase 1 validada y funcionando:

```
n8n → HTTP POST → agent.py (Python) → claude -p --chrome
    → extensión Claude in Chrome → web.whatsapp.com (SÓLO LECTURA)
```

Una máquina. Lee los chats recientes, genera borradores contextualizados. La calidad se validó
como utilizable. No envía nada.

**Dos cosas que el MVP dejó probadas y no se rediscuten:**

- **Leer los chats recientes funciona.** Es el criterio validado. No hay que inventar un
  detector de "conversación fría": los chats recientes de un vendedor con 200 conversaciones
  abiertas ya son, en su mayoría, seguimientos pendientes.
- **La cantidad de máquinas es variable.** El n8n del MVP ya permitía sumar y restar máquinas.
  El sistema nuevo tiene que conservar esa propiedad: se dan de alta y de baja desde el panel.

Las siete lecciones técnicas del MVP están en [`MVP-REFERENCIA.md`](MVP-REFERENCIA.md) §6 y se
convirtieron en chequeos automáticos del agente.

## 7. Qué cambia respecto del MVP

| | MVP | Ahora |
|---|---|---|
| Máquinas | 1, Windows | **N, macOS** — alta y baja desde el panel |
| Envío | no | **sí** |
| Interfaz | un `.bat` | página web con un botón |
| Estado | una planilla | base de datos |
| Red | misma LAN, IP fija | cada Mac desde donde sea |
| Auditoría | no hay | completa |
| Límites | ninguno | topes en código |

Se construye desde cero. Lo único que se migra literal es el prompt, porque su calidad está
validada.

## 8. Alcance: qué está adentro y qué no

**Adentro:** leer chats, redactar, revisar, enviar, registrar, dar de alta y baja máquinas,
pausar, frenar.

**Afuera, y no se discute hasta que el sistema esté andando:** responder mensajes entrantes,
API oficial de WhatsApp, integración con CRM, app móvil, más de un cliente, que el modelo decida
a quién escribirle.

## 9. Cómo se trabaja

- **Un solo entorno: producción.** No hay staging. Todavía no hay usuarios reales del panel, así
  que el lugar donde se prueba es producción. Cuando haya vendedores activos esto se revisa.
- **Una sola rama: `main`.** Se despliega desde ahí.
- **Sin plazos.** Las fases tienen criterio de salida verificable, no fecha. Una fase termina
  cuando se cumple el criterio.
- **Sin ventana de despliegue.** Se despliega cuando está listo. El sistema no corre solo: si
  algo se rompe, no sale ningún mensaje hasta que alguien apriete el botón.

## 10. Stack

| Capa | Tecnología |
|---|---|
| Panel | Next.js 15 + TypeScript + Tailwind + shadcn/ui |
| Backend | Python 3.12 + FastAPI + Pydantic v2 + APScheduler |
| Base de datos | MongoDB Atlas |
| Cola | MongoDB. Sin Redis |
| Agente | Python + Playwright, corriendo en cada Mac |
| Lectura y redacción | `claude -p --chrome` con la extensión Claude in Chrome |
| Infraestructura | Render (backend, panel, cron de backup) + Cloudflare + R2 |
| CI | GitHub Actions |

Deliberadamente afuera: n8n, staging, Kubernetes, microservicios, Redis, Auth.js, colas
distribuidas.

## 11. Glosario

| Término | Significa |
|---|---|
| **Agente** | El programa que corre en la Mac del vendedor |
| **Backend** | El servidor central en Render |
| **Panel** | La página que usa el dueño |
| **Corrida** | Una ejecución completa: leer, redactar, revisar, enviar |
| **Job** | Una unidad mínima de trabajo. Ej.: "redactar el mensaje de este chat" |
| **Borrador** | Un mensaje redactado que todavía no salió |
| **Retenido** | Un borrador apartado automáticamente. Necesita decisión humana |
| **Guardrail** | Un límite implementado en código |
| **Destinos permitidos** | La lista blanca de números a los que el sistema puede escribir |
| **Kill switch** | Botón que frena todo de inmediato |
| **E.164** | Formato internacional de teléfono: `+5491144405036` |
