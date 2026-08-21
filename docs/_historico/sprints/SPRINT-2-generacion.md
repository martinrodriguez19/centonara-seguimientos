# Sprint 2 — Generación

**Duración:** 1 semana · **Puede enviar:** no (R7)

---

## Objetivo

Migrar la generación del MVP al sistema nuevo, con paridad de calidad. Al terminar, el botón
genera borradores de las 8 máquinas y quedan guardados.

**Esto es lo único que el MVP ya sabía hacer.** No inventamos nada: migramos lo que está validado.

---

## Tareas

### T2.1 — Migrar el prompt
`prompt.txt` del MVP a `agente/prompts/prompt-listar.txt`, **sin cambios funcionales**.
Placeholders `{{DEVICE_ID}}`, `{{N_CHATS}}`, `{{RUN_ID}}`.
**Terminado cuando:** produce el mismo JSON que el MVP sobre los mismos chats.

### T2.2 — Job `LISTAR_CHATS`
Invocación de `claude -p --chrome` con **prompt por stdin** y `encoding="utf-8"` (`07` §5). Parseo
del JSON, manejo de salida malformada.
**Terminado cuando:** una salida inválida se reporta como fallo con el `raw` completo, sin
reventar el agente.

### T2.3 — Principio de variables acotadas
El equivalente de `ALLOWED_VARS` del MVP: sólo viajan variables validadas, nunca texto de prompt
desde el backend.
**Terminado cuando:** un intento de inyectar texto arbitrario en el payload es rechazado por el
esquema Pydantic.

### T2.4 — Job `REDACTAR`
Separado de la lectura. Llamada de texto plano a la API, **sin navegador**. Un job por chat.
**Terminado cuando:** redactar 20 borradores no abre ninguna pestaña.
**Por qué:** es el paso más frecuente y sacarlo del circuito del navegador es donde está el ahorro.

### T2.5 — Persistencia
Chats y borradores en la base, con el resumen de **una línea** (nunca la conversación completa,
D1).
**Terminado cuando:** una revisión manual confirma que no hay texto de cliente más allá del
resumen.

### T2.6 — Endpoint de corrida
`POST /api/corridas` con `tipo: "generacion"`. Devuelve al instante y encola.
**Terminado cuando:** responde en menos de 500 ms con 8 máquinas.

### T2.7 — Cron en n8n
Disparo a las 08:00. **Sólo el horario**: ninguna lógica de negocio en n8n.
**Terminado cuando:** el workflow tiene un solo nodo HTTP y un nodo de notificación.

### T2.8 — Medición de costo ⚠ HITO H1
Registrar `costo_usd` por job y por corrida. Medir una corrida completa real.
**Terminado cuando:** hay un número medido, no estimado, del costo de generar 20 borradores.

---

## Criterio de salida

- [ ] El botón genera borradores de las 8 máquinas
- [ ] La calidad es equivalente a la del MVP (revisión manual de 20 borradores)
- [ ] No se guarda texto de conversación más allá del resumen de una línea
- [ ] `REDACTAR` no usa el navegador
- [ ] **Costo por corrida medido y comparado con el presupuesto**

## Hito de decisión H1

Con el costo real medido, se compara contra el presupuesto proyectado a 8 máquinas. Si excede,
**se para y se revisa el diseño antes de construir el envío**. Es mucho más barato descubrirlo
acá que en el Sprint 6.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El prompt se "mejora" al migrarlo | Migración literal. Las mejoras son otro ticket, después de verificar paridad |
| Los acentos se rompen en Windows | `encoding="utf-8"`. Problema #6 del historial |
| "Tu mensaje se cortó" | Prompt por stdin, nunca como argumento. Problema #6 |
| El costo es más alto de lo esperado | Justamente para eso está H1 |
