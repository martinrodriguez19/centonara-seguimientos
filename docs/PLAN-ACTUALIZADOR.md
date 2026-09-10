# Plan — Que los agentes se actualicen solos (Mac y Windows)

> **El pedido.** Hoy actualizar el agente es correr el instalador a mano en cada máquina, y
> reinstalar de cero cuando algo falta. Se pide: un actualizador propio, que corra cada vez que el
> cliente prende la máquina, en Mac **y** en Windows, y que no dependa del `deviceId` para poder
> actualizar.
>
> Fecha: 10/09/2026. **Estado: los seis sprints están implementados** (mismo día). Decisiones
> registradas como [D45–D48](06-DECISIONES.md). Backend y agente en verde con sus tests nuevos;
> el frontend se escribió contra los tipos y **no se pudo compilar en la máquina de desarrollo**
> (sin red al registry de npm): falta `pnpm typecheck`. Lo que necesita una máquina real está en
> [`PENDIENTE-CON-MAQUINA.md`](PENDIENTE-CON-MAQUINA.md).
>
> **Un cambio de diseño respecto de lo propuesto abajo, en el Sprint 2:** el actualizador no es
> un shell script sino `actualizar.py` —un archivo, sólo biblioteca estándar, el mismo en Mac y
> Windows— y **no reinicia al agente**: el agente se reinicia solo cuando ve que `agente/VERSION`
> cambió, entre dos jobs. Eso hizo que el actualizador se pueda probar entero sin red ni launchd,
> y que Windows saliera casi gratis. El resto del plan se implementó como está escrito.
>
> **El hallazgo que ordena el plan:** de las tres máquinas de la corrida del 09/09, la que
> funcionó (Sofía, **Windows**, instalada a mano) tenía el agente nuevo; las dos Macs —las que se
> instalaron con `instalar.sh`— fallaron. Y **el sistema no podía decir cuál era cuál**: las tres
> reportaron `version: 0.1.0`, el panel no muestra por qué falló una tanda, y nadie avisó que dos
> de tres máquinas produjeron cero toda la tarde. Por eso el Sprint 1 no actualiza nada: hace
> visible qué versión corre cada máquina. Un actualizador que no se puede verificar es un
> actualizador en el que no se puede confiar.
>
> **La regla que gobierna el alcance:** la máquina de Sofía funciona. Nada de este plan la toca
> hasta que el actualizador esté probado en otra.

---

## 0. Qué prueban los logs del 09/09, y qué no

| Lo que se creía | Lo que dicen los logs | Cómo se sabe |
|---|---|---|
| Sofía no estaba actualizada ("manda 6 en vez de 20") | **Sí estaba.** Dejó borradores con `motivo: "ya_compro"`, y esa rama del prompt nace en `4decc8c` | `git show 4decc8c~1:agente/prompts/prompt-borradores.txt` no menciona `ya_compro` |
| El volumen lo pone el agente | Lo pone el **backend**: `chats_por_tanda` (8) y `tope_diario_borradores` (20). Sofía hizo 8+9+3 = 20 exacto | `pase_unico._presupuesto`, `configuracion.POR_DEFECTO` |
| Las Macs fallaron redactando | Fallaron **antes de abrir un solo chat**: `registrados: 0, salteados: 0, repetidos: 0` en las seis tandas, ~15 s por intento | Un `claude -p` real tarda minutos; el reporte volvió sin chats |

Las tres causas posibles de ese fallo temprano, todas de máquina y ninguna del proyecto:

1. **Sin `AGENTE_DEVICE_ID`** — `jobs/borradores.py:282` devuelve `ERROR_INESPERADO` al instante.
2. **Chrome cerrado, con otro perfil, o no encontrado** — `ejecutor.py:103` corta antes de pagarle
   al modelo (instantáneo, o 20 s si Chrome no arranca).
3. **Agente viejo** que no conoce el job (`bucle._no_sabe_hacer_nada`), instantáneo.

