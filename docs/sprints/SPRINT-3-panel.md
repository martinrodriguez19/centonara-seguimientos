# Sprint 3 — Panel y sala de salida

**Duración:** 2 semanas · **Puede enviar:** no (R7)

---

## Objetivo

Que el cliente entre a un link, vea lo que se va a enviar, y pueda editarlo o frenarlo. Es el
sprint que convierte un script en un producto.

Al terminar, todo el flujo funciona salvo el último paso: apretar enviar.

---

## Tareas

### T3.1 — Triage
`core/triage.py` con las 7 señales de `05` §3. Listas de palabras en `configuracion`, no
hardcodeadas.
**Terminado cuando:** sobre 50 borradores reales, retiene entre el 10% y el 20% y un humano está
de acuerdo con lo que retuvo.

### T3.2 — Ventana de veto
Al validar, el mensaje pasa a `EN_ESPERA` con `sale_a_las`. Un scheduler mueve a `ENCOLADO` los
vencidos. `ventana_veto_minutos: 0` equivale a full auto.
**Terminado cuando:** con la ventana en 0, el mensaje pasa directo; con 300, espera.

### T3.3 — Vencimientos
Scheduler que marca `VENCIDO` los `RETENIDO` sin resolver y los mensajes de más de 24 h.
**Terminado cuando:** un retenido que nadie mira termina en `VENCIDO`, no en `ENCOLADO`.
**Por qué:** liberarlos por defecto invertiría el sentido del triage.

### T3.4 — Sala de salida
La pantalla principal. Retenidos arriba, en espera abajo con cuenta regresiva visible
("sale en 47 min"). Edición en línea. Vetar individual y por lote.
**Terminado cuando:** el cliente la usa sin ayuda y entiende qué está viendo.

### T3.5 — Edición con revalidación
Editar recalcula `idempotency_key` y vuelve a pasar los guardrails.
**Terminado cuando:** si el humano escribe `{nombre}` al editar, se rechaza igual.
**Por qué:** un humano también puede empeorar un mensaje.

### T3.6 — Panel principal
Estado de las 8 máquinas, botón de corrida con barra de progreso, contador del día, kill switch
visible en todas las pantallas.
**Terminado cuando:** el kill switch se ve sin hacer scroll en cualquier pantalla.

### T3.7 — Modo prueba visualmente inconfundible
Banda de color en toda la aplicación cuando el modo no es real.
**Terminado cuando:** es imposible confundirse. Alguien mira la pantalla 2 segundos y sabe en qué
modo está.

### T3.8 — Fricción proporcional
Vetar 3 mensajes es un click. Liberar 20 retenidos pide escribir la cantidad.
**Terminado cuando:** las acciones masivas piden confirmación explícita.

### T3.9 — Historial
Qué salió, a quién, cuándo, en qué modo, quién lo editó o vetó. Con buscador por contacto.
**Terminado cuando:** buscando un número, aparece todo lo que se le mandó.
**Por qué:** es la pantalla que se abre cuando un cliente se queja.

### T3.10 — Revisión posterior
Lo de ayer, con la señal de triage de cada uno. Marcar "salió mal" con categoría.
**Terminado cuando:** se puede marcar un problema y queda registrado para ajustar el prompt.

### T3.11 — Configuración
Topes, ventana, señales de triage, exclusiones. Cada cambio auditado.
**Terminado cuando:** cambiar `ventana_veto_minutos` deja registro de quién y cuándo.

### T3.12 — Notificaciones en n8n
"Hay 18 mensajes para salir a las 13:00. 3 requieren tu decisión." Con link directo.
**Terminado cuando:** el mail llega y el link abre la sala de salida filtrada.

### T3.13 — Tests E2E
Playwright sobre los flujos críticos: entrar, ver, editar, vetar, liberar, kill switch.
**Terminado cuando:** corren en CI.

---

## Criterio de salida

- [ ] **El cliente usa el panel sin ayuda y explica qué está viendo**
- [ ] El triage retiene entre 10% y 20% y el criterio le parece razonable
- [ ] Un retenido que nadie mira termina en `VENCIDO`
- [ ] Editar revalida los guardrails
- [ ] El kill switch está visible en todas las pantallas
- [ ] E2E en verde

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El triage retiene demasiado y molesta | Ajustar señales con datos reales, no con supuestos |
| El cliente no entiende la diferencia entre veto y aprobación | Que la cuenta regresiva sea explícita: "sale en 47 min salvo que lo frenes" |
| Se construye una pantalla que nadie usa | Demo con el cliente a mitad de sprint, no al final |
