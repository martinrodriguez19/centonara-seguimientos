# Plan — Horarios, cuota de Claude, repesca y máquinas ausentes

> **El pedido.** Cinco cosas, todas sobre *cuándo* trabaja el sistema y qué hace cuando algo no
> está: (1) que el actualizador no trabaje cada hora sino una vez por día, a una hora que se elige
> en el panel; (2) que si una máquina se queda sin tokens de Claude se apague sola y vuelva a las
> 3–4 horas, y —de yapa— que las máquinas descansen de noche en vez de estar prendidas 24/7;
> (3) que la PC Windows que queda "Ready" y no "Running" se levante sola 15 minutos antes de la
> corrida; (4) una corrida extra, a una hora elegida, que revise si cada máquina hizo lo que tenía
> que hacer y complete lo que falta; (5) que una máquina apagada no deje la corrida colgada: que
> quede afuera, la corrida termine y se pueda largar otra.
>
> Fecha: 02/10/2026. Base: `main` en `e283960`. Estado: **implementado entero el mismo día**
> (sprints 1 a 4), sin commitear ni desplegar. Decisiones
> D59–D64, numeradas en el orden de los sprints (§6 = D59, §4 = D60, §5 = D61, §3 = D62, §2 = D63,
§7 = D64); cada una se escribe en `06-DECISIONES.md` antes de tocar código, como siempre. Las
> respuestas del dueño están en §9 y ya aplicadas en el texto.
>
> **La segunda regla, del dueño: nada de esto pide tocar una computadora.** Ni terminal, ni ir a la
> máquina, ni reinstalar. Todo llega con el deploy y el actualizador que ya está en cada máquina, y
> todo se maneja desde el panel. Lo que el sistema operativo no deja hacer sin permiso de
> administrador se resuelve con un cuadro del sistema que acepta el vendedor desde su silla, o
> queda como está y se dice (§7).
>
> **La regla que ordena el plan: lo que anda no se toca.** No cambia qué chats se leen, cómo se
> redacta, cómo se deja un borrador ni cómo se envía. No cambia la corrida de las 17 (D51), el
> pase único (D38–D44), el canario (D35) ni la cadena de versiones (D45–D58). Todo lo nuevo es
> *alrededor* de la corrida: cuándo arranca, quién entra, cuándo termina, qué pasa después.

---

## 0. Qué hay hoy, verificado en el código

