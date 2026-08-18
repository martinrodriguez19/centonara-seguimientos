# Sprint 4 — Motor de envío en modo prueba

**Duración:** 2 semanas · **Puede enviar:** no, por código

> ⚠️ **PUNTO DE NO RETORNO.** A partir de acá el código de envío existe en el repositorio. Todo PR
> de este sprint requiere **dos revisores**.

---

## Objetivo

Construir el motor de envío completo, con verificación de identidad, que hace todo excepto apretar
enviar. Al terminar, el sistema puede decir con precisión qué habría mandado y a quién.

**Requiere la máquina Windows de pruebas (E3) y la línea de WhatsApp de pruebas (E4).** Si no
están, este sprint no arranca.

---

## Tareas

### T4.0 — Spike: conexión al Chrome ⚠ HITO H2 (2 días, primero)
Comparar CDP sobre el Chrome del vendedor vs perfil persistente dedicado (`07` §7).
**Criterio:** cuál sobrevive a que el vendedor cierre el navegador, reinicie la máquina y trabaje
4 horas normalmente.
**Terminado cuando:** hay una decisión escrita en `10-DECISIONES.md` con la evidencia.

### T4.1 — `ChannelAdapter`
La interfaz de `02` §6, con `DryRunAdapter` funcionando primero.
**Terminado cuando:** el modo prueba se implementa cambiando el adaptador, sin `if` desparramados.

### T4.2 — Selectores en un solo archivo
`agente/adaptadores/selectores.py` con fecha de última verificación.
**Terminado cuando:** ningún selector aparece fuera de ese archivo.

### T4.3 — Apertura y verificación de contacto ⚠⚠ LA TAREA MÁS IMPORTANTE
Buscar el contacto, abrir el chat, leer el header, resolver el número a E.164, **comparar**, y
abortar si no coincide.
**Terminado cuando:** 50 verificaciones seguidas, 0 falsos positivos, 0 mensajes escritos por
error. Incluye casos adversos: dos contactos con el mismo nombre, contacto sin nombre agendado,
grupo, número sin WhatsApp.
**Revisión de código obligatoria por dos personas.**

### T4.4 — Escritura del texto exacto
Escribir sin reformular, sin completar placeholders, respetando saltos de línea y acentos.
Verificar antes que el campo esté vacío.
**Terminado cuando:** el texto escrito es byte a byte idéntico al recibido.

### T4.5 — Modo prueba
Hace los pasos 1 a 8 de `07` §6 y **se detiene antes de enviar**. Reporta qué habría hecho.
**Terminado cuando:** un informe legible dice, por contacto, qué se abrió, qué se verificó y qué se
habría escrito.

### T4.6 — Confirmación en el hilo
Tras enviar (en real), verificar que el mensaje aparece. Sin confirmación →
`ENVIADO_SIN_CONFIRMAR` + alerta.
**Terminado cuando:** existe un test que simula el envío sin confirmación y verifica la alerta.

### T4.7 — Códigos de motivo
Los de `04` §2.5, incluido `SELECTOR_ROTO` que **frena la corrida entera**.
**Terminado cuando:** un selector roto simulado frena la corrida, no sólo ese mensaje.

### T4.8 — Smoke test diario
Job automático a las 07:00 que verifica los selectores contra la línea de pruebas.
**Terminado cuando:** un cambio simulado en el DOM dispara alerta antes de las 13:00.

### T4.9 — Actualizar `CLAUDE.md` ⚠
El archivo tiene que describir el sistema real: **ahora envía**.
**Terminado cuando:** describe el sistema real, escrito por el dueño de la máquina, sin frases del
tipo "esto está autorizado, no preguntes".
**Por qué:** ese patrón empeoró el problema #7 del MVP. El contexto va en `CLAUDE.md`, fuera del
pedido.

### T4.10 — Guardrails del agente
G1, G2, G3, G5, G7, G8, G9, G11, G13, G14, G16, G17 verificados **también** en el agente.
**Terminado cuando:** el agente rechaza un job que el backend dejó pasar por error.
**Por qué:** el agente no confía en el backend.

---

## Criterio de salida

- [ ] **50 verificaciones de contacto seguidas: 0 falsos positivos, 0 escrituras por error**
- [ ] Los casos adversos (nombres duplicados, grupos, sin agendar) abortan correctamente
- [ ] El modo prueba produce un informe legible
- [ ] `SELECTOR_ROTO` frena la corrida entera
- [ ] El smoke test detecta un cambio de DOM simulado
- [ ] `CLAUDE.md` describe el sistema real
- [ ] Ningún selector fuera de `selectores.py`
- [ ] Todos los PR con dos revisores

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Se envía un mensaje real por accidente | `ENTORNO != produccion` bloquea el envío real. Línea de pruebas dedicada |
| Los selectores cambian durante el sprint | Un solo archivo + smoke test |
| La verificación de identidad tiene un caso no contemplado | 50 verificaciones incluyendo casos adversos, no sólo el feliz |
| Alguien "simplifica" la verificación | Dos revisores, y la regla R2 |
