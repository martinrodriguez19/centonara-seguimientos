# 05 — Fases

> **No hay fechas.** Una fase termina cuando se cumple su criterio de salida, no cuando se acaba
> una semana.
>
> **El orden es por dependencia de hardware, no por riesgo.** Todo lo que se puede construir desde
> una máquina cualquiera va primero. Lo que necesita una Mac queda al final, junto.

---

## 1. Panorama

```
F1  NÚCLEO         datos, estados, cola, endpoints, kill switch
      │
F2  PANEL          login, máquinas, el botón, revisión de borradores
      │
F3  GENERACIÓN     LISTAR, REDACTAR, triage, persistencia, costo
      │
F4  ENVÍO          selectores, verificación de identidad, modo prueba, piloto real
      │                                                          🚪 PUERTA
F5  macOS Y ALTA   launchd, permisos, barra de menú, instalador, rollout
```

**F1 a F4 se hacen desde Windows.** El MVP se validó en Windows 11, así que `claude -p --chrome`,
la extensión y WhatsApp Web funcionan ahí. Y Playwright contra una página web es el mismo
Playwright en todos lados: los selectores que se escriban en F4 valen igual para la Mac.

**F5 es todo lo que necesita una Mac**, y es plomería: cómo arranca el programa, qué permisos pide
el sistema, cómo se instala. Nada de eso cambia lo que el producto hace.

### La única puerta

Al final de F4, con tres mensajes reales enviados, el cliente decide si sigue. Antes de eso no hay
nada que decidir con datos.

### Lo que se sabe y lo que no

**El MVP ya demostró que Claude puede leer WhatsApp Web y redactar borradores utilizables.** Eso no
se vuelve a probar: se vuelve a construir, en F3, y si algo se rompió en el camino se ve ahí mismo.

Lo que sigue sin estar probado es **si Playwright puede escribir y enviar de forma confiable**. Se
sabe en F4. Construir F1 a F3 antes de esa respuesta es una apuesta consciente, y es una apuesta
chica: la cola, el panel, los guardrails y el registro hacen falta igual, incluso si algún día
hubiera que cambiar el canal de envío.

---

## 2. F1 — Núcleo

**Termina cuando:** se da de alta una máquina, un agente simulado la toma, aparece online, y el
kill switch la frena en menos de 10 segundos.

Todo esto es Python y MongoDB. No toca el navegador ni el sistema operativo.

| # | Tarea | Terminada cuando |
|---|---|---|
| F1.1 | Bajar Render de 8 servicios a 3 y limpiar los workflows | `render.yaml` tiene backend, panel y backup. Sin staging, sin n8n |
| F1.2 | Normalización a E.164 (`core/contactos.py`) | 100% de cobertura y pasan todos los formatos argentinos |
| F1.3 | Las seis colecciones e índices, en un script idempotente | Correrlo dos veces no rompe nada |
| F1.4 | Máquina de estados (`core/estados.py`) | Existe un test por cada transición inválida |
| F1.5 | Cola sobre MongoDB, atómica, con `disponible_desde` | Varios consumidores concurrentes: ningún job se entrega dos veces |
| F1.6 | Alta, baja y token por máquina | El token se muestra una vez; revocarlo devuelve 401 en la petición siguiente |
| F1.7 | Los cuatro endpoints del agente | Un agente real consulta, toma un `DIAGNOSTICO` y lo reporta |
| F1.8 | Agente: bucle de consulta, latido, reintentos con backoff | Se corta la red 5 minutos, vuelve, y sigue **sin reiniciar** |
| F1.9 | Agente: los nueve chequeos de diagnóstico | En Windows los que no aplican reportan `n/a`, no fallan |
| F1.10 | Kill switch | Menos de 10 segundos hasta que un agente deja de recibir trabajo |
| F1.11 | Auditoría de sólo inserción | Un `update` falla **a nivel de base de datos**, no por convención |

---

## 3. F2 — Panel

**Termina cuando:** alguien que no es del equipo entra, entiende qué está viendo, da de alta una
máquina y dispara una corrida sin ayuda.