| Tema | Qué hay hoy | Dónde |
|---|---|---|
| Actualizador | Corre **al iniciar sesión y cada hora**. El intervalo está escrito en los instaladores (`StartInterval 3600`; `-RepetitionInterval 1h`). En cada vuelta pregunta `GET /api/agente/version-esperada`; si coincide con `VERSION` sale; si no, baja el tarball, `uv sync`, y el agente se reinicia solo entre jobs | `instalar-mac.sh:251`, `instalar.ps1:141`, `actualizar.py:471-567`, `api/agente.py:365` |
| Cambiar el horario del actualizador | La tarea/plist sólo se escribe al instalar. El actualizador reemplaza su propia copia pero **nunca reescribe su disparador** → un cambio en el instalador no llega a las máquinas sin volver a correrlo | `actualizar.py:451-463` |
| Cuota de Claude agotada | **No se reconoce.** Sale como `ERROR_INESPERADO`, se reintenta 3 veces en ~90 s y queda `fallido`. Nadie pausa la máquina ni espera al reinicio de la cuota. El `LIMITE_USO` de D38 que quedó en la rama `trabajo-local-limite-uso` **ya no existe**: la rama no está en el repositorio | `jobs/claude_code.py:180-243`, `core/cola.py:434-516` |
| Pausas | Global: `pausa_global` (kill switch). Por máquina: `activo`, `frenado_por_canario_en`, `pausado_hasta`. Con cualquiera, `GET /jobs/proximo` devuelve 423 y el agente espera 60 s sin gastar nada | `core/vendedores.py:265-280`, `api/agente.py:182-195` |
| Energía | Ningún instalador toca `caffeinate`, `pmset` ni `powercfg`. La guía del panel pide a mano `powercfg … standby 0` en Windows. No hay nada para Mac | `frontend/lib/guia.ts:676-719` |
| Windows "Ready" | El agente lo lanza la tarea "Centonara Agente" **sólo al iniciar sesión**. Cuando hay versión nueva, el agente lanza un hijo desacoplado y sale con 0: la tarea queda *Ready* y ya no es dueña del proceso. Si ese hijo muere, **nadie lo levanta hasta el próximo inicio de sesión**. En Mac, `KeepAlive` lo cubre. Está anotado como 3.6 en `PLAN-INSTALACION-Y-REINSTALACION.md`, sin aprobar | `agente/reinicio.py:107-161`, `instalar.ps1:367-374` |
| Quién entra a una corrida | `maquinas_disponibles` = todas las que no están pausadas. **No mira el latido**: una PC apagada recibe su job igual ("si la Mac se prende más tarde, toma el job") | `core/corridas.py:66-75` |
| Cuándo termina una corrida | "Terminada" = no queda ningún job `pendiente`/`tomado`. Un job `pendiente` **no vence nunca**. Si una máquina no aparece, la corrida queda "en curso" hasta que alguien aprieta Cancelar, y la programada del día siguiente se saltea (`corrida_en_curso`). La del 29/09 estuvo 21 h así | `core/corridas.py:215-238`, `core/programacion.py:129` |
| Verificar el trabajo | **No existe.** Los topes son techos (`tope_diario_borradores` = 20 por máquina y día), no metas. El panel muestra `dejados / 20` sin avisar si quedó corto. El "por qué paró" sí queda: `tandas[].fin` (`tope_diario_borradores`, `fin_de_ventana`, `tanda_vacia`, …) | `core/pase_unico.py:98-141, 595-628`, `core/mensajes.py:307-340` |
| Programar algo | El patrón ya existe y anda: `mantenimiento_periodico` cada 5 min → `programacion.revisar`, hora argentina, marca diaria atómica en la colección `programacion`, dos horas de gracia, y lo salteado queda en la auditoría | `core/programacion.py`, `main.py:31-68` |

Tres cosas que salen de esto y ordenan todo lo demás:

1. **El punto (5) es la base de los otros.** La repesca y la reactivación por cuota necesitan que
   una corrida *termine*; hoy una sola PC apagada la deja abierta y bloquea todo lo programado.
2. **El agente puede reprogramar las tareas de su propia máquina, sin administrador.** En Windows
   las tres tareas se registraron como el usuario, con `-RunLevel Limited` (`instalar.ps1:123`):
   el mismo usuario las puede cambiar. En Mac son `LaunchAgents` del usuario
   (`~/Library/LaunchAgents`): el agente puede reescribir el del actualizador y recargarlo sin
   `sudo`, porque es otro servicio y no se mata a sí mismo. Eso es lo que permite cambiar horarios
   sin que nadie toque la máquina (§2).
3. **La PC Windows no tiene quién la levante.** Lo único que corre ahí además del agente es la
   tarea del actualizador; es el lugar natural para un guardián (§3).

---

## 1. Línea del día, como queda

Todas las horas se eligen en el panel (Ajustes → Automático → **Horarios**), en hora argentina, con
los mismos controles que ya tiene la corrida programada (`CampoHora`, `DiasDeLaSemana`).

```
 00:00 ─── descanso ─── 08:00     15:00         16:45       17:00          20:45      21:00
   │  el agente suspende  │         │              │           │              │          │
   │  la computadora      │    actualización   revisión    corrida        revisión   repesca
   │  (§7)                │    del día (§2)    antes de    programada     antes de   (§5)
   └──────────────────────┘                    la corrida  (D51, igual)   la repesca
                                               (§3)           │           (§3)
                                              sin cuota → pausa hasta el reinicio (§4)
                                              PC ausente → afuera, la corrida termina (§6)

 Domingo: descanso todo el día (del domingo 00:00 al lunes 08:00, seguido). Sin corrida ni repesca.
```

