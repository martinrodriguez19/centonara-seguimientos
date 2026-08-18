# Sprint 5 — Envío real, piloto

**Duración:** 1 semana · **Puede enviar:** sí, 3 mensajes, con alguien mirando

> Este es el sprint en que el sistema le escribe a una persona real por primera vez.

---

## Objetivo

Enviar 3 mensajes reales a 3 contactos que aceptaron recibirlos, desde una máquina, con el equipo
observando en vivo. Verificar que llegaron al contacto correcto y quedaron registrados.

**No es un sprint de código. Es un sprint de verificación.** Si hace falta escribir mucho código
nuevo, el Sprint 4 no estaba terminado.

---

## Prerrequisitos — sin esto no arranca

- [ ] E5: 3 contactos propios que aceptaron explícitamente recibir mensajes de prueba
- [ ] E8: acuerdo escrito con el cliente sobre el riesgo de bloqueo de líneas
- [ ] R6: consentimiento registrado del vendedor de la máquina piloto
- [ ] Sprint 4 cerrado con sus 50 verificaciones

---

## Tareas

### T5.1 — Habilitar el envío real
`ENTORNO=produccion` en una sola máquina, con tope de 3 mensajes.
**Terminado cuando:** el tope de 3 está en configuración y verificado con un test.

### T5.2 — Canario
Los primeros 3 mensajes salen, el sistema espera 10 minutos, y recién libera el resto. Si fallan,
frena todo.
**Terminado cuando:** un fallo simulado del canario frena la corrida automáticamente.
**Nota:** en este sprint los 3 mensajes *son* el canario.

### T5.3 — Envío observado
Los 3 mensajes, con el equipo mirando la pantalla en vivo.
**Terminado cuando:** los 3 llegaron al contacto correcto y los 3 destinatarios lo confirmaron por
otro medio.

### T5.4 — Verificación del registro
Que los 3 estén en `mensajes` y en `auditoria`, con timestamp, y aparezcan en el historial.
**Terminado cuando:** buscando el número en el historial aparece el mensaje enviado.

### T5.5 — Prueba del kill switch en real
Frenar el sistema con un envío en curso.
**Terminado cuando:** se aprieta durante una corrida real y el mensaje siguiente no sale.

### T5.6 — Prueba de identidad en real
Encolar deliberadamente un mensaje con un `contacto_id` que no corresponde al nombre.
**Terminado cuando:** el sistema aborta, reporta `CONTACTO_NO_COINCIDE` y **no escribe nada**.
**Esta es la prueba más importante del proyecto.**

### T5.7 — SOP del vendedor reescrito
El del MVP dice "No envía ningún mensaje. Nunca." Reescribirlo describiendo el sistema real.
**Terminado cuando:** el vendedor de la máquina piloto lo leyó, lo entendió y lo confirmó.

### T5.8 — Medición de costo real
Costo de una corrida de envío completa, ahora que el envío es determinístico.
**Terminado cuando:** hay un número medido de costo por mensaje enviado.

---

## Criterio de salida

- [ ] 3 mensajes reales llegaron al contacto correcto, confirmados por el destinatario
- [ ] Los 3 están registrados con timestamp y aparecen en el historial
- [ ] **T5.6 pasó: el sistema abortó un envío con identidad incorrecta sin escribir nada**
- [ ] El kill switch funcionó en vivo
- [ ] SOP reescrito y confirmado por el vendedor
- [ ] Costo por mensaje medido

## Hito de decisión H3

Con 3 mensajes reales enviados, **el cliente decide si el proyecto continúa.** Es el último punto
barato para frenar. Presentarle: los 3 mensajes tal como llegaron, el costo medido, y los riesgos
de `11-RIESGOS.md`.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Un mensaje sale a un contacto equivocado | T5.6 se prueba **antes** de T5.3 |
| El destinatario responde y confunde al vendedor | Los 3 contactos saben que es una prueba |
| El equipo se confía porque salió bien | 3 mensajes exitosos no prueban nada sobre 160 diarios. Por eso existe el Sprint 6 |