El motivo exacto está guardado en `jobs.detalle.motivo` y en `jobs.stderr` (`cola.py:461`), pero
**el panel no lo muestra** y el log del backend imprime sólo el código. Eso también se arregla acá.

---

## 1. Lo que hay hoy, y dónde se rompe

| Pieza | Qué hace hoy | Dónde se rompe |
|---|---|---|
| `agente/instalador/instalar.sh` (409 líneas) | Instala todo con un comando. Idempotente: "correrlo de nuevo es la forma de actualizar" | **Lo corre una persona, máquina por máquina.** Nada lo dispara solo |
| `instalar.sh:138` | `git -C "$REPO" pull --ff-only 2>/dev/null` con `|| true` | En una Mac con el repo clonado —rama distinta, cambios locales, credencial vencida— el update es un **no-op silencioso**: imprime "se usa como está" y sigue instalando código viejo |
| `instalar.sh:150` | Baja `refs/heads/main.tar.gz` y lo extrae sobre el árbol | **Nunca borra** un archivo que arriba se eliminó o renombró, y no deja constancia de qué commit quedó |
| `agente/agente/__init__.py:8` | `__version__ = "0.1.0"`, fijo a mano | El `version` que viaja en `agente_registrado` **no dice nada**. Es lo que hizo que esta investigación empiece a ciegas |
| `deviceId` | Se resuelve mientras instala (`perfiles.recomendar`) | Si la extensión no se usó todavía, queda vacío y hay que **volver a correr el instalador** después de abrirla a mano. Es el acoplamiento que se pide romper |
| Windows | `instalar.sh:36` corta con "Este instalador es para macOS" | La máquina de Sofía se armó a mano. **Funciona, y nadie la puede actualizar** sin repetir ese trabajo a mano |
| Autoarranque | Dos LaunchAgents (`com.centonara.agente` con `KeepAlive`, y `com.centonara.chrome`) | Correcto y ya funciona. **Falta el tercero**, el que actualiza |
| Alertas | `alertas.revisar` mira máquinas caídas, selectores y canario | No mira **versiones viejas** ni **jobs que fallan siempre**. Dos de tres máquinas en cero no encendieron nada |

Lo bueno: el agente en Python **ya es multiplataforma**. `perfiles.py`, `navegador.py`,
`conexion.py` y `permiso_mcp.py` tienen sus ramas `win32`, y `diagnostico._permisos_macos`
devuelve `NO_APLICA` fuera de macOS. Windows no es reescribir el agente: es escribir su
instalador y su arranque.

---

## 2. Cómo queda

```
  PANEL                      BACKEND                        MÁQUINA (Mac o Windows)
  ┌──────────────┐   fija    ┌───────────────────────┐      ┌────────────────────────────┐
  │ versión      │──────────>│ version_agente_       │      │ actualizador               │
  │ esperada     │   sha     │   esperada  (config)  │<─────│  1. ¿qué sha me toca?      │
  │              │           │                       │      │  2. ¿ya lo tengo? -> fin   │
  │ mac-lautaro  │           │ GET /api/agente/      │      │  3. bajar ESE sha          │
  │  7912e13 ok  │<──────────│     version-esperada  │      │  4. sync + reiniciar       │
  │ mac-thomas   │  compara  │                       │      │  5. ¿volvió? no -> rollback│
  │  4decc8c ✗   │           │ POST /api/agente/     │<─────│                            │
  └──────────────┘           │      registrar        │ sha  │ agente (KeepAlive)         │
                             └───────────────────────┘      └────────────────────────────┘
```

Cinco propiedades, y ninguna es opcional:

1. **El actualizador es un proceso aparte del agente.** Si fuera parte del agente, una versión
   que no arranca se lleva puesto al que tenía que arreglarla. Aparte, es chico, cambia casi
   nunca, y sigue funcionando cuando el agente está roto.