En cada máquina, la tarea del actualizador deja de correr cada hora y corre **cuatro veces por
día**: al iniciar sesión, a la hora de la actualización, y 15 minutos antes de la corrida y de la
repesca. Las horas las pone el panel; el agente las copia a su máquina (§2).

Valores de fábrica: actualización 15:00, corrida 17:00 (la que ya está), repesca 21:00, descanso
00:00–08:00 de lunes a sábado y domingo entero. **Todo nuevo nace apagado**, como D51: el deploy no
cambia nada hasta que se prende en el panel.

---

## 2. El actualizador, una vez por día y a horario *(D63)*

Dos piezas: el backend decide **si** hay que actualizar, y el agente decide **cuándo** se despierta
el actualizador en su máquina.

**2.A El backend sólo entrega la versión nueva a la hora elegida.** El endpoint `version-esperada`
ya tiene la regla "si no corresponde, el actualizador no hace nada": con `sha` vacío,
`actualizar.py:503-506` escribe "no se sabe qué versión toca (…): no se toca nada" y sale. Fuera
del horario el backend contesta `sha: ""` con `origen: "fuera_de_horario"`; dentro del horario, la
versión nueva. Funciona **con el `actualizar.py` que ya está instalado**: desde el deploy del
backend, bajar, `uv sync` y reiniciar pasan una vez por día, sin tocar ninguna máquina.

**2.B El agente reprograma la tarea del actualizador.** Con 2.A la tarea igual se despierta cada
hora para hacer una consulta de un segundo. Para que deje de hacerlo, el agente copia los horarios
del panel a su máquina:

- El backend agrega `horarios` a la respuesta del registro y del latido: hora de actualización, de
  la corrida y de la repesca, y el descanso.
- El agente compara con lo que dejó la última vez (`~/.centonara/estado/horarios.json`) y, si
  cambió, reescribe los disparadores del actualizador: al iniciar sesión + a las 15:00 + 15 min
  antes de la corrida + 15 min antes de la repesca, los días que corresponda.
  - **Windows:** `Set-ScheduledTask "Centonara Actualizador"` con los disparadores nuevos (sin la
    repetición horaria) y `-StartWhenAvailable`, que ya tiene: si la PC estaba suspendida a esa
    hora, corre al despertar. Permiso de usuario, sin administrador.
  - **Mac:** reescribe `com.centonara.actualizador.plist` con `StartCalendarInterval` en vez de
    `StartInterval 3600`, y `launchctl bootout` + `bootstrap` de **ese** servicio. launchd también
    corre al despertar lo que se perdió durmiendo.
- Si algo falla, no toca nada más: la tarea queda como estaba (cada hora, que anda) y el agente
  manda en su latido `tareas: falla` con el motivo → chequeo en la tarjeta de la máquina.
- Cuando se cambia una hora en el panel, la máquina la toma en su próximo latido (30 s).

**Cómo llega sin que nadie toque nada:** el código nuevo del agente viaja por el actualizador de
hoy, cada hora, como cualquier versión. Al reiniciarse con la versión nueva, el agente reprograma
la tarea. Desde ahí, cuatro veces por día.

**"Actualizar ahora"** para un arreglo urgente: ya no puede esperar a la vuelta horaria. El botón
del panel le avisa a cada agente vivo en su latido (`actualizar_ya`) y el agente dispara la tarea
del actualizador (`Start-ScheduledTask` / `launchctl kickstart`). El backend abre la entrega de la
versión nueva por una hora.

