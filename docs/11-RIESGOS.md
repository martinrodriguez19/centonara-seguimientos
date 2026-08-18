# 11 — Riesgos

> Ordenados por costo esperado, no por probabilidad.

---

## 1. Escribir en el chat equivocado

**El riesgo más caro del proyecto.** Un mensaje de seguimiento comercial en la conversación
equivocada es un problema inmediato con un cliente real que paga.

| | |
|---|---|
| Probabilidad | Baja, si la verificación está bien hecha |
| Impacto | **Muy alto** — daño reputacional inmediato y concreto |
| Dueño | Equipo técnico |

**Mitigaciones**
- Verificación de identidad por código, no por modelo (D5)
- Comparación E.164 exacta inmediatamente antes de escribir (R2)
- Aborto si el número no se puede resolver
- 50 verificaciones con casos adversos como criterio de salida del Sprint 4
- T5.6: prueba deliberada de identidad incorrecta en real
- Dos revisores para todo PR del camino de envío

**Si pasa**
1. Kill switch inmediato
2. Identificar el alcance en `auditoria` (a quién más pudo pasarle)
3. Avisar al vendedor dueño de la línea **antes** de que el cliente pregunte
4. No reanudar hasta entender la causa raíz

---

## 2. Bloqueo de una línea por WhatsApp

Automatizar WhatsApp Web va contra los Términos de Servicio de Meta. **El riesgo recae sobre las
líneas de los vendedores, no sobre nuestra infraestructura.**

| | |
|---|---|
| Probabilidad | Media a largo plazo |
| Impacto | Alto — un vendedor pierde su WhatsApp de trabajo |
| Dueño | **Cliente** (decisión informada, E8) |

**Lo que dispara bloqueos** no es principalmente el volumen:
- Patrones de tiempo regulares
- Mensajes a contactos sin el número agendado
- Reportes de "bloquear/reportar" del receptor
- Textos idénticos a muchos destinatarios

**No hay umbral seguro publicado.** 15 mensajes automatizados pueden costar un número y 200
manuales no.

**Mitigaciones de diseño**
- Sólo chats existentes, nunca iniciar con desconocidos
- Pausas aleatorias 45–180 s, nunca fijas
- Textos únicos por conversación (se generan por chat)
- Tope conservador: 20 por máquina por día
- Ventana horaria hábil
- Monitoreo de degradación (T7.8)
- Exclusión automática ante respuesta negativa

**Mitigación operativa**
El cliente conoce el riesgo y decidió avanzar. **Tiene que estar por escrito** (E8), incluyendo
qué pasa si una línea se bloquea: quién se hace cargo, si el vendedor pierde sus chats, cómo se
recupera.

**Si pasa**
1. Frenar esa máquina de inmediato
2. **Frenar el rollout completo** — la regla del Sprint 7
3. Investigar qué la diferenciaba de las demás
4. No reactivar hasta entender la causa

---

## 3. El costo excede el presupuesto

| | |
|---|---|
| Probabilidad | Media |
| Impacto | Alto — puede hacer inviable el proyecto |
| Dueño | Tech lead |

El MVP midió con Opus: USD 0.086 una consulta trivial, USD 0.258 abrir una pestaña. Extrapolado a
un envío conducido por modelo (6 a 10 interacciones), daba USD 1–2 por mensaje. A 160 diarios,
inviable.

**Mitigación principal: D5.** Con el envío determinístico, sólo se paga leer y redactar.

**Mitigaciones adicionales**
- `REDACTAR` sin navegador (T2.4)
- Registro de `costo_usd` por job desde el día uno
- Presupuesto por corrida que frena automáticamente (G19)
- **Hito H1 al final del Sprint 2**: se mide antes de construir el envío

---

## 4. Envío masivo por error

Un bug o una configuración mal puesta que envía todo lo que haya en la lista.