2. **La versión la fija el panel** (D45). La máquina no decide: pregunta. Eso da rollback y
   despliegue por máquina sin tocar ninguna Mac. **Si el backend no contesta, no se actualiza**
   —seguir con lo que hay es siempre mejor que saltar a algo que nadie pidió.
3. **Nada interactivo.** Ni una pregunta, ni una contraseña. Todo lo que hoy pregunta el
   instalador (identificador, token) ya está en el `.env` y se conserva.
4. **Rollback automático.** Si después de actualizar el agente no vuelve a registrarse, el
   actualizador restaura el árbol anterior y lo levanta. Una máquina en la casa de un vendedor no
   se puede quedar rota esperando a que alguien la mire.
5. **Barato cuando está al día.** Compara sha y sale en un segundo. Corre al iniciar sesión y cada
   hora; el 99 % de las veces no hace nada.

---

## 3. Decisiones que introduce

- **D45 — La versión del agente la fija el panel.** El backend guarda `version_agente_esperada`
  (un sha corto, o vacío = "lo último de `main`"). El actualizador instala **ese** sha, no lo que
  esté en `main` en ese instante. Motivo: un commit malo no se propaga solo a las máquinas del
  cliente, y el rollback es un campo del panel en vez de una visita a tres casas.
- **D46 — El actualizador es un servicio propio, con rollback.** Tercer LaunchAgent en Mac, tarea
  programada en Windows. Vive **fuera** del árbol que reemplaza (`~/.centonara/bin/`), porque un
  script no puede sobrescribirse a sí mismo mientras corre.
- **D47 — El `deviceId` se resuelve en caliente.** Deja de ser un requisito de instalación: si
  falta, el agente lo busca al arrancar y otra vez cuando llega un job de borradores, y lo
  persiste cuando lo encuentra. Instalar y actualizar dejan de depender de que alguien haya
  abierto la extensión.
- **D48 — Windows vuelve al parque, y convive con macOS.** Corrige el alcance de
  [D16](06-DECISIONES.md) ("el parque es macOS"): hay una máquina Windows en producción y
  funcionando. Lo específico del sistema operativo queda en **un archivo por plataforma**, no en
  `if`s repartidos.

---

## 4. Los sprints

### Sprint 0 — Un renglón que ensucia todos los post-venta *(15 min)*

`guardrails.PLACEHOLDERS` compila con `re.IGNORECASE`, así que `\bTODO\b` matchea la palabra
castellana **"todo"** — y el post-venta que introdujo `4decc8c` dice, textual, "quedó **todo**
bien?". Cada borrador post-venta sale marcado con `G3_TEXTO_INVALIDO` sin tener nada malo.

- `backend/app/core/guardrails.py:94-101` — sacar `re.IGNORECASE`. Las tres (`XXX`, `TODO`, `TBD`)
  son convenciones en mayúscula; las llaves y los corchetes no dependen del caso.
- `backend/tests/test_guardrails.py` — un caso nuevo: `"Te falto algo o quedo todo bien?"` **pasa**,
  y `"TODO: completar con el precio"` sigue sin pasar.

**Terminado cuando:** los 6 borradores del 09/09 dejarían de tener señal, y el test lo fija.

### Sprint 1 — Saber qué corre cada máquina *(medio día)*

Sin esto no se puede verificar nada de lo que sigue.

| Archivo | Cambio |
|---|---|
| `agente/agente/version.py` *(nuevo)* | Lee `agente/VERSION` (una línea: `<sha corto> <fecha>`), y si no está devuelve `"0.1.0-dev"`. Sin red y sin git: el archivo lo escribe el actualizador |
| `agente/agente/__init__.py` | `__version__` pasa a salir de ahí |
| `backend/app/api/agente.py:65` | `Registro.version` a `max_length=64` (hoy 32, justo para un sha con fecha) |
| `backend/app/api/panel.py` `_resumir_maquina` | Agrega `version_esperada` y `actualizada: bool` |
| `backend/app/core/corridas.py` `progreso` | Las tandas fallidas viajan con `codigo` y `detalle.motivo` — **es lo que hubiera contestado la pregunta del 09/09 en un minuto** |
| `backend/app/core/alertas.py` | Dos alertas nuevas: `maquina_desactualizada` (reportó un sha distinto del esperado hace más de N horas) y `maquina_falla_siempre` (sus últimos 3 jobs fallaron) |
| `frontend/` | La tarjeta de máquina muestra el sha y un punto si está atrasada; la tarjeta de corrida muestra el motivo del fallo |