| # | Cambio | Dónde |
|---|---|---|
| 2.1 | `actualizacion: {activa: False, hora: "15:00", forzar_hasta: None}` en `POR_DEFECTO` | `core/configuracion.py` |
| 2.2 | `version-esperada`: si `activa` y no estamos en `[hora, hora + 2 h)` ni antes de `forzar_hasta`, devuelve `sha: ""`, `origen: "fuera_de_horario"`. Función pura `toca_actualizar(config, ahora)` con test, en el estilo de `programacion._toca` | `api/agente.py:365`, `core/versiones.py` |
| 2.3 | `horarios` y `actualizar_ya` en las respuestas de registro y latido | `api/agente.py` |
| 2.4 | El agente reprograma la tarea del actualizador (Windows y Mac) y reporta `tareas` | `agente/agente/tareas.py` (nuevo), `bucle.py` |
| 2.5 | Botón **"Actualizar ahora"** en Ajustes → Versión del agente | `components/config/sistema.tsx`, `api/panel.py` |
| 2.6 | La alerta `maquina_desactualizada` hoy espera 2 h (`HORAS_PARA_ACTUALIZARSE`), pensando en la vuelta horaria. Con el horario prendido, cuenta desde el fin de la ventana de hoy | `core/alertas.py:43, 381-420` |
| 2.7 | El panel muestra "se actualiza a las 15:00" en vez de "atrasada" mientras la versión nueva espera su hora | `api/panel.py:146`, `lib/derivados.ts` |

---

## 3. Revisión antes de la corrida: la PC Windows no se queda "Ready" *(D62)*

Dos partes: arreglar la causa y revisar justo antes de que haga falta. **No cada 15 minutos:** una
vez, 15 minutos antes de la corrida, y otra antes de la repesca.

**3.1 La causa (es el 3.6 ya escrito en el plan de instalación).** Cuando el agente de Windows ve
una versión nueva, en vez de lanzar un hijo desacoplado y salir con 0, **sale con 75** y deja que
la tarea lo levante (ya tiene `-RestartCount 999 -RestartInterval 1min`; con salida ≠ 0 eso sí
actúa). La tarea vuelve a ser la dueña del proceso: queda *Running* y se terminan los agentes
duplicados. Es código del agente: llega solo con la actualización. — `agente/reinicio.py`.

**3.2 La revisión.** Las vueltas del actualizador de 16:45 y 20:45 (§2.B) empiezan, antes de
preguntar la versión y **sin red**, por mirar si el agente está vivo: si `vivo.json` tiene más de 3
minutos y no hay ningún proceso `agente.main`, arranca el agente (`Start-ScheduledTask "Centonara
Agente"` / `launchctl kickstart`; las dos ya existen en `actualizar.py:429-448`). Decide por la
señal de vida y no por lo que dice el Programador de tareas, así un agente vivo nunca se duplica.
Las vueltas de inicio de sesión y de las 15:00 hacen lo mismo, de paso.

- Es código de `actualizar.py`, que se copia solo a `~/.centonara/bin` en cada actualización
  (`actualizar.py:451-463`): llega sin tocar la máquina.
- Corre en Mac también, aunque ahí `KeepAlive` ya levanta el agente.
- No revive durante el descanso (§7).
- Cuando revive al agente, éste se registra con `arranque: "revision"` → evento en el historial de
  la máquina, para saber cuántas veces pasa.

---

## 4. Sin tokens: la máquina se pausa sola y vuelve *(D60)*

