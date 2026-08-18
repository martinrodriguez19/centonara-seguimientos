# Documentación del proyecto — Sistema de seguimiento comercial v2

**Para quien llega nuevo: leé el `01` y el `02`. Con eso ya podés participar de una reunión.
Antes de escribir código, leé también el `05` y el `08`.**

---

## Mapa de la documentación

### Para entender el proyecto

| Documento | Qué contiene | Leer si… |
|---|---|---|
| `01-CONTEXTO.md` | Qué hace el sistema, para quién, por qué existe. Glosario. | siempre, primero |
| `02-ARQUITECTURA.md` | Cómo está construido y por qué así | siempre, segundo |
| `10-DECISIONES.md` | Las decisiones tomadas y las alternativas descartadas | cuando algo te parezca raro |

### Para construir

| Documento | Qué contiene | Leer si… |
|---|---|---|
| `03-MODELO-DE-DATOS.md` | Colecciones de MongoDB, estados, índices | tocás datos |
| `04-CONTRATOS-API.md` | Endpoints, payloads, códigos de error | tocás backend, front o agente |
| `05-REGLAS-INVIOLABLES.md` | Los límites que el sistema no puede cruzar | **antes de escribir la primera línea** |
| `06-ENTORNO-LOCAL.md` | Cómo levantar todo en tu máquina | tu primer día |
| `07-EL-AGENTE.md` | El componente que corre en la PC del vendedor | trabajás en el agente |
| `08-CONVENCIONES.md` | Git, código, tests, definición de terminado | siempre, antes del primer PR |

### Calendario

| Sprint | Nombre | Semanas |
|---|---|---|
| 0 | Fundaciones | 1 |
| 1 | Backend core y agente v2 | 2 |
| 2 | Generación | 1 |
| 3 | Panel y sala de salida | 2 |
| 4 | Envío en modo prueba ⚠ punto de no retorno | 2 |
| 5 | Envío real — piloto | 1 |
| 6 | Guardrails y endurecimiento | 2 |
| 7 | Rollout | 3 |
| | **Total** | **14** |

### Para planificar

| Documento | Qué contiene |
|---|---|
| `09-ROADMAP.md` | Los 8 sprints, dependencias, criterios de salida |
| `sprints/SPRINT-0..7.md` | Detalle de cada sprint con tickets y criterios de aceptación |
| `11-RIESGOS.md` | Qué puede salir mal y qué hacemos al respecto |
| `12-ORDEN-DE-EJECUCION.md` | **En qué orden hacer todo.** Qué bloquea a qué, y cuándo se tocan las máquinas de los vendedores |
| `13-QUE-HACER-CON-EL-MVP.md` | Qué se migra del MVP, qué se lee como referencia y qué se descarta |

---

## Lo mínimo que hay que entender antes de tocar nada

Cuatro frases:

1. El sistema lee conversaciones de WhatsApp de clientes, redacta mensajes de seguimiento con un
   modelo de lenguaje, y los **envía automáticamente**.
2. Los mensajes salen desde el WhatsApp personal de cada vendedor, en su nombre, desde su
   computadora.
3. Del otro lado hay **personas reales que son clientes reales** del negocio. Un error nuestro es
   un mensaje inapropiado a un cliente que paga.
4. Por eso hay un documento llamado `05-REGLAS-INVIOLABLES.md`. No es una formalidad.

---

## Estado del proyecto

**Existe un MVP funcionando** (Fase 1) que lee chats y redacta borradores, pero **no envía**.
Corre en una sola máquina Windows, con scripts sueltos y disparo manual.

**Vamos a construir la v2 desde cero**, reutilizando el conocimiento del MVP pero no su código
—salvo el prompt de generación, que sí se migra tal cual porque está validado.

El MVP se conserva en `referencia/mvp-fase1/`, **en cuarentena y fuera de la ruta de
construcción**. Qué se copia, qué se lee y qué se descarta está detallado en
`13-QUE-HACER-CON-EL-MVP.md`. Leelo antes de abrir esa carpeta.

---

## Contactos

| Rol | Quién | Para qué |
|---|---|---|
| Product owner / cliente | (completar) | decisiones de negocio, aprobación de fases |
| Tech lead | (completar) | decisiones técnicas, revisión de PRs |
| Backend | (completar) | FastAPI, Mongo, guardrails |
| Frontend | (completar) | Next.js, panel |
| Agente / Windows | (completar) | el ejecutable que corre en la PC del vendedor |

---

## Decisiones cerradas

**No hay decisiones pendientes.** Las tres que quedaban abiertas se resolvieron y están
documentadas. Si alguna se quiere cambiar, se cambia en `10-DECISIONES.md` primero y recién
después en el código.

| # | Decisión | Resolución | Dónde |
|---|---|---|---|
| D1 | Qué se guarda de las conversaciones | Sólo el resumen de una línea, TTL 90 días. El texto enviado se guarda indefinido | `03`, `05` |
| D2 | Cuentas de Anthropic | 8 asientos individuales, uno por máquina | `07`, `11` |
| D3 | PC apagada a la hora de envío | El mensaje vence y se descarta. Aparece al día siguiente en revisión posterior | `03`, `09` |
| D4 | Modelo de control humano | Veto con ventana 08:00→13:00, no aprobación. La inacción envía | `01`, `05` |
| D5 | Motor de envío | Determinístico (Playwright). El LLM sólo lee y redacta | `02`, `07` |
| D6 | Dónde vive el backend | VPS en la nube, agentes con polling saliente | `02`, `06` |