**Terminado cuando:** el panel dice, sin entrar a Mongo, qué versión tiene cada máquina y por qué
falló su última tanda.

### Sprint 2 — El actualizador, en Mac *(1 día)*

| Archivo | Qué es |
|---|---|
| `backend/app/core/configuracion.py` | Campo `version_agente_esperada: ""` (vacío = lo último de `main`) |
| `backend/app/api/agente.py` | `GET /api/agente/version-esperada` → `{"sha": "...", "ref": "main"}`. Autenticado con el token de la máquina, el que ya tiene. Resuelve `main` → sha contra la API de GitHub y **cachea** el resultado unos minutos: veinte máquinas preguntando cada hora no pueden ser veinte llamadas a GitHub |
| `backend/app/api/panel.py` | `PATCH /api/panel/configuracion` ya valida contra `POR_DEFECTO`, así que el campo se edita solo. Se agrega al formulario |
| `agente/instalador/actualizar.sh` *(nuevo, chico)* | Los 6 pasos de abajo |
| `agente/instalador/instalar-mac.sh` | Escribe el tercer LaunchAgent, `com.centonara.actualizador`: `RunAtLoad` + `StartInterval 3600` + `ThrottleInterval`. Y copia `actualizar.sh` a `~/.centonara/bin/` |
| `agente/instalador/instalar.sh` | Deja de ser el actualizador: sigue sirviendo para instalar de cero, y al final delega el update en `actualizar.sh` |

Los seis pasos de `actualizar.sh`, en orden, cada uno con su salida temprana:

1. **Preguntar.** `GET /api/agente/version-esperada` con el token del `.env`. Sin respuesta → sale
   0 y no toca nada (propiedad 2).
2. **Comparar.** Si el sha es el de `agente/VERSION` → sale 0. Este es el camino normal.
3. **Bajar.** `archive/<sha>.tar.gz` a un temporal. Un sha exacto, no una rama: lo que se verifica
   es lo que se instala. El repositorio es público, así que no hace falta credencial.
4. **Guardar y aplicar.** El árbol actual se copia a `~/.centonara/respaldo/<sha_anterior>/`, y el
   nuevo se sincroniza con `rsync -a --delete --exclude .env --exclude .venv --exclude .git`.
   El `--delete` es la diferencia con hoy: los archivos borrados arriba desaparecen abajo.
   ⚠️ El navegador de envío vive en `~/Library/Application Support/Centonara/Chrome`, **fuera** del
   repo: actualizar no lo toca y no hay que volver a escanear ningún QR.
5. **Sincronizar y reiniciar.** `uv sync`, escribir `agente/VERSION`, y
   `launchctl kickstart -k gui/$uid/com.centonara.agente`.
6. **Comprobar, o volver atrás.** Espera hasta 90 s a que el agente vuelva a registrarse con el
   sha nuevo (se mira el log del agente, no el backend). Si no vuelve: restaura el respaldo,
   `uv sync`, reinicia, y deja el porqué en `~/Library/Logs/centonara/actualizador.log`. La
   próxima corrida la toma con la versión vieja, que es la que funcionaba.

Tests (`agente/tests/test_actualizador.py`, con un servidor y un tarball falsos): al día no hace
nada · sha nuevo actualiza y reinicia · backend caído no toca nada · agente que no vuelve a
levantar dispara el rollback · un archivo borrado arriba desaparece abajo · el `.env` sobrevive.

**Terminado cuando:** en una Mac de prueba, pinear un sha viejo en el panel la hace bajar sola en
menos de una hora, y pinear uno roto la deja andando con el anterior.