| # | Cambio | Dónde |
|---|---|---|
| 4.1 | **Reconocer la cuota agotada.** Una lista única de textos (en minúsculas): `usage limit`, `limit reached`, `you've hit your limit`, `rate_limit_error` con `429`, y el sobre JSON con `is_error: true` aunque `returncode == 0`. Código propio **`LIMITE_USO`**. Se extrae la hora de reinicio si viene (`…|<epoch>` o `resets 9pm`, `resets Oct 6, 9am`); si no, no se inventa | `agente/jobs/claude_code.py:_leer`, `_desenvolver` |
| 4.2 | `LIMITE_USO` en `Codigo`, en `_NO_SE_REINTENTAN` y fuera de `maquina_falla_siempre` (no es una falla de la máquina) | `core/cola.py:80-157`, `core/alertas.py:330` |
| 4.3 | Al recibirlo: la máquina queda con **`pausa_cuota_hasta`** = la hora de reinicio + 10 min, o `ahora + horas_pausa_cuota` (config, **4 h** de fábrica) si no vino. Campo **propio**: no pisa el `pausado_hasta` que pone el dueño. `esta_pausada` lo suma | `core/vendedores.py`, `api/agente.py:/jobs/{id}/resultado` |
| 4.4 | El job queda `fallido/LIMITE_USO` (no se deja esperando 4 h): **la corrida puede terminar** con las demás máquinas. Lo que faltó lo completa la repesca (§5) | `core/cola.py:reportar` |
| 4.5 | Alerta urgente propia, con `maquina`: "*Sofía* se quedó sin cuota de Claude. Vuelve sola a las 21:10". Se apaga sola al vencer la pausa | `core/alertas.py` |
| 4.6 | En la tarjeta de la máquina, estado **"Sin cuota hasta 21:10"** (distinto de "Pausada", que es del dueño) y botón "Quitar" | `lib/derivados.ts:situacion`, `components/maquinas/*` |

Mientras dura la pausa el agente recibe 423 y espera de a 60 s: **no gasta un token**. Cuando
vence, no arranca nada solo: la máquina queda disponible para la repesca o la corrida siguiente.

**Por máquina, no global.** Cada máquina tiene su sesión de Claude. Si dos comparten cuenta, la
segunda se entera en su próximo job, y eso cuesta una llamada fallida, no una corrida. Pausar
todo el sistema porque una cuenta se quedó sin cuota frenaría a las otras cuatro.

**Lo que no se puede probar desde acá:** el texto exacto que imprime Claude Code de la cuenta del
cliente cuando se queda sin cuota (cambia entre versiones y entre planes). No hace falta ir a la
máquina: el fallo ya llega al panel (Errores, el motivo del job con los últimos 300 caracteres de
lo que dijo Claude). Se copia de ahí la próxima vez que pase y, si no coincide con la lista de 4.1,
se agrega. Mientras tanto, un texto no reconocido sigue el camino de hoy: tres intentos y fallido.

---

## 5. La repesca: revisar y completar *(D61)*

Una segunda vuelta programada, a la hora que elija el usuario (21:00 de fábrica), que hace
**dos cosas**: mira qué hizo cada máquina hoy y, a la que le faltó, le larga una corrida sólo a ella.

**"Lo que tenía que hacer"** = `tope_diario_borradores` (20) por máquina y por día argentino. El
conteo ya existe y es el del backend (`borradores_dejados_hoy`: borradores dejados + enviados).
Una máquina **no está en falta** si paró porque no quedaban chats (`fin_de_ventana`,
`tanda_vacia`): hizo todo lo que había.

Por máquina, la repesca anota una de estas:

| Resultado | Cuándo | Qué hace |
|---|---|---|
| Completa | `dejados ≥ tope` | Nada |
| Sin chats | la última tanda de hoy terminó en `fin_de_ventana` / `tanda_vacia` | Nada |
| **Repescada** | le faltan y está disponible | Entra a la corrida de repesca |
| Sin cuota | `pausa_cuota_hasta` todavía no venció | Nada; queda dicho |
| Ausente | sin latido hace más de 10 min | Nada; queda dicho |
| Pausada | la pausó el dueño | Nada |

**Cómo completa sin lógica nueva:** la corrida de repesca es una corrida de generación normal,
sólo con las máquinas en falta. El pase único **ya** limita cada máquina a lo que le queda del día
(`_presupuesto` resta `borradores_dejados_hoy` del tope): si Sofía dejó 14, la repesca le hace 6,
no 20. Ningún número nuevo.

