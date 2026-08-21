# 12 — Orden de ejecución

> El "en qué orden hago las cosas" del proyecto. Complementa a `09-ROADMAP.md`: ese dice **qué**
> se construye en cada sprint, este dice **en qué secuencia** y **qué no puede empezar antes de qué**.

---

## 1. El principio: tres carriles en paralelo

El error más común en un proyecto así es tratarlo como una fila única. No lo es. Hay tres carriles
que avanzan al mismo tiempo y se cruzan en momentos específicos.

```
CARRIL A — TÉCNICO      S0 ─ S1 ─ S2 ─ S3 ─ S4 ─ S5 ─ S6 ─ S7
                              │         │         │         │
CARRIL B — CLIENTE      ══════╪═════════╪═════════╪═════════╪═══
   dependencias, consentimientos, acuerdos escritos, capacitación
                              │         │         │         │
CARRIL C — DOCUMENTACIÓN ═════╪═════════╪═════════╪═════════╪═══
   los .md se actualizan durante los sprints, no al final
```

**El carril B es el que se subestima.** No depende del equipo técnico, tiene plazos que no
controlás, y bloquea sprints. Arranca la semana 1.

---

## 2. Día 0 — antes de escribir una línea

Todo el equipo, en este orden:

| Paso | Qué | Quién | Tiempo |
|---|---|---|---|
| 1 | Leer `01-CONTEXTO` | todos | 20 min |
| 2 | Leer `02-ARQUITECTURA` | todos | 30 min |
| 3 | Leer `05-REGLAS-INVIOLABLES` | **todos, sin excepción** | 25 min |
| 4 | Leer `08-CONVENCIONES` | todos | 15 min |
| 5 | Reunión: preguntas y objeciones | todos | 60 min |
| 6 | Leer el documento del rol propio (`03`, `04`, `07`) | según rol | 25 min |
| 7 | Leer `06-ENTORNO-LOCAL` y montar el entorno | todos | 40 min |

**El paso 5 no se saltea.** Si alguien del equipo no está de acuerdo con una decisión, es mucho más
barato discutirla el día 0 que en el sprint 4. Toda objeción que sobreviva a la discusión se anota
en `10-DECISIONES.md`.

---

## 3. Secuencia semana por semana

| Sem | Sprint | Carril A (técnico) | Carril B (cliente) | Carril C (docs) |
|---|---|---|---|---|
| 1 | S0 | Repo, Docker, esqueletos, CI, Render/Atlas, backups | **Pedir E1–E8 por escrito.** Arrancar conversación con los 8 vendedores | — |
| 2 | S1 | Modelo de datos, E164, estados, cola | Seguimiento de E2 (asientos) y E3 (PC de pruebas) | `03` si el modelo cambia |
| 3 | S1 | Auth, endpoints de agente, polling, kill switch | Idem | `04` si la API cambia |
| 4 | S2 | Migrar prompt, `LISTAR_CHATS`, `REDACTAR`, medir costo | **H1: presentar el costo medido** | `10` con el resultado de H1 |
| 5 | S3 | Triage, ventana de veto, vencimientos | Validar criterios de triage con el cliente | `05` §3 con las palabras del rubro |
| 6 | S3 | Sala de salida, historial, revisión posterior, config | **Demo del panel al cliente** | — |
| 7 | S4 | **Spike H2** (conexión a Chrome), adapter, selectores | E3 y E4 **tienen que estar listas** | `10` con la decisión H2 |
| 8 | S4 | Verificación de contacto, escritura, modo prueba, smoke test | Cerrar E8 (acuerdo de riesgo por escrito) | **`CLAUDE.md` actualizado** |
| 9 | S5 | Envío real: 3 mensajes observados | E5 (3 contactos), consentimiento del vendedor piloto. **H3** | `SOP-vendedor.md` reescrito |
| 10 | S6 | Los 20 guardrails y sus tests | Cerrar los 8 consentimientos (E6) | — |
| 11 | S6 | Caos, carga, alertas, observabilidad | Idem | `11-RIESGOS` revisado |
| 12 | S7 | Instalador, bandeja, autoactualización | **Capacitación al dueño y a los vendedores** | SOPs finales |
| 13 | S7 | **Instalación en las 8 máquinas.** Activar vendedor 1 | Acompañamiento | — |
| 14 | S7 | Activar 2 → 4 → 8, escalonado | Traspaso y monitoreo | Documento de traspaso |