### Sprint 3 — El `deviceId` deja de ser un requisito *(2 h)*

| Archivo | Cambio |
|---|---|
| `agente/agente/perfiles.py` | `resolver_device_id()`: lo busca en el `.env`, y si no está, en los logs de la extensión (ya lo hace `_device_id_de`) |
| `agente/agente/main.py` | Al arrancar, si viene vacío, lo resuelve y lo **persiste** en `~/.centonara/estado.json` (no en el `.env`, que lo reescribe el instalador) |
| `agente/agente/jobs/ejecutor.py` | `device_id` pasa a ser un *callable*: se resuelve **cuando llega el job**, no cuando arrancó el proceso. Es el cambio que hubiera salvado a las dos Macs del 09/09 |
| `agente/agente/diagnostico.py` | El chequeo `device_id` usa el mismo resolvedor, así el panel y el job nunca discrepan |

**Terminado cuando:** una máquina instalada sin haber abierto nunca la extensión se pone en verde
sola la primera vez que alguien la usa, sin que nadie vuelva a correr el instalador.

### Sprint 4 — Windows, sin tocar la que funciona *(1–2 días)*

**Regla del sprint: la máquina de Sofía no se toca hasta el final, y lo único que se le agrega es
el actualizador.** Su instalación a mano funciona; reinstalarla no está en el alcance.

| Archivo | Qué es |
|---|---|
| `agente/instalador/actualizar.ps1` *(nuevo)* | Los mismos 6 pasos. `robocopy /MIR` excluyendo `.venv`, `.git` y `.env` en lugar de rsync; `Stop-ScheduledTask` + `Start-ScheduledTask` en lugar de `launchctl kickstart` |
| `agente/instalador/instalar.ps1` *(nuevo)* | El equivalente de `instalar.sh`: instala `uv` y Claude Code con sus instaladores de Windows, comprueba la sesión con un `claude -p`, baja el proyecto, escribe el `.env` con los datos que ya resuelve `perfiles.py`, y registra dos tareas programadas (agente al iniciar sesión con reintento, y actualizador cada hora) |
| `agente/agente/diagnostico.py` | Dos chequeos que hoy asumen macOS quedan explícitos en Windows: el de la sesión de Claude (Llavero vs `%USERPROFILE%\.claude`) y el de Chrome |
| `docs/SOP-instalar-windows.md` *(nuevo)* | El paso a paso, hermano del de Mac |

Orden concreto: primero `actualizar.ps1` probado en una máquina Windows **de prueba**; recién
cuando dé dos actualizaciones limpias seguidas, se le registra la tarea a la de Sofía.
`instalar.ps1` va después: sirve para la próxima máquina, no para arreglar la que anda.

⚠️ Lo que nadie verificó nunca en Windows: el navegador de envío (Playwright con carpeta
dedicada) y el permiso de sitio de la extensión. Sofía deja borradores, que es el circuito que no
los usa. Antes de prometer envíos desde Windows hay que correr `--vincular` y
`--verificar-selectores` ahí.

### Sprint 5 — El post-venta, listo y apagado *(2 h)*

Se deja preparado y **no cambia lo que sale hoy**, como se pidió.

| Archivo | Cambio |
|---|---|
| `backend/app/core/configuracion.py` | `dias_veto_ya_compro`: 180 → **45**. Sigue siendo la misma perilla del panel; deja de ser medio año de silencio por una compra |
| `backend/app/core/configuracion.py` | Campo nuevo `post_venta_ofrecer: ""` — **vacío de fábrica, y vacío no cambia nada**. Cuando el dueño escriba ahí qué ofrecer, viaja al prompt |
| `agente/agente/jobs/borradores.py` `POST_VENTA_ACTIVO` | Un bloque más: si `post_venta_ofrecer` trae texto, se pregunta cómo le fue **y** se ofrece eso en la misma línea. Vacío, el prompt queda igual que hoy |
| `backend/app/core/mensajes.py` | `crear_borrador` guarda el `motivo`, para que el panel pueda decir "este es un post-venta" en vez de mostrarlo como un seguimiento cualquiera |