| # | Cambio | Dónde |
|---|---|---|
| 5.1 | `repesca: {activa: False, hora: "21:00", dias: [1..6]}` en la config (domingo no) | `core/configuracion.py` |
| 5.2 | `programacion.py` se generaliza a **varias tareas con su propia marca diaria** (`_id: "corrida"`, `"repesca"`, …) en vez de `"unica"`. La corrida de las 17 conserva su marca (migración: leer `"unica"` como `"corrida"` una vez) | `core/programacion.py` |
| 5.3 | `repesca.revisar`: el resumen por máquina (tabla de arriba) y `corridas.disparar(..., maquinas=[…], motivo="repesca")` | `core/repesca.py` (nuevo) |
| 5.4 | `disparar` acepta una lista de máquinas; si no se pasa, las de siempre. La corrida guarda `motivo` (`manual`, `programada`, `repesca`) para el historial | `core/corridas.py:78` |
| 5.5 | El resumen se guarda en la corrida (`revision_del_dia`) y sale en el historial y en una tarjeta "Hoy" del inicio: "4 de 5 completas · Sofía repescada (faltaban 6) · Lautaro sin cuota hasta 22:10" | `core/corridas.py`, `app/(panel)/panel/page.tsx` |
| 5.6 | Si después de la repesca alguna sigue en falta sin motivo, aviso (no urgente) | `core/alertas.py` |

Reglas de borde:
- Si hay una corrida en curso a la hora de la repesca, **espera** dentro de su ventana de gracia
  (2 h, como D51) en vez de saltearse; si no se libera, queda en la auditoría como salteada.
- **Envía si el cliente lo decidió.** La repesca no tiene un modo propio: si el envío automático
  (D52) está prendido, la repesca envía igual que la corrida de las 17, con la misma regla de
  siempre — sólo dentro de la ventana de envío del panel (hoy L–V 09:00–19:00). Una repesca a las
  21 con esa ventana **sólo dejaría borradores**. Para que no sea una sorpresa, al guardar la hora
  de la repesca el panel avisa: "A las 21:00 la repesca sólo deja borradores: la ventana de envío
  termina a las 19:00. Para que envíe, adelantá la repesca o extendé la ventana". Las dos cosas
  las decide el cliente desde el panel; el sistema no amplía la ventana solo.
- La repesca sólo aplica al pase único (`modo_borrador` extensión). Con el camino viejo de LISTAR
  no hay presupuesto por máquina y repetir la corrida duplicaría trabajo: se saltea y lo dice.

---

## 6. La máquina ausente queda afuera y la corrida termina *(D59; revisa D51 en parte)*

Tres capas, de la más barata a la más fuerte:

| # | Cambio | Dónde |
|---|---|---|
| 6.1 | **Al largar.** `maquinas_disponibles` deja afuera a la que no tiene latido de los últimos 10 min (`MINUTOS_CAIDA`, el mismo número de la alerta). La corrida guarda `maquinas_excluidas: [{maquina, motivo}]` (`sin_latido`, `sin_cuota`, `pausada`) y el panel las muestra en el detalle. Si no queda ninguna, el 409 `NoHayMaquinas` de siempre | `core/corridas.py:66-75` |
| 6.2 | **Durante.** En cada vuelta del mantenimiento: si una máquina de una corrida en curso lleva **20 min sin latido** y tiene jobs `pendiente`/`tomado`, esos jobs pasan a `fallido/MAQUINA_AUSENTE` (código nuevo, no se reintenta, evento en el historial). Un agente ocupado en una tanda de 35 min **no** cuenta como ausente: el latido corre en paralelo cada 30 s | `core/corridas.py`, `main.py:mantenimiento_periodico` |
| 6.3 | **Techo.** Una corrida que sigue abierta **5 h** después de largada (config `horas_max_corrida`) cierra lo que quede como `fallido/VENCIDO`. Es el 3.4 del plan de instalación | idem |
| 6.4 | `POST /corridas` devuelve **409 si hay una en curso** (hoy sólo lo impide el botón). Con dos disparadores automáticos —17 y repesca— la guarda tiene que estar en el backend | `core/corridas.py:disparar`, `api/panel.py:349` |

Lo que esto **no** cambia: el canario (D35), el respaldo de B2, la pausa global y cómo se ve una
corrida sana. Si la PC vuelve después de quedar afuera, no retoma nada viejo: entra a la repesca
de esa noche o a la corrida del día siguiente, con su presupuesto intacto.

