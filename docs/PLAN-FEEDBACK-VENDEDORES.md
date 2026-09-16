# Plan — Lo que pidieron los vendedores, la corrida de las 17 y el envío automático

> **Los pedidos.** (1) Mensajes sin signos de apertura: nada de `¿` ni `¡`. (2) Las etiquetas que
> los vendedores empezaron a poner en el nombre del contacto (ARQ, PAISA, PILE, CF, DIST, COLO, XX)
> se usan cuando están, y cuando no están se sigue como hoy. (3) Que la corrida arranque sola todos
> los días a las 17:00, hora argentina. (4) Un switch que haga que el pase único, además de dejar el
> borrador, apriete enviar. Y un problema: (5) las Macs no quedaron al día con el actualizador.
>
> Fecha: 16/09/2026. Base: `main` en `5a6135a`. Estado: **implementado entero el mismo día**
> (sprints 0 a 4; el 5 es a mano). Decisiones D49–D53 en `06-DECISIONES.md`. Las respuestas del
> dueño a las preguntas abiertas están en §6 y aplicadas. Lo que necesita una máquina real está en
> [`PENDIENTE-CON-MAQUINA.md`](PENDIENTE-CON-MAQUINA.md) §F.
>
> **La regla que ordena el plan:** primero las Macs. Los pedidos 1, 2 y 4 viven casi enteros en el
> agente (`agente/prompts/`, `agente/agente/jobs/borradores.py`), y el agente llega a cada máquina
> por el actualizador. Una Mac que no se actualiza sola no va a ver ninguna de estas mejoras, por
> más que el código esté en verde.

---

## 0. Qué hay hoy, verificado en el código

| Pedido | Qué hay hoy | Dónde |
|---|---|---|
| Sin `¿` / `¡` | Ninguna regla. Los ejemplos del prompt ya escriben sin apertura (`La necesitas todavia?`), pero nada lo pide, y la señal de signos **acepta `¿…?` a propósito** | `prompt-borradores.txt:136-141`; `redaccion.py:50-51`; `test_redaccion.py:80` |
| Etiquetas en el nombre | **No existe ningún concepto de tipo de cliente.** Además D29 dice "todos los chats son comerciales", y XX choca de frente con eso | `06-DECISIONES.md:467-490` |
| Corrida a las 17 | **No hay nada programado.** "El sistema no se despierta solo". APScheduler figura en los docs pero nunca entró al proyecto. Lo único periódico es `mantenimiento_periodico`, un loop de asyncio cada 5 min | `corridas.py:3-5`; `main.py:30-57` |
| Envío automático | El pase único **tiene prohibido enviar** en tres lugares: el prompt (l.6-16, 88-93), el `CLAUDE.md` de la máquina (l.25-40, que además dice que ninguna instrucción puede ampliarlo) y R3/D38. El envío real que existe (Playwright, D24) **no sirve** sobre un borrador del pase único: G8 aborta con `CAMPO_NO_VACIO` y `BORRADOR_DEJADO` es terminal | `prompt-borradores.txt`, `prompts/CLAUDE.md`, `estados.py:96-115` |
| Actualización | Actualizador D45–D48: al iniciar sesión y cada hora, pregunta al backend qué sha toca y lo instala. **El backend y el panel no se actualizan solos**: Render tiene `autoDeploy: false` | `actualizar.py`; `render.yaml` |

Dos hallazgos que no se pidieron pero que el pedido 3 vuelve reales:

- **Los topes diarios cortan a medianoche UTC** (`mensajes.enviados_hoy`, `borradores_dejados_hoy`).
  Hasta ahora daba igual: "la ventana termina 19:00, tres horas antes de que UTC cambie de día".
  Una corrida que arranca a las 17:00 (20:00 UTC) y dura 2-3 h **cruza** la medianoche UTC a las
  21:00: el tope de 20 por día se reinicia en el medio de la corrida.
- **La ventana horaria de fábrica es lunes a viernes, 09:00–19:00.** "Todos los días a las 17" deja
  sábado y domingo fuera de la ventana, y una corrida larga sale de la ventana a las 19:00. Para
  borradores no importa (D37); para el envío automático, sí.

---

## 1. Las Macs: por qué no quedaron al día

### La causa más probable