**Terminado cuando:** con la configuración de fábrica, el prompt renderizado es **idéntico** al de
hoy (un test lo fija), y poner una frase en `post_venta_ofrecer` la hace aparecer.

---

## 5. Lo que este plan NO toca

- **La máquina de Sofía**, hasta el Sprint 4 y sólo para agregarle el actualizador.
- **Los LaunchAgents que ya funcionan.** El del agente y el de Chrome quedan como están; se suma
  uno, no se reescriben los dos.
- **El circuito de envío.** Nada de esto pasa cerca de un mensaje que sale.
- **`instalar.sh` como instalación de cero.** Sigue siendo el comando del SOP; lo que pierde es el
  rol de actualizador, que hacía mal.
- **El `.env`, el token y el navegador vinculado.** Actualizar no vuelve a pedir nada de eso.

---

## 6. Cómo se verifica que funcionó

1. **Antes de empezar:** en el panel, las tres máquinas muestran `0.1.0` y no se puede saber cuál
   está atrasada. Ése es el punto de partida.
2. **Después del Sprint 1:** las tres muestran un sha, y las dos Macs muestran el motivo real por
   el que fallaron sus tandas del 09/09.
3. **Después del Sprint 2:** pinear en el panel el sha anterior (`4decc8c`) hace que una Mac de
   prueba baje sola a esa versión y lo reporte. Volver a `main` la trae de vuelta. Ninguna de las
   dos veces alguien tocó la Mac.
4. **La prueba que importa:** apagar la Mac, pushear un commit, prenderla. A los pocos minutos el
   panel muestra el sha nuevo.
5. **La prueba del rollback:** pinear un commit que no arranca. La máquina queda en la versión
   anterior, tomando trabajo, y el panel lo dice.

---

## 7. Riesgos, y qué los contiene

| Riesgo | Qué lo contiene |
|---|---|
| Un commit malo llega solo a las tres máquinas | D45: la versión la fija el panel, no `main`. Y el rollback del paso 6 |
| El actualizador se rompe a sí mismo | Vive fuera del árbol que reemplaza (`~/.centonara/bin/`), y el cuerpo va dentro de una función, como ya hace `instalar.sh` |
| Actualizar en medio de una tanda | El agente reporta el job antes de morir (`bucle._hacer` reporta **siempre**), y un job tomado que nadie reporta lo recupera el barrido de `mantenimiento`. Igual: el reinicio espera a que no haya job tomado, con un techo de 5 min |
| `rsync --delete` se lleva algo que no debía | Las exclusiones son explícitas (`.env`, `.venv`, `.git`) y hay respaldo del árbol anterior. El test del sprint cubre el caso |
| Veinte máquinas preguntando a GitHub | El sha lo resuelve el **backend**, con caché. Las máquinas hablan sólo con el backend |
| Windows rompe lo que funciona | Nada de Windows toca la máquina de Sofía hasta que el actualizador dé dos vueltas limpias en otra |

---

## 8. Orden y esfuerzo

| Sprint | Qué desbloquea | Esfuerzo |
|---|---|---|
| 0 — el renglón de G3 | Deja de ensuciar el panel hoy mismo | 15 min |
| 1 — visibilidad | **Todo lo demás**: sin esto no se verifica nada | ½ día |
| 2 — actualizador Mac | Que las dos Macs se pongan al día solas, para siempre | 1 día |
| 3 — `deviceId` en caliente | Que no haya que reinstalar por un dato que el agente puede buscar | 2 h |
| 4 — Windows | Que la máquina de Sofía también se actualice sola | 1–2 días |
| 5 — post-venta | Preparado y apagado | 2 h |

Los sprints 0 y 1 se pueden hacer y desplegar hoy: no tocan ninguna máquina.