Revisa la frase de D51 "un job para una Mac apagada la espera": ahora no la espera.

---

## 7. Descanso: de noche y los domingos, lo hace el agente *(D64)*

A la hora del descanso el agente termina el job que tenga, no toma otro y **suspende** la
computadora (sin administrador: `SetSuspendState` en Windows, `pmset sleepnow` en Mac). **No
programa ningún despertar: a la mañana la despierta el vendedor cuando llega al negocio**
(respuesta del dueño, §9). Suspender y no apagar: se conserva la sesión, el Chrome y WhatsApp.

**El horario:** las noches de lunes a sábado de 00:00 a 08:00, y el domingo entero: del domingo
00:00 al lunes 08:00 es un solo descanso. Editable en el panel, con un switch "Suspender" (apagado,
descansan sin dormirse).

| # | Cambio | Dónde |
|---|---|---|
| 7.1 | `descanso: {activa: False, desde: "00:00", hasta: "08:00", dias: [1..6], dia_libre: [7], suspender: True}` | `core/configuracion.py` |
| 7.2 | Durante el descanso: `/jobs/proximo` 423 "descanso", el latido responde `descanso_hasta`, `version-esperada` contesta `sha: ""` (`origen: "descanso"`), la corrida y la repesca no disparan | `api/agente.py`, `core/programacion.py`, `core/repesca.py` |
| 7.3 | El agente deja `descanso.json` (el guardián no lo revive) y suspende, una vez por descanso | `agente/agente/descanso.py` |
| 7.4 | En el panel: "Descansando hasta…" durante el descanso y "Dormida: la despierta el vendedor" después, en vez de "Sin conexión" | `api/panel.py`, `lib/derivados.ts` |
| 7.5 | Alerta urgente **una hora antes de la corrida** si una máquina sigue dormida | `core/alertas.py` |
| 7.6 | El panel avisa si la corrida o la repesca caen dentro del descanso | `components/config/envio.tsx` |

---

## 8. Orden de trabajo

| Sprint | Qué | Por qué en este orden | ¿Hay que tocar una máquina? |
|---|---|---|---|
| **1** | §6 (ausentes, techo, 409) | Es la base: sin esto, repesca y cuota quedan bloqueadas por cualquier PC apagada | No (sólo backend) |
| **2** | §4 (cuota) + §5 (repesca) | Van juntos: la cuota cierra el job, la repesca completa | No (el agente llega con el actualizador de hoy) |
| **3** | §3 (3.1 + la revisión) + §2 (horarios) | Tienen que salir juntos: al pasar el actualizador de "cada hora" a "cuatro veces por día", la revisión de las 16:45 tiene que estar ya en esa misma versión. Esta versión todavía viaja por la vuelta horaria | No |
| **4** | §7 (descanso) | Lo más nuevo y lo único que toca energía. Se prende primero una noche sin "Suspender" | No. A la mañana la despierta el vendedor |

Cada sprint: decisión escrita en `06-DECISIONES.md` antes del código, tests (backend con Mongo
real; cobertura 100% en `cola` y los módulos que la exigen; en el agente, la reprogramación de
tareas y el descanso con los comandos del sistema simulados), `test_contrato_panel.py` en el mismo
commit que `lib/panel.ts`, textos en `lib/textos.ts`. Deploy como siempre: backend primero, panel
después; el agente llega solo.

**Lo que no se puede probar desde acá** y se mira en el panel después de cada deploy, no en la
máquina: que las cinco reporten `tareas: ok` (§2), que la Windows quede revisada a las 16:45, y la
primera noche de descanso (que vuelvan las cinco a las 08:00).

---

## 9. Respuestas del dueño (02/10/2026)

1. **Nada pide terminal ni ir a la máquina.** Aplicado en todo el plan: §2.B (el agente reprograma
   la tarea), §3 (sin `-SoloActualizador`), §4 (el texto de la cuota se lee en el panel), §7 (el
   permiso de Mac lo acepta el vendedor en un cuadro del sistema).