| # | Tarea | Terminada cuando |
|---|---|---|
| F2.1 | Login con contraseña única y cookie de sesión | Sin cookie, todo devuelve 401 |
| F2.2 | Pantalla de estado: máquinas, diagnóstico, contador del día | Muestra **qué chequeo** falló, no "error" |
| F2.3 | Alta y baja de máquinas | La cantidad es variable; nada en el código asume un número fijo |
| F2.4 | El botón: dispara una corrida, con progreso | Devuelve al instante y encola |
| F2.5 | Kill switch visible sin scroll en todas las pantallas | Una sola confirmación, no tres |
| F2.6 | Modo prueba visualmente inconfundible | Alguien mira dos segundos y sabe en qué modo está |
| F2.7 | Configuración editable: topes, palabras, destinos permitidos | El cliente cambia un tope sin tocar código |

El panel se construye contra datos de prueba: en esta fase todavía no hay borradores de verdad.

---

## 4. F3 — Generación

**Termina cuando:** una corrida real genera borradores y el dueño los revisa en el panel.

Acá aparece el navegador. **Funciona en Windows**: es lo que hacía el MVP.

| # | Tarea | Terminada cuando |
|---|---|---|
| F3.1 | Job `LISTAR` con la invocación validada del MVP | Devuelve N chats con resumen; una salida rota se reporta con el `raw` completo |
| F3.2 | Job `REDACTAR`, sin navegador | Redactar 20 borradores no abre ninguna pestaña |
| F3.3 | Variables acotadas con Pydantic | Un intento de inyectar texto de prompt lo rechaza el esquema |
| F3.4 | Persistir chats y borradores | Revisión manual: no queda texto del cliente más allá del resumen de una línea |
| F3.5 | Triage con las cinco señales, palabras en `configuracion` | Sobre borradores reales retiene 10–20%, y un humano está de acuerdo |
| F3.6 | Panel: ver, editar, vetar y liberar borradores | El dueño revisa una corrida entera sin ayuda |
| F3.7 | Editar revalida todo | Un humano que escribe `{nombre}` a mano recibe el mismo rechazo que el modelo |
| F3.8 | Registrar `costo_usd` por job y por corrida | El panel muestra el costo de la corrida |

> **Sobre el costo.** No hace falta medirlo antes: F3.8 lo registra solo. El número importa antes
> de encender las 5 máquinas todos los días, no antes de escribir código. Si sale muy alto, lo que
> se ajusta es `n_chats` y la frecuencia, no la arquitectura.

Los prompts ya están escritos, en `agente/prompts/`. Se migraron del MVP sin cambios funcionales.

---

## 5. F4 — Envío

**Termina cuando:** salieron tres mensajes reales, al contacto correcto, con alguien mirando.

Playwright contra WhatsApp Web. **Todo esto se desarrolla en Windows** y el código sirve igual en
la Mac: los selectores son de una página web, no de un sistema operativo.

El orden de esta fase no es negociable: **la prueba de que el sistema aborta va antes del primer
envío real.**

| # | Tarea | Terminada cuando |
|---|---|---|
| F4.1 | Lista de destinos permitidos, verificada en backend y agente | Un número fuera de la lista devuelve `DESTINO_NO_PERMITIDO` en los dos lados |
| F4.2 | Decidir la conexión al Chrome: CDP vs perfil dedicado | Hay evidencia de cuál sobrevive a media jornada de uso normal |
| F4.3 | Archivo único de selectores, con fecha de verificación | Ningún selector aparece fuera de ahí |
| F4.4 | **Verificación de identidad del contacto** | Los cinco casos adversos abortan correctamente |
| F4.5 | Escritura del texto exacto | Byte a byte idéntico al recibido, con acentos y saltos de línea |
| F4.6 | Modo prueba: hace todo menos apretar enviar | Informe legible de qué habría hecho, contacto por contacto |
| F4.7 | Confirmación en el hilo | Sin confirmación → `SIN_CONFIRMAR` + alerta |
| F4.8 | Códigos de motivo y reintentos por código | `CONTACTO_NO_COINCIDE` **nunca** reintenta |
| F4.9 | Chequeo de selectores antes de cada corrida | Si el DOM cambió, la corrida no arranca |
| F4.10 | `CLAUDE.md` del agente, describiendo que el sistema **envía** | Ver la advertencia de abajo |
| F4.11 | Canario y jitter en la cola | 20 envíos producen 20 intervalos distintos |
| F4.12 | 50 verificaciones de identidad seguidas | 0 falsos positivos, 0 mensajes escritos por error |
| F4.13 | **Prueba de identidad incorrecta** — antes de F4.14 | El sistema aborta y el campo de escritura queda vacío, verificado en el DOM |
| F4.14 | Los tres mensajes reales, uno por vez | Llegaron al contacto correcto y están en `auditoria` |
| F4.15 | Los ocho guardrails, con un test que intenta violar cada uno | 100% de cobertura en guardrails y estados |
| F4.16 | Escenarios de caos | Nunca se envía dos veces ni se pierde un registro |