La primera guía de instalación de Mac (commit `146e0e8`) decía **`git clone`**. Una Mac instalada
así tiene `~/centonara-seguimientos/.git`, y el instalador actual, al ver esa carpeta, **no baja
nada**: "ya está clonado con git — se usa como está" (`instalar.sh`, paso 3). A partir de ahí:

1. El paso 6 corre el `instalar-mac.sh` **del árbol viejo**, que no conoce el actualizador: no
   escribe `com.centonara.actualizador.plist` ni copia `actualizar.py` a `~/.centonara/bin/`.
2. El paso 7 intenta correr `~/.centonara/bin/actualizar.py` (no existe; imprime un aviso y sigue)
   y después `launchctl bootstrap …/com.centonara.actualizador.plist` sobre un archivo que no
   existe. Con `set -e`, **el instalador se corta ahí**.
3. Resultado: el agente arranca con el código viejo, sin actualizador, y nada lo va a cambiar.

Encaja con "no se actualizó al 100 %": el instalador arrancó, hizo la mitad y se cortó.

### Otras dos causas que se descartan en un minuto

- **La versión está fijada en el panel.** Configuración → *Versión del agente* con un sha adentro
  hace que todas las máquinas se queden en ese commit (D45). Tiene que estar **vacío**.
- **GitHub no le contesta al backend.** El backend resuelve `main` con la API pública de GitHub sin
  token: 60 consultas por hora por IP, y Render comparte IPs de salida. Si no la resuelve, las
  máquinas "no saben qué versión toca" y no hacen nada. En el log se ve como
  `no se sabe qué versión toca (desconocida)`.

### El diagnóstico, en cada Mac (un solo pegado, no cambia nada)

```bash
echo "--- git:"; ls -d ~/centonara-seguimientos/.git; echo "--- servicios:"; ls ~/Library/LaunchAgents | grep centonara; echo "--- actualizador:"; ls ~/.centonara/bin/; echo "--- version:"; cat ~/centonara-seguimientos/agente/VERSION; echo "--- log:"; tail -15 ~/Library/Logs/centonara/actualizador.log
```

| Lo que dice | Qué es |
|---|---|
| Aparece `.git`, hay 2 servicios y no hay `actualizar.py` | La causa probable de arriba |
| 3 servicios, y el log dice `al día` pero la versión es vieja | Versión fijada en el panel |
| El log dice `desconocida` | GitHub no le contesta al backend |

### El arreglo de hoy, sin esperar código

**No hace falta borrar la carpeta**, y conviene no hacerlo: ahí está el `.env` con el token de la
máquina, y sin él el instalador vuelve a preguntar identificador y token (el token sólo se ve al dar
de alta; si se perdió, se rota en el panel). La sesión de WhatsApp del navegador de envío vive fuera
de la carpeta y tampoco se toca. Alcanza con **apartar el `.git`** y volver a correr el instalador:

```bash
mv ~/centonara-seguimientos/.git ~/centonara-git-viejo; curl -fsSL --http1.1 https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/instalar.sh | bash
```

Sin `.git`, el instalador baja `main`, escribe los tres servicios, corre el actualizador (que además
borra los archivos viejos que ya no existen arriba) y deja `agente/VERSION`. Se verifica con los
comandos de "Verificar que quedó bien" de `COMANDOS-MAQUINAS.md`: **tres** líneas en
`launchctl list | grep centonara`, y el sha en la tarjeta de la máquina del panel.

### El arreglo en el código (Sprint 0)

Que ninguna otra máquina caiga en esto, y que si algo falla, el instalador lo diga en vez de
cortarse a medias.

---

## 2. Decisiones que introduce

