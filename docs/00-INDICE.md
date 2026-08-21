# Documentación

> Ocho documentos. Antes eran veintitrés. Si algo no está acá es porque no hacía falta escribirlo
> todavía.

---

## Leelos en este orden

| # | Documento | Para qué | Cuándo |
|---|---|---|---|
| 01 | [El proyecto](01-PROYECTO.md) | Qué construimos y por qué | Primero, siempre |
| 02 | [Arquitectura, datos y contratos](02-ARQUITECTURA.md) | Cómo está armado | Antes de tocar backend o panel |
| 03 | [Reglas, guardrails y riesgos](03-REGLAS.md) | Los límites que no se cruzan | **Todos, sin excepción** |
| 04 | [El agente y el entorno](04-AGENTE.md) | Lo que corre en la Mac del vendedor | Antes de tocar `agente/` |
| 05 | [Fases](05-FASES.md) | Qué se construye y en qué orden | Al empezar una fase |
| 06 | [Decisiones](06-DECISIONES.md) | Por qué las cosas son como son | Cuando algo te parezca raro |
| 07 | [Convenciones](07-CONVENCIONES.md) | Git, código, tests, despliegue | Antes del primer PR |

Y dos que no se leen de corrido:

| Documento | Qué es |
|---|---|
| [EQUIPO.md](EQUIPO.md) | Los seis agentes de desarrollo y su prompt base |
| [PROMPTS.md](PROMPTS.md) | Los 42 prompts de ejecución, en orden |
| [PENDIENTE-CON-MAQUINA.md](PENDIENTE-CON-MAQUINA.md) | **Lo que falta y necesita una máquina.** Empezá acá si volvés después de un tiempo |

Y tres runbooks: [`RUNBOOK-auditoria.md`](RUNBOOK-auditoria.md) (el rol de MongoDB que hace
inmutable el registro), [`RUNBOOK-backups.md`](RUNBOOK-backups.md) y
[`RUNBOOK-rollback.md`](RUNBOOK-rollback.md).

Más [`MVP-REFERENCIA.md`](MVP-REFERENCIA.md), que explica qué hacer con el MVP congelado en
`referencia/mvp-fase1/` — sobre todo los siete problemas que ya costaron días de depuración.

---

## Si tenés quince minutos

Leé [`03-REGLAS.md`](03-REGLAS.md) entero. Es corto y es el único que, si lo salteás, puede
terminar en un mensaje comercial en el chat equivocado de un cliente real.

---

## Lo que cambió respecto de la versión anterior

Si venías del plan viejo —14 documentos numerados, 8 sprints, 75 prompts— esto es lo que se movió:

| Antes | Ahora | Por qué |
|---|---|---|
| Máquinas Windows 11 | **macOS** | El parque real es Mac (D16) |
| Cantidad fija de máquinas | **Variable**, alta y baja desde el panel | Como el n8n del MVP |
| Staging + producción, 8 servicios | **Sólo producción, 3 servicios** | No hay usuarios que proteger (D17) |
| n8n para horarios y avisos | **APScheduler dentro de FastAPI** | Hacía tres crons y costaba dos servicios (D18) |
| 14 semanas, 8 sprints con duración | **5 fases con criterio de salida** | Sin plazos (D19) |
| Sprints ordenados por riesgo | **Fases ordenadas por hardware**: F1–F4 desde Windows, F5 las Macs | No frenarse esperando equipos |
| 20 guardrails duplicados | **8** | Los que cubren un modo de falla caro (D20) |
| 12 estados de mensaje | **6 + un campo `motivo`** | Lo demás eran matices |
| "El código de envío no existe hasta el sprint 4" | **Lista de destinos permitidos** | Misma garantía, sin impedir explorar (D21) |
| Ventana de veto: la inacción envía | **Enviar es un segundo botón** | La inacción no manda nada (D4) |
| Auth.js con magic links | **Una contraseña** | Entran una o dos personas (D22) |
| Cron 08:00 y envío 13:00 | **Cuando el dueño aprieta el botón** | Es como lo va a usar |
| Retener chats de más de 60 días | Se sacó esa señal del triage | Contradecía el criterio validado del MVP |

Lo viejo está en [`_historico/`](_historico/). No se borró: si alguna vez hay que entender por qué
algo estaba escrito de otra forma, está ahí. **No se lee como documentación vigente.**