> ⚠️ **Sobre F4.10.** En el MVP el modelo se negaba a ejecutar por falta de contexto verificable. El
> primer intento de arreglarlo fue agregar al prompt *"esto está autorizado, no preguntes"*, y
> **empeoró el problema**: es el patrón exacto de una inyección. La solución fue poner el contexto
> real en un `CLAUDE.md` escrito por el dueño de la máquina, fuera del pedido. Nada de frases de
> autorización, descripción honesta. Ya está escrito en `agente/prompts/CLAUDE.md`; en esta fase se
> revisa contra lo que el sistema realmente hace.

**Para F4.14 hace falta:** una línea de WhatsApp que no sea de nadie del equipo, tres contactos que
acepten recibir los mensajes, y el acuerdo escrito con el cliente sobre el riesgo de bloqueo de
líneas. Todo lo anterior de la fase se hace sin nada de eso, en modo prueba.

### 🚪 Puerta

Con tres mensajes reales enviados, el cliente decide si sigue. Se le presenta: los mensajes tal
como los recibió el destinatario, el costo medido por mensaje, el estado de los riesgos, y qué
falta para que lo use el equipo.

La presentación tiene que permitirle decir que no. Si sólo permite decir que sí, está mal armada.

---

## 6. F5 — macOS y alta de máquinas

**Termina cuando:** las máquinas operan varios días seguidos sin intervención técnica.

**Esta es la única fase que necesita Macs.** Es plomería: nada de lo que hay acá cambia lo que el
producto hace, y por eso está al final.

| # | Tarea | Terminada cuando |
|---|---|---|
| F5.1 | Portar el agente a macOS y documentar los permisos que pide | Está la lista, y el diagnóstico los verifica |
| F5.2 | LaunchAgent en `~/Library/LaunchAgents/` | Se reinicia la Mac, se loguea, y el agente ya corre |
| F5.3 | Instalador de tres pasos | Alguien que no lo escribió instala una Mac siguiéndolo |
| F5.4 | Ícono en la barra de menú con "pausar por hoy" | Un vendedor pausa su máquina sin ayuda |
| F5.5 | Asientos de Claude asignados y extensión habilitada por política | Ver D2 — es una llamada al administrador del Enterprise |
| F5.6 | SOPs, y **retirar de circulación el SOP viejo** | Ver abajo |
| F5.7 | Una conversación de consentimiento por vendedor, registrada | `acepto_condiciones_en` cargado para cada máquina activa |
| F5.8 | Alta escalonada: una máquina, después dos, después el resto | Ninguna señal de degradación en el camino |

> ⚠️ **Sobre F5.6.** El SOP viejo dice textual *"No envía ningún mensaje. Nunca."*. No alcanza con
> escribir el nuevo: hay que **sacar el viejo de circulación** — Drive, mails, impresos, grupos. Es
> el paso que se olvida.

**F5.5 conviene empezarlo antes**, aunque la fase esté al final. Si la política de la organización
tiene restringida la extensión Claude in Chrome, el sistema no funciona en ninguna máquina, y eso
no se arregla desde el código. Es una llamada, no una tarea técnica.

### Instalar no es activar

Las máquinas se dan de alta de a una, y se instalan pausadas. Si aparece cualquier señal de
degradación —mensajes que no llegan, una queja, un contacto que bloquea— **se frena el alta de
máquinas nuevas y se investiga**. Es la regla que evita perder cinco líneas en vez de una.

---

## 7. Criterio de salida del proyecto

- Las máquinas operan varios días seguidos sin intervención técnica
- Ninguna línea bloqueada
- Ningún mensaje al contacto equivocado
- Costo mensual dentro del presupuesto
- El dueño explica el sistema en una frase y sabe cómo frenarlo