2. **Revisar antes de la corrida, no cada 15 minutos.** §3: 15 min antes de la corrida y de la
   repesca.
3. **Descanso: suspender, y que lo haga el agente. Despertar no: lo hace el vendedor cuando
   llega** (segunda respuesta, el mismo día). §7.
4. **La repesca envía si el cliente lo decidió** (envío automático prendido), dentro de la ventana
   de envío del panel. §5.
5. **Los domingos descansan.** Descanso del sábado 00:00 al lunes 08:00; corrida y repesca de lunes
   a sábado.
6. **Cuota: vuelve sola a la hora de reinicio (o 4 h) y la repesca completa.** §4.
7. **Actualización a las 15:00.** §2.

---

## 10. Encontrado en la auditoría, fuera del pedido (no se toca sin decirlo)

- `cola.recuperar_colgados` devuelve a `pendiente` cualquier job `tomado` de más de 1 h, **sin
  mirar `intentos`**: un job que cuelga siempre se reentrega para siempre. El docstring de
  `main.py` dice lo contrario y habla de "40 minutos" (el código usa 3.600 s). §6.3 lo acota por
  arriba; arreglarlo es una línea, pero es otro cambio.
- `metricas.enviados_hoy` corta el día en medianoche **UTC**; el resto del sistema usa el día
  argentino (D51).
- La rama `trabajo-local-limite-uso` ya no existe en el repositorio: lo único que se rescataba de
  ahí (`LIMITE_USO`) se rehace en §4.

---

## 11. Lo que cambió al implementar

- **Windows (D62): relevo en vez de "salir con 75".** El 3.6 confiaba en que la tarea reintente
  cuando el agente sale con 75, pero ese reintento depende de que Windows cuente la salida como
  falla. Se eligió un relevo: antes de irse, el agente lanza un PowerShell oculto que espera a que
  termine y arranca la tarea. No depende de cómo lo interprete Windows.
- **El guardián corre en todas las vueltas del actualizador**, no sólo en las de 16:45 y 20:45:
  lee un archivo y no usa red, así que no cuesta nada. Si el guardián arrancó al agente y en la
  misma vuelta hay versión nueva, no lo arranca otra vez (en una PC sin tarea serían dos agentes).
- **La alerta de "sin cuota" es aviso, no urgente**: la máquina vuelve sola y no hay nada que
  hacer; una urgente que no pide acción enseña a ignorarlas.
- **"Reprogramar la tarea" se hace una vez por arranque del agente**, sin archivo de estado: si
  alguien reinstala, el instalador vuelve a dejar la tarea cada hora, y un "ya lo apliqué"
  guardado no lo vería.
- **Un "Actualizar ahora" no depende de que se pueda reprogramar la tarea**: si lo segundo falla,
  lo primero se hace igual (lo encontraron los tests).
- **La repesca espera dentro de su gracia** si hay una corrida en curso, sin consumir el día; en
  los últimos 10 minutos de la gracia queda salteada en la auditoría.
- **El descanso tiene un switch "Suspender"**: apagado, las máquinas descansan sin dormirse. Es la
  salida si WhatsApp no vuelve bien de la suspensión (PENDIENTE-CON-MAQUINA H7).
- **Sin despertar automático.** Se implementó primero (tarea con `-WakeToRun`, `pmset repeat` con
  el cuadro de contraseña en Mac) y se sacó por pedido del dueño: el vendedor la despierta al
  llegar. El aviso de "no volvió" pasó de "15 minutos después del descanso" a "una hora antes de
  la corrida", que es cuando importa.
- **El botón "Generar" cuenta sólo máquinas con señal de vida**, porque desde D59 una apagada no
  recibe trabajo.
- Las decisiones quedaron numeradas en el orden de los sprints (D59 = máquinas ausentes).

**Qué se activa a mano** y qué hay que mirar en las máquinas: `PENDIENTE-CON-MAQUINA.md` §H.