---

## 4. Las computadoras de los vendedores — cuándo y cómo

Confirmado: **la configuración de las 8 máquinas de vendedores va al final, en la semana 13,
cuando todo lo demás está listo y probado.** Es lo correcto: instalar en 8 máquinas de gente que
trabaja, para después tener que volver a tocarlas, es la peor forma de gastar el crédito de
paciencia del equipo comercial.

### La distinción que hay que tener clara

| | Máquina de pruebas | Máquinas de vendedores |
|---|---|---|
| Cuántas | 1 | 8 |
| Cuándo | **Semana 7** (bloquea el Sprint 4) | **Semana 13** |
| De quién | Del equipo, dedicada | De cada vendedor, en uso diario |
| Línea de WhatsApp | De prueba, de nadie | Real, de trabajo |
| Se puede romper | Sí | **No** |

**El Sprint 4 no puede arrancar sin la máquina de pruebas.** No es negociable: el motor de envío
no se puede construir contra un simulador. Pero es *una* máquina, del equipo, con una línea que no
le importa a nadie. Eso hay que conseguirlo en la semana 1 (E3, E4) para tenerlo en la 7.

### La recomendación que difiere un poco de tu plan

Instalar las 8 el mismo día tiene un riesgo concreto: **las 8 máquinas reales no se parecen a la
de pruebas.** Versiones distintas de Chrome, antivirus corporativos, políticas de grupo, Windows
con actualizaciones pendientes, usuarios sin permisos de administrador. Si el instalador falla por
algo de eso, falla 8 veces el mismo día, con 8 vendedores mirando.

Propuesta: **una sola máquina de vendedor real en la semana 9**, la del vendedor piloto del
Sprint 5. Con eso descubrís los problemas de entorno real con una persona y con tiempo, en vez de
con ocho y sin margen. Las otras 7 siguen yendo a la semana 13, como querés.

Si preferís mantener las 8 juntas al final, es viable — pero entonces reservá **dos días** para la
instalación, no uno, y tené el rollback listo.

### El día de instalación, paso a paso

Antes de tocar la primera máquina:

- [ ] Instalador probado en al menos 2 máquinas Windows distintas
- [ ] Los 8 tokens generados y anotados, uno por máquina
- [ ] `SOP-instalacion.md` verificado por alguien que no lo escribió
- [ ] Los 8 consentimientos registrados (sin esto el backend no encola: G15)
- [ ] Kill switch probado y el dueño sabe usarlo
- [ ] Todos los vendedores capacitados **antes**, no ese día

Por máquina (objetivo: 10 minutos):

1. Ejecutar el instalador
2. Pegar el token
3. Escanear el QR de WhatsApp Web
4. Verificar que el ícono de bandeja está en verde
5. Verificar que la máquina aparece online en el panel
6. Correr un job de diagnóstico desde el panel
7. Mostrarle al vendedor el ícono y el "pausar por hoy"
8. **Dejar la máquina pausada.** Se activa después, escalonadamente

El paso 8 es importante: instalar no es activar. Se instalan las 8 y se van activando de a una
según el calendario de rollout.

---

## 5. Orden dentro de cada sprint técnico

Regla general: **primero lo que otros necesitan, después lo que sólo usás vos.**

