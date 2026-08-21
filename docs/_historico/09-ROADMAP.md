# 09 — Roadmap

**14 semanas, 8 sprints.** Cada sprint tiene un criterio de salida verificable. No se pasa al
siguiente sin cumplirlo.

---

## 1. Panorama

| Sprint | Nombre | Sem | Entregable verificable | ¿Puede enviar? |
|---|---|---|---|---|
| 0 | Fundaciones | 1 | Infraestructura y entornos andando | **No — imposible** |
| 1 | Backend core + agente | 2 | Las 8 máquinas online en el panel | **No — imposible** |
| 2 | Generación | 1 | Borradores en base, paridad con el MVP | **No — imposible** |
| 3 | Panel y sala de salida | 2 | El cliente ve, edita y frena desde el navegador | **No — imposible** |
| 4 | Envío en modo prueba | 2 | Verificación de contacto al 100%, nada sale | No (por código) |
| 5 | Envío real — piloto | 1 | 3 mensajes reales correctos | **Sí, 3** |
| 6 | Guardrails y triage | 2 | Batería de tests que intenta romper todo | Sí, controlado |
| 7 | Observabilidad y rollout | 3 | 8 vendedores en producción | Sí |

```
S0 ──▶ S1 ──▶ S2 ──▶ S3 ──┐
        │                  ├──▶ S4 ──▶ S5 ──▶ S6 ──▶ S7
        └──────────────────┘
                    ▲
              PUNTO DE NO RETORNO
```

**El Sprint 4 es el punto de no retorno.** De 0 a 3 no existe la posibilidad técnica de que salga
un mensaje: el código de envío no está en el repositorio (regla R7). Vale la pena conservar esa
propiedad todo lo que se pueda.

---

## 2. Dependencias externas — conseguir en el Sprint 0

Estas no dependen del equipo y tienen plazo de entrega. **Si no arrancan en la semana 1, bloquean
sprints posteriores.**

| # | Qué | Bloquea | Responsable |
|---|---|---|---|
| E1 | Render, MongoDB Atlas y dominio en Cloudflare | S0 | Tech lead |
| E2 | **8 asientos de plan Anthropic** (D2) | S2 | Cliente |
| E3 | **Máquina Windows 11 de pruebas dedicada** | S4 | Cliente |
| E4 | **Línea de WhatsApp de pruebas** (que no sea de nadie del equipo ni de un vendedor) | S4 | Cliente |
| E5 | 3 contactos propios que acepten recibir mensajes de prueba | S5 | Cliente |
| E6 | **Consentimiento firmado de los 8 vendedores** (R6) | S7 | Cliente |
| E7 | Cuenta de correo saliente para magic links | S1 | Tech lead |
| E8 | Acuerdo escrito de riesgo de bloqueo de líneas | S5 | Cliente |

**E3, E4 y E6 son las críticas.** E6 en particular puede tardar más que cualquier sprint técnico:
hay que hablar con 8 personas y explicarles que el sistema va a mandar mensajes en su nombre.
Empezar en la semana 1, en paralelo a todo.

---

## 3. Criterios de salida

| Sprint | No se cierra hasta que… |
|---|---|
| 0 | `docker compose up` levanta todo, CI verde, rollback probado |
| 1 | Las 8 máquinas simuladas aparecen online y toman jobs. `test_contactos.py` al 100% |
| 2 | Una corrida genera borradores de las 8 máquinas, con la misma calidad que el MVP |
| 3 | El cliente usa el panel sin ayuda y entiende qué está viendo |
| 4 | 50 verificaciones de contacto seguidas, 0 falsos positivos, 0 mensajes escritos por error |
| 5 | 3 mensajes reales llegaron al contacto correcto, confirmados y registrados |
| 6 | Todo `test_guardrails.py` verde, cobertura 100% en guardrails y estados |
| 7 | 8 vendedores operando 5 días seguidos sin intervención técnica |

---

## 4. Hitos de decisión

En estos puntos se para y se decide con datos, no con supuestos.

### H1 — Fin del Sprint 2: costo real
Se mide el costo de una corrida completa de generación con el modelo elegido. Si el costo
proyectado a 8 máquinas excede el presupuesto, se revisa el diseño **antes** de construir el
envío.

### H2 — Sprint 4, día 2: conexión al Chrome
Spike para elegir entre CDP sobre el Chrome del vendedor o perfil persistente dedicado
(`07-EL-AGENTE.md` §7). Criterio: cuál sobrevive a que el vendedor cierre el navegador, reinicie
y trabaje 4 horas normalmente.

### H3 — Fin del Sprint 5: ¿seguimos?
Con 3 mensajes reales enviados, el cliente decide si continúa. Es el último punto barato para
frenar el proyecto.

### H4 — Sprint 7, tras el primer vendedor: modo de operación
Con dos semanas de datos reales se decide si se afloja el triage o la ventana de veto. **Antes no
hay datos suficientes para decidirlo.**

---

## 5. Rollout — cómo se activan los 8

Uno por vez. Nunca dos en la misma semana.

| Semana | Vendedores activos | Modo |
|---|---|---|
| 1 | 1 | triage al máximo, ventana 24 h |
| 2 | 1 | observación, sin cambios |
| 3 | 2 | ventana normal (08:00 → 13:00) |
| 4 | 4 | |
| 5 | 8 | |

Antes de activar a cada vendedor: SOP entregado, riesgo explicado, consentimiento registrado,
ícono de bandeja explicado.

**Si aparece cualquier señal de degradación —mensajes que no llegan, quejas, un contacto que
bloquea— se frena el rollout y se investiga.** No se sigue sumando gente con un problema abierto.

---

## 6. Qué queda explícitamente fuera de alcance

| Fuera | Cuándo se revisa |
|---|---|
| WhatsApp Coexistence / Cloud API | Cuando el volumen o el riesgo lo justifiquen. El `ChannelAdapter` deja el camino abierto |
| Responder mensajes entrantes | No está previsto. Sería otro producto |
| Multi-cliente (multi-tenancy) | Si aparece un segundo cliente |
| Integración con CRM | Sprint futuro, vía n8n |
| App móvil | No |
| Que el modelo decida a quién escribirle | **Nunca** (regla R4) |