- **D49 — Sin signos de apertura.** Regla contable del prompt ("nunca `¿` ni `¡`; sólo el de
  cierre"), señal `SIGNO_DE_APERTURA` en `redaccion.py` (informa, no bloquea), y en los caminos
  donde el texto pasa por código antes de llegar a WhatsApp —el circuito viejo— se quita en
  código.
- **D50 — Las etiquetas del nombre dicen quién es el cliente, y XX es no contactar** *(revisa D29
  en parte)*. Todos los chats siguen siendo comerciales, **salvo los que el vendedor marcó XX**. Las
  etiquetas se reconocen en código (Python, con tests); el significado y la guía de enfoque de cada
  una viven en la configuración, editables desde el panel. Sin etiqueta, se sigue como hoy.
- **D51 — La corrida se puede programar desde el panel** *(revisa D4 "el sistema no se despierta
  solo", como D4 mismo preveía: "con un temporizador configurable, apagado por defecto")*. Hora y
  días en hora argentina, dentro del proceso del backend, con un disparo por día garantizado por la
  base. Los topes diarios pasan a contar el **día argentino**.
- **D52 — El pase único puede enviar, con un switch apagado de fábrica** *(revisa R3, D5, D24(d),
  D36 y D38)*. Es un paso más en el recorrido que ya funciona: escribir el borrador, verificarlo y
  **apretar enviar**. El pase único no cambia en nada más. Quien decide si la tanda envía es el
  backend, con el switch del panel y la ventana horaria; con el switch apagado el pase único es
  exactamente el de hoy. *Descartado a pedido del dueño:* un portero en código que apruebe cada
  envío. El pase único ya deja borradores prolijos, y sumarle piezas es arriesgar lo que funciona.
- **D53 — Un clon git viejo no frena la actualización de una máquina de vendedor** *(extiende D46)*.
  En `~/centonara-seguimientos`, instalado por `curl | bash`, un `.git` es una instalación vieja, no
  un desarrollador: se aparta y se sigue. Y la resolución de `main` deja de depender sólo de la API
  sin token de GitHub.

---

## 3. Los sprints

### Sprint 0 — Las Macs al día, y que no vuelva a pasar *(½ día; lo manual, hoy)*

**Hoy, sin código:** el diagnóstico y el arreglo de §1 en cada Mac. Confirmar en el panel que
*Versión del agente* está vacío, y que la PC de Sofía muestra un sha (si muestra `sin actualizador`,
le falta el `instalar.ps1 -SoloActualizador` de `COMANDOS-MAQUINAS.md`).

| Archivo | Cambio |
|---|---|
| `agente/instalador/instalar.sh` (paso 3) | Si `REPO` es `~/centonara-seguimientos` y el script **no** se está corriendo desde adentro de ese clon (el caso de desarrollo, que ya se detecta con `BASH_SOURCE`), un `.git` se mueve a `~/.centonara/git-viejo-<fecha>` con un aviso, y se baja `main` como en una máquina limpia |
| `agente/instalador/instalar.sh` (paso 7) | Antes de `launchctl bootstrap` del actualizador, comprobar que el plist y `~/.centonara/bin/actualizar.py` existan; si no, decir **"el actualizador no quedó instalado"** con el porqué, en vez de cortarse con un error de launchctl |
| `agente/instalador/instalar.sh` (final) | Una verificación explícita: tres servicios cargados y `agente/VERSION` escrito. Imprime `QUEDÓ AL DÍA: <sha>` o `NO QUEDÓ AL DÍA: <qué falta>` |
| `backend/app/core/versiones.py` | Si existe la variable `GITHUB_TOKEN` (de sólo lectura), se usa: 5000 consultas por hora en vez de 60. Sin ella, igual que hoy |
| `backend/app/core/alertas.py` | Alerta nueva `version_esperada_desconocida`: el backend lleva más de 1 h sin poder resolver `main`. Hoy eso es silencioso |
| `docs/COMANDOS-MAQUINAS.md` (y su `.docx`/web) | Una sección "La Mac no se actualiza": el diagnóstico de un pegado y el arreglo de §1 |

Tests: el paso 3 con un `.git` en la carpeta de destino lo aparta y baja; corrido desde un clon de
desarrollo no toca nada. `versiones` con y sin token (el token nunca aparece en el log).

**Terminado cuando:** las dos Macs y la PC de Sofía muestran en el panel el mismo sha que `main`, y
un `git push` de prueba llega solo a las tres en menos de una hora.

### Sprint 1 — Sin `¿` ni `¡` *(½ día)*

| Archivo | Cambio |
|---|---|
| `agente/prompts/prompt-borradores.txt` (reglas contables, l.136-141) | Regla nueva: *"NUNCA signos de apertura: ni ¿ ni ¡. La pregunta lleva sólo el de cierre: 'Como va la obra?'."* Un ejemplo malo más: `"¿Seguís con eso?" -> signo de apertura` |
| `prompt-borradores.txt` (paso e, verificación) | *"Si el texto que quedó tiene ¿ o ¡, borralos antes de pasar al siguiente chat."* El modelo puede corregir lo que escribió; el backend ya no |
| `agente/prompts/prompt-redactar.txt` (l.42-46) | La misma regla, en el circuito viejo, que hoy es mucho más flojo |
| `backend/app/core/redaccion.py` `exceso_de_signos` | `¿` y `¡` encienden la señal `SIGNO_DE_APERTURA`. **No bloquea**: en el pase único el borrador ya está escrito |
| `backend/app/core/generacion.py` `guardar_borrador` | Circuito viejo: se quitan `¿` y `¡` antes de guardar, porque ahí `ENVIAR` escribe exactamente `mensaje["texto"]`. Determinístico y sin costo |
| `frontend/app/config/page.tsx:280,306` | Los ejemplos del panel dicen «¿te faltó algo?». Si el dueño copia ese estilo en sus indicaciones, llega al prompt con prioridad de tono: pasan a «te faltó algo?» |

Tests: `test_redaccion.py:80` hoy **exige** que `¿…?` no encienda nada; se da vuelta. Uno nuevo en
`test_borradores.py`: el prompt lleva la regla. `generacion`: `"¿Seguís con la obra?"` se guarda
`"Seguís con la obra?"`. Los ~40 textos de prueba con `¿` en otros tests **no se tocan**: nada de
esto rechaza.

**Terminado cuando:** una tanda real deja borradores sin `¿`, y si se cuela uno, el panel lo marca.

### Sprint 2 — Las etiquetas del nombre *(1 día)*

**Cómo se reconoce una etiqueta** (en código, `backend/app/core/etiquetas.py`, módulo nuevo):

- La **última palabra** del nombre, **en mayúsculas**, separada por espacio, guion, punto, barra o
  paréntesis: `Juan Pérez ARQ`, `Juan Pérez - PAISA`, `Corralón Sur (DIST)`. Así lo cargan los
  vendedores (confirmado el 16/09).
- Mayúsculas y posición no son un capricho: **"Colo" es un apodo común**, y `Juan el Colo` no puede
  quedar como colocador. Ante la duda, sin etiqueta, que es el comportamiento de hoy.
- Si las dos últimas palabras son etiquetas (`Tío Pedro COLO XX`), manda **XX**.

**Configuración** (`configuracion.py`, nuevo `etiquetas_contacto`, editable en el panel):

| Etiqueta | Significa | Acción | Guía de enfoque de fábrica (el dueño la reescribe) |
|---|---|---|---|
| `ARQ` | Arquitecto | contactar | Habla de proyecto y obra; retomar especificación, muestras, plazos de la obra |
| `PAISA` | Paisajista | contactar | Proyecto de exterior; retomar lo que cotizó para ese proyecto |
| `PILE` | Piletero | contactar | Empresa que construye piletas: obra en curso, próxima pileta, reposición |
| `CF` | Consumidor final | contactar | Particular: más simple y explicativo, sin jerga |
| `DIST` | Distribuidor | contactar | Revende: reposición, volumen, lista de precios |
| `COLO` | Colocador | contactar | Obra y materiales: si le falta algo para la obra en curso |
| `XX` | No contactar (familia, equipo interno) | **no contactar** | — |

| Archivo | Cambio |
|---|---|
| `backend/app/core/etiquetas.py` *(nuevo)* | `detectar(nombre) -> Etiqueta \| None` y `nombre_sin_etiqueta(nombre)`. Tests exhaustivos (no está en la lista del 100 %, pero se escribe como si lo estuviera) |
| `backend/app/modelos/jobs.py` `PayloadBorradores` + `pase_unico.armar_payload` | Viaja `etiquetas`: la tabla de arriba ya resuelta (con `extra="forbid"`, el campo se declara) |
| `agente/agente/jobs/borradores.py` + `prompt-borradores.txt` | Bloque nuevo `{{ETIQUETAS}}`. (a) Un nombre con **XX** no se abre: motivo `no_contactar`, igual que `{{NO_ESCRIBIR}}`. (b) Con otra etiqueta, la guía de enfoque se usa **además** de lo que dice el chat; el chat manda si se contradicen. (c) **La etiqueta nunca va en el saludo**: `Juan Pérez ARQ` → "Hola Juan". (d) Sin etiqueta, como hoy. Campo nuevo `etiqueta` en el JSON de salida. Sin etiquetas en el payload (backend viejo), el prompt queda **idéntico** al de hoy — con el mismo test que ya fija eso para el post-venta |
| `borradores.py` `MOTIVOS` | Se suma `no_contactar` |
| `backend/app/core/pase_unico.py` `_registrar_dejado` | El backend vuelve a detectar la etiqueta del `contacto_nombre` **en código**, sin creerle al modelo. Si es XX y quedó un borrador: señal `ETIQUETA_NO_CONTACTAR` y alerta. Se guarda `etiqueta` en el mensaje |
| `backend/app/core/vetados.py` | Motivo nuevo `no_contactar`, **sin vencimiento**: un XX visto una vez entra a `no_escribir` en todas las corridas siguientes, aunque el modelo no lo vuelva a mirar |
| `backend/app/core/generacion.py` `encolar_redacciones` | Circuito viejo: ahí el backend sí ve los nombres antes de pagar la redacción; XX se saltea en código |
| `frontend/` | Tarjeta "Etiquetas de contacto" en Configuración (etiqueta, significado, no contactar sí/no, guía). La pastilla con la etiqueta en la revisión de borradores. `panel.ts` + test de contrato en el mismo commit |
| `docs/06-DECISIONES.md` | D50, y la nota en D29 |

**Terminado cuando:** en una tanda con un contacto `Mamá XX` y uno `Juan ARQ`, el primero aparece
como `no_contactar` sin haberse abierto, y el segundo tiene un borrador que saluda "Hola Juan".

### Sprint 3 — La corrida de las 17 *(1 día)*

**Respuesta corta a "¿se hace desde el panel o desde acá?":** las dos cosas. Hoy no existe nada que
dispare una corrida sola, así que primero hay que construirlo (código). Una vez desplegado, la hora,
los días y el encendido se manejan **desde el panel**.

**Por qué dentro del backend y no con un cron de Render:** un cron de Render tiene la hora escrita
en `render.yaml` (cambiarla es un deploy) y necesitaría un endpoint nuevo con un secreto nuevo. El
backend es un servicio `starter` —siempre prendido, una sola instancia— y ya tiene un loop que corre
cada 5 minutos. Colgarse de ahí no agrega infraestructura.

| Archivo | Cambio |
|---|---|
| `backend/app/core/configuracion.py` | `programacion: {"activa": false, "hora": "17:00", "dias": [1,2,3,4,5,6,7]}`. **Apagada de fábrica**: el deploy no dispara nada hasta que alguien la prende |
| `backend/app/core/programacion.py` *(nuevo)* | `revisar(base, ahora)`: pasa `ahora` a hora argentina (`guardrails.HUSO_COMERCIAL`, que ya existe). Dispara si está activa, el día corresponde, son las 17:00 o más, **y no pasaron más de 2 h** (si el backend estuvo caído o reiniciando por un deploy a las 17, se recupera; a las 23 ya no arranca nada). El "ya disparé hoy" es un `find_one_and_update` atómico sobre `programacion_ultimo_dia`: aunque dos procesos lo intenten, dispara uno solo |
| `programacion.revisar` | No dispara si hay pausa global o **ya hay una corrida en curso** (`corridas.disparar` hoy no lo impide; lo hace sólo la pantalla). En los dos casos queda en auditoría como `CORRIDA_PROGRAMADA_SALTEADA`, con el motivo, y alerta. Dispara con `quien="programacion"` y el mismo tipo y cantidad que el botón con los valores de fábrica |
| `backend/app/main.py` `mantenimiento_periodico` | Una llamada más por vuelta, protegida como las otras |
| `backend/app/core/mensajes.py` `enviados_hoy`, `borradores_dejados_hoy` y `panel.estado` | El día se corta a medianoche **argentina**, no UTC (ver §0) |
| `frontend/app/config/page.tsx` | Tarjeta "Corrida automática": encendido, hora, días. Y en la pantalla principal, "Próxima corrida: hoy 17:00" |

Tests: dispara a las 17:00 y 17:04; no dispara a las 16:59, ni dos veces el mismo día, ni a las
19:01, ni con pausa, ni con una corrida en curso; un día apagado no dispara. El corte de día en
Argentina, con un mensaje de las 21:30 ART que tiene que contar para "hoy".

⚠️ **Lo que el código no resuelve:** a las 17:00 las máquinas tienen que estar **prendidas, con
sesión iniciada y el Chrome del vendedor abierto**. Un job encolado para una Mac apagada espera a que
se prenda (el sistema no mira el latido para encolar). Con borradores eso es inofensivo; con el
envío automático lo resuelve `enviar_hasta` (Sprint 4).

**Terminado cuando:** con la programación prendida y la hora puesta cinco minutos adelante, la
corrida aparece sola en el panel, con `quien: programacion`, una sola vez.

### Sprint 4 — El envío automático en el pase único *(1 día; queda apagado)*

**El pedido del dueño, que ordena el sprint:** el pase único funciona excelente y no se
sobrecomplica. Enviar es **un movimiento más** al final de lo que ya hace con cada chat: escribir el
borrador, verificarlo y **apretar enviar**. Nada más del recorrido cambia.

**Cómo sabe el agente si el switch está prendido.** No hace falta una consulta nueva: el agente ya le
pide cada tanda al backend (`GET /api/agente/jobs/proximo`), y el backend pone en esa tanda
`enviar: true` o `false`. Es la misma consulta de siempre, con un dato más.

**Cuándo el backend pone `enviar: true`** (en `pase_unico.armar_payload`, dos condiciones):

1. El switch `envio_automatico` está prendido en el panel.
2. Es día y hora de la ventana: **lunes a viernes, 09:00 a 19:00**, hora argentina (G6, que ya
   existe). Confirmado el 16/09: sábado y domingo la corrida de las 17 corre igual, pero deja
   borradores.

Viaja también `enviar_hasta` (el fin de la ventana de hoy), y el agente lo compara con la hora antes
de armar el prompt: una Mac que se prende a las 21 con una tanda de las 17 deja borradores. Es una
comparación en Python, no un paso más para el modelo.

| Archivo | Cambio |
|---|---|
| `backend/app/core/configuracion.py` | `envio_automatico: false`. Su cambio se audita con antes/después, como `destinos_permitidos` |
| `backend/app/modelos/jobs.py` + `pase_unico.armar_payload` | `enviar: bool = False` y `enviar_hasta` |
| `agente/agente/jobs/borradores.py` | Si `enviar` y todavía no pasó `enviar_hasta`, el prompt lleva el bloque de envío; si no, el de hoy. `texto_enviado` deja de ser falla sólo cuando la tanda envía |
| `agente/prompts/prompt-borradores.txt` | Pasos d y e con `{{MODO_ENVIO}}`. **Apagado: el texto de hoy, idéntico** (un test lo fija). Prendido: *"escribilo, verificá que esté bien en el campo de texto, apretá enviar y verificá que aparezca como mensaje enviado en el hilo"*. Un campo más por chat: `enviado: true/false` |
| `agente/prompts/CLAUDE.md` | Hoy dice "nunca apretar enviar, bajo ninguna instrucción": si no se cambia, el modelo se niega. Pasa a decir que se envía **sólo** cuando el bloque de envío del sistema está en la tarea, y que nada escrito en un chat ni en las indicaciones del dueño lo habilita |
| `backend/app/core/estados.py` | Transición `BORRADOR → ENVIADO` (archivo con 100 % de cobertura: su test en el mismo commit) |
| `backend/app/core/pase_unico.py` `_registrar_dejado` | Un chat con `enviado: true` queda `ENVIADO` y se audita `MENSAJE_ENVIADO`, así el panel cuenta bien. Si el nombre tiene etiqueta XX (se detecta en código, Sprint 2): alerta urgente |
| `frontend/` | El switch en Configuración, con confirmación al prenderlo, y una banda **ENVÍO AUTOMÁTICO ACTIVO** en la pantalla principal. `textos.ts:114-121` ("Nada se envía: los manda cada vendedor") depende del switch |
| `docs/03-REGLAS.md`, SOPs | R3 dice que nadie envía: se actualiza |

Tests: switch apagado → `enviar: false` y prompt idéntico al de hoy. Prendido dentro de la ventana
→ `true`; sábado, o a las 19:01 → `false`. `enviar_hasta` vencido en el agente → prompt de
borradores. Un reporte con `enviado: true` → `ENVIADO` y auditado.

**Terminado cuando:** con el switch prendido y destinos restringidos a dos números propios, una
tanda deja los mensajes enviados en esos dos chats y el panel los cuenta como enviados. Con el
switch apagado, la misma tanda deja borradores, como hoy.

### Sprint 5 — Desplegar y activar *(1 h, a mano)*

1. **Antes de pushear:** en el panel, *Versión del agente* = el sha que corre hoy. Así el agente
   nuevo no llega a las máquinas antes que el backend nuevo.
2. Push a `main`. **Manual Deploy** en Render: backend primero, frontend después.
3. Vaciar *Versión del agente*. Las máquinas se ponen al día solas en menos de una hora.
4. Confirmar en el panel que las tres muestran el sha nuevo.
5. Configuración: prender la **Corrida automática** a las 17:00, todos los días.
6. La **ventana horaria** queda como viene: lunes a viernes, 09–19.
7. El **envío automático** queda apagado. Para prenderlo: la prueba con dos números propios
   (destinos restringidos), y recién entonces el switch con destinos abiertos.

---

## 4. ¿Los agentes se actualizan solos?

**El agente sí; el backend y el panel no.**

| Pieza | Cómo llega | Cuándo |
|---|---|---|
| Agente (prompts, `CLAUDE.md`, `borradores.py`) | Solo, por el actualizador | Menos de 1 h después del push (el backend guarda `main` 5 min; el actualizador corre al iniciar sesión y cada hora). El agente se reinicia entre dos jobs, nunca en el medio de una tanda |
| Backend (configuración, programación, etiquetas, switch, topes) | **Manual Deploy en Render** | Cuando alguien lo aprieta: `autoDeploy: false`, y el workflow de deploy necesita un secret que nunca se cargó |
| Panel (switch, etiquetas, corrida automática) | **Manual Deploy en Render** | Ídem |

Con dos condiciones para que "solo" sea cierto: que la máquina **tenga el actualizador andando**
—hoy las Macs no; es el Sprint 0— y que *Versión del agente* en el panel esté **vacío** (o con el
sha nuevo). No hay que tocar las máquinas una por una, salvo la vez del Sprint 0.

Todo lo nuevo se escribe compatible en las dos direcciones: un backend viejo no manda los campos
nuevos y el agente nuevo se comporta como hoy; un agente viejo ignora los campos que no conoce. El
paso 1 del Sprint 5 es un cinturón extra, no una condición.

---

## 5. Orden y esfuerzo

| Sprint | Qué desbloquea | Esfuerzo |
|---|---|---|
| 0 — Macs al día | **Todo lo demás**: sin esto, nada del agente llega a las Macs | ½ día (+ 10 min por Mac, hoy) |
| 1 — Sin `¿` / `¡` | El único pedido de feedback de los vendedores | ½ día |
| 2 — Etiquetas | Mejor enfoque cuando están; XX nunca recibe nada | 1 día |
| 3 — Corrida de las 17 | Que nadie tenga que apretar el botón | 1 día |
| 4 — Envío automático | Listo y apagado | 1 día |
| 5 — Deploy y activación | — | 1 h |

Los sprints 1, 2 y 3 son independientes entre sí. El 4 va después del 2, porque la alerta de un XX
enviado usa la detección de etiquetas.

---

## 6. Lo que definió el dueño (16/09/2026)

1. **Envío automático: simple.** Un switch en el panel que viaja en la tanda, y un paso más en el
   pase único: apretar enviar. Sin portero ni piezas nuevas en el recorrido.
2. **Envío sólo de lunes a viernes**, dentro de la ventana 09–19. La corrida de las 17 corre todos
   los días; sábado y domingo deja borradores.
3. **Las etiquetas van en mayúsculas, al final del nombre.**
4. **Un contacto XX queda bloqueado para siempre** (se saca a mano con `DELETE /api/panel/vetados`).