**Mitigaciones**
- Topes duros en código, no en prompt ni en n8n (R1)
- Doble verificación: backend y agente (el agente no confía en el backend)
- Canario: 3 mensajes, 10 minutos de espera, freno automático si fallan
- Kill switch efectivo en menos de 10 s
- `ENTORNO=produccion` como única llave del envío real
- El código de envío no existe antes del Sprint 4 (D11)

---

## 5. Los selectores de WhatsApp Web cambian

**Probabilidad: alta.** Es cuestión de cuándo, no de si.

**Mitigaciones**
- Un solo archivo de selectores con fecha de verificación
- **Falla cerrada**: si no encuentra el header, aborta y no escribe
- Smoke test diario a las 07:00, antes de la corrida de las 13:00
- `SELECTOR_ROTO` frena la corrida entera, no sólo ese mensaje

**Si pasa**
El sistema se frena solo y alerta. Se corrige el archivo de selectores, se despliega, se reanuda.
Costo esperado: un día de mensajes.

---

## 6. Un mensaje inapropiado llega a un cliente

El modelo lee mal una conversación y redacta algo que no corresponde: un seguimiento comercial
sobre un reclamo abierto, un dato inventado presentado como compromiso.

**Tasa aceptada por el negocio: ~1 en 100.** A 160 diarios: ~1,6 por día, ~35 por mes.

**Mitigaciones**
- Triage: aparta las señales de riesgo, que es donde se concentran los errores
- Ventana de veto 08:00–13:00
- Revisión posterior para detectar patrones y ajustar el prompt
- Muestreo obligatorio: 2 mensajes al azar por vendedor por semana
- Exclusión automática ante respuesta negativa

**Nota importante.** Los errores **no se distribuyen al azar**: el prompt funciona bien en el chat
típico precisamente porque es típico. El 1 en 100 cae en el caso raro, que suele ser también el
más caro. Por eso el triage no es redundante con la tasa de error.

---

## 7. Un vendedor no sabe que el sistema envía en su nombre

| | |
|---|---|
| Probabilidad | Alta si no se gestiona |
| Impacto | Alto — pérdida de confianza interna |
| Dueño | **Cliente** |

El `SOP-vendedor.md` del MVP dice *"No envía ningún mensaje. Nunca."*

**Mitigaciones**
- SOP reescrito antes de activar (T5.7, T7.5)
- Consentimiento individual registrado (R6, G15)
- El backend **rechaza encolar** sin consentimiento
- Ícono de bandeja con "pausar por hoy"
- Capacitación (T7.6)

**Es la única tarea del roadmap que no depende del equipo técnico y la que más puede tardar.**
Empezar en la semana 1.

---

## 8. Dependencia del equipo técnico

Si el cliente no puede operar el sistema solo, el proyecto no terminó.

**Mitigaciones**
- Kill switch accesible a cualquier rol
- Configuración editable desde el panel, sin tocar código
- `SOP-cliente-operacion.md` y `SOP-incidentes.md`
- T7.9 es criterio de salida: el cliente ejecuta una tarea de mantenimiento sin el equipo

---

## 9. Riesgos menores

| Riesgo | Mitigación |
|---|---|
| Máquina apagada a la hora de envío | D3: se descarta, aparece en revisión posterior |
| Sesión de WhatsApp caída | Autodiagnóstico + alerta al vendedor por el ícono |
| El cliente responde y nadie contesta | Alerta al vendedor. El sistema **no** responde (fuera de alcance) |
| Duplicados por reintento | `idempotency_key` único en base |
| Pérdida de datos | Backup diario cifrado + restauración probada en el Sprint 0 |
| Token filtrado | Uno por máquina, rotable individualmente |
| Node menor a 22 | Documentado. Problema #1 del historial del MVP |

---

## 10. Revisión

Este documento se revisa al cierre de cada sprint. Un riesgo que se materializó se mueve a
`10-DECISIONES.md` con lo que se hizo al respecto.
