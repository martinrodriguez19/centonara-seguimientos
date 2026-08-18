# Sprint 6 — Guardrails y endurecimiento

**Duración:** 2 semanas · **Puede enviar:** sí, controlado

---

## Objetivo

Que el sistema resista el uso real. Al terminar, existe una batería de tests que intenta violar
cada regla y falla en todas.

**Este es el sprint que se saltea cuando hay apuro. No se saltea.** Es el que evita que el
proyecto termine mal.

---

## Tareas

### T6.1 — Los 20 guardrails ⚠
Todos los de `05` §2, en backend y agente donde corresponda.
**Terminado cuando:** los 20 están implementados y cada uno tiene su test.

### T6.2 — `test_guardrails.py` ⚠ BLOQUEANTE
Un test por guardrail que **intenta violarlo** y verifica que falla. No alcanza con probar el
camino feliz.
**Terminado cuando:** cobertura 100% de `core/guardrails.py` y `core/estados.py`.

### T6.3 — Anti-duplicados
7 días por contacto, aunque aparezca en corridas distintas y con nombres distintos.
**Terminado cuando:** un test crea el mismo contacto con dos nombres y verifica que sólo recibe uno.

### T6.4 — Topes
Por corrida (25), por máquina por día (20), global (160).
**Terminado cuando:** un test intenta encolar 30 y verifica que se cortó en 25.

### T6.5 — Ventana horaria y jitter
09:00–19:00 hábiles. Pausa aleatoria 45–180 s, **nunca fija**.
**Terminado cuando:** un test verifica que 20 envíos tienen 20 intervalos distintos.
**Por qué:** los patrones regulares son lo que dispara bloqueos.

### T6.6 — Orden aleatorizado
La lista no se recorre siempre igual.
**Terminado cuando:** dos corridas con los mismos contactos producen órdenes distintos.

### T6.7 — Presupuesto por corrida
Si el costo supera el umbral, frena y avisa.
**Terminado cuando:** una corrida simulada cara se frena sola.

### T6.8 — Exclusiones automáticas
Un contacto que responde con señales de molestia entra en `contactos_bloqueados` y se alerta.
**Terminado cuando:** funciona y el contacto no vuelve a recibir nada.

### T6.9 — Reintentos
Política por código de motivo: `CHAT_NO_ABRE` reintenta, `CONTACTO_NO_COINCIDE` **nunca**.
**Terminado cuando:** un test verifica que los no reintentables no se reintentan.

### T6.10 — Prueba de caos
Apagar una máquina a mitad de corrida, cortar la red, matar el agente, llenar el disco.
**Terminado cuando:** en ningún escenario se envía dos veces ni se pierde un registro.

### T6.11 — Prueba de carga
160 mensajes simulados en un día con 8 agentes.
**Terminado cuando:** el sistema los procesa sin degradarse y respeta todos los topes.

### T6.12 — Alertas
Fallidos, canario caído, selector roto, máquina offline en horario, presupuesto excedido,
`ENVIADO_SIN_CONFIRMAR`.
**Terminado cuando:** cada una se dispara en una prueba y llega a quien corresponde.

### T6.13 — Observabilidad
Sentry, Uptime Kuma, métricas de `04` §3.5 incluida `tasa_edicion`.
**Terminado cuando:** el panel muestra costo por mensaje y tasa de edición del último mes.

---

## Criterio de salida

- [ ] **Los 20 guardrails con test que intenta violarlos**
- [ ] Cobertura 100% en `guardrails.py` y `estados.py`
- [ ] La prueba de caos no produce duplicados ni pérdidas
- [ ] 160 mensajes simulados procesados correctamente
- [ ] Todas las alertas verificadas
- [ ] `tasa_edicion` visible en el panel

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Se saltea por apuro | Es criterio de salida del roadmap. No se negocia |
| Los tests prueban el camino feliz | Cada test **intenta violar** el guardrail. Se revisa en el PR |
| Se descubre un problema de diseño tarde | Mejor acá que en producción con 8 vendedores |