| Sprint | Primero | Después | Al final |
|---|---|---|---|
| S0 | Repo y estructura | Docker, esqueletos | CI, Render/Atlas, backups |
| S1 | Modelo de datos, E164 | Estados, cola, auth | Endpoints, agente, panel de salud |
| S2 | Migrar el prompt | `LISTAR_CHATS`, `REDACTAR` | Persistencia, medición |
| S3 | Triage, ventana, vencimientos | Sala de salida | Historial, config, E2E |
| S4 | **Spike H2** | Adapter, selectores, **verificación** | Escritura, modo prueba, smoke test |
| S5 | **T5.6 (identidad incorrecta)** | Canario | Los 3 mensajes reales |
| S6 | Guardrails y tests | Caos y carga | Alertas, observabilidad |
| S7 | Instalador, bandeja | SOPs, capacitación | Instalación y rollout |

Dos inversiones de orden que parecen raras y son a propósito:

- **En el S4, el spike va primero.** Elegir cómo se conecta al Chrome cambia cómo se escribe todo
  lo demás. Hacerlo después significa reescribir.
- **En el S5, la prueba de identidad incorrecta va ANTES de mandar los 3 mensajes reales.** Probás
  que el sistema aborta cuando debe, y recién entonces lo dejás enviar de verdad.

---

## 6. Los documentos son vivos

No se escriben una vez. Estos cambian durante el proyecto:

| Documento | Cuándo se toca | Quién |
|---|---|---|
| `03-MODELO-DE-DATOS` | Cada cambio de esquema | Backend |
| `04-CONTRATOS-API` | **Antes** de cambiar un endpoint | Quien lo cambia |
| `05-REGLAS-INVIOLABLES` | Casi nunca. Un cambio acá es un evento | Tech lead |
| `10-DECISIONES` | Cada decisión, **antes** de implementarla | Quien decide |
| `11-RIESGOS` | Al cierre de cada sprint | Tech lead |
| `CLAUDE.md` | Sprint 4, cuando el sistema pasa a enviar | Dueño de la máquina |
| SOPs | Sprints 5 y 7 | QA / soporte |

`04-CONTRATOS-API` es la fuente de verdad: si el código se desvía, el que está mal es el código.

---

## 7. Los cuatro puntos donde se para

| Punto | Cuándo | Qué se decide |
|---|---|---|
| **H1** | Fin S2, semana 4 | El costo medido, ¿entra en el presupuesto? Si no, se rediseña antes de construir el envío |
| **H2** | S4 día 2, semana 7 | CDP sobre el Chrome del vendedor vs perfil dedicado |
| **H3** | Fin S5, semana 9 | Con 3 mensajes reales enviados, ¿el cliente sigue? **Último punto barato para frenar** |
| **H4** | S7, tras 2 semanas del piloto | ¿Se afloja el triage o la ventana de veto? Con datos, no con supuestos |

---

## 8. Qué bloquea a qué — la lista corta

Si sólo te acordás de cinco cosas de este documento, que sean estas:

1. **La máquina Windows de pruebas y la línea de WhatsApp de prueba bloquean el Sprint 4.**
   Se piden la semana 1, se necesitan la semana 7.
2. **Los 8 consentimientos bloquean el rollout.** Son 8 conversaciones con personas. Empiezan la
   semana 1. El backend rechaza encolar sin ellos (G15).
3. **H1 bloquea el Sprint 4.** No se construye el envío sin saber cuánto cuesta.
4. **El Sprint 6 bloquea el rollout.** Es el que se saltea cuando hay apuro; no se saltea.
5. **Instalar no es activar.** Las 8 se instalan juntas y se activan de a una.

---

## 9. Cronograma: qué comunicar

**14 semanas** es el plan. **18 semanas** es el rango realista que conviene comunicar.

La diferencia está casi toda en el Sprint 4: es el único que depende de cómo se comporte un
sistema que no controlamos (WhatsApp Web) y de una decisión de spike que puede salir para
cualquier lado. Los demás sprints son razonablemente predecibles.

Prometer 14 y entregar 18 es peor que prometer 18 y entregar 15.
