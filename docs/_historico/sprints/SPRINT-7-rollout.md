# Sprint 7 — Rollout

**Duración:** 3 semanas · **Puede enviar:** sí, en producción

---

## Objetivo

Poner el sistema en manos de los 8 vendedores, de a uno por vez, sin sorpresas.

**Este sprint es más de operaciones que de código.** Si aparece mucho desarrollo nuevo, algo del
Sprint 6 quedó abierto.

---

## Prerrequisitos

- [ ] **E6: consentimiento registrado de los 8 vendedores** (R6). Sin esto, el backend no encola
- [ ] Sprint 6 cerrado
- [ ] SOPs reescritos y entregados

---

## Tareas

### T7.1 — Instalador
PyInstaller + Inno Setup. Instala, crea la tarea programada, escribe `settings.json`, fija el
`deviceId`, corre el autodiagnóstico.
**Terminado cuando:** una instalación completa toma 3 pasos y menos de 10 minutos.
**Por qué:** el SOP del MVP tenía 12 pasos.

### T7.2 — Ícono de bandeja
Estados, última corrida, "pausar por hoy" (`07` §8).
**Terminado cuando:** un vendedor pausa su máquina sin ayuda.

### T7.3 — Autoactualización
Con validación de hash SHA-256.
**Terminado cuando:** se despliega una versión nueva y las 8 se actualizan solas en 24 h.

### T7.4 — Arranque automático
Task Scheduler al iniciar sesión, con reinicio ante fallo.
**Terminado cuando:** se reinicia la máquina, se loguea, y el agente está corriendo sin
intervención.

### T7.5 — SOPs finales
- `SOP-instalacion.md` — 3 pasos
- `SOP-vendedor.md` — reescrito: **el sistema envía**
- `SOP-cliente-operacion.md` — rutina diaria y kill switch
- `SOP-incidentes.md` — qué hacer si algo sale mal

**Terminado cuando:** alguien que no participó del proyecto instala una máquina siguiendo el SOP.

### T7.6 — Capacitación
Sesión con los 8 vendedores: qué hace, qué no hace, cómo pausar, qué hacer si un cliente
pregunta. Y con el dueño: el panel, el kill switch, la sala de salida.
**Terminado cuando:** el dueño explica el sistema en una frase y sabe cómo frenarlo.

### T7.7 — Rollout escalonado
| Semana | Activos | Modo |
|---|---|---|
| 1 | 1 | triage al máximo, ventana 24 h |
| 2 | 1 | observación |
| 3 | 2 | ventana normal |
| 4 | 4 | |
| 5 | 8 | |

**Terminado cuando:** los 8 operan 5 días seguidos sin intervención técnica.

### T7.8 — Monitoreo de degradación
Vigilar señales de bloqueo: mensajes sin doble tilde, quejas, aumento de fallos.
**Terminado cuando:** hay una alerta automática y alguien la mira todos los días.

### T7.9 — Traspaso
Documentar cómo agregar un vendedor, rotar un token, restaurar un backup, interpretar una alerta.
**Terminado cuando:** el cliente ejecuta una de estas tareas sin el equipo.

### T7.10 — Hito H4
Tras dos semanas del primer vendedor, revisar la tasa de veto y decidir si se afloja el triage o
la ventana.
**Terminado cuando:** hay una decisión documentada **basada en datos**, no en supuestos.

---

## Criterio de salida

- [ ] 8 vendedores operando 5 días seguidos sin intervención técnica
- [ ] Ninguna línea bloqueada
- [ ] Ningún mensaje al contacto equivocado
- [ ] Costo mensual dentro del presupuesto
- [ ] El dueño opera el sistema sin el equipo
- [ ] Los 8 consentimientos registrados

## Regla de freno

**Si aparece cualquier señal de degradación —mensajes que no llegan, una queja, un contacto que
bloquea— se frena el rollout y se investiga.** No se sigue sumando vendedores con un problema
abierto. Es la regla que evita perder 8 líneas en vez de una.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Un vendedor no quiere participar | Se respeta. El sistema funciona con menos de 8 |
| Se activan todos juntos por apuro | El escalonamiento es criterio de salida |
| Una línea se bloquea | Regla de freno + `11-RIESGOS.md` §1 |
| El cliente queda dependiendo del equipo | T7.9 es criterio de salida |
