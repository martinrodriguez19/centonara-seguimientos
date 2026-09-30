# Plan — Auditoría de instalación: comandos que funcionen en Mac nueva, Mac vieja y Windows, y reinstalar desde cero

> **El pedido.** Varias máquinas fallaron y siguen fallando. Los comandos de Windows de la
> documentación no anduvieron tal cual (notas de campo del 25/09), la corrida de las 17 del 29/09
> quedó "en curso" 21 horas, dos Macs fallaron toda la corrida con *"OAuth session expired"*, y no
> hay forma de "matar el agente y traer uno nuevo desde cero". Se pide: una auditoría del
> proyecto, un plan de correcciones, comandos que funcionen en **Mac nueva, Mac vieja (la instalada
> con `git clone`, o con macOS anterior a 13) y Windows**, y la documentación de instalar y
> reinstalar **adentro del panel**.
>
> Fecha: 30/09/2026. Base: `main` en `f558d7e`. Estado: **sprints 0 a 2 implementados el mismo
> día; el sprint 3 (cambios en el agente y el backend) espera aprobación** — ver §5.
>
> **La regla que ordena el plan:** una máquina que falla tiene que poder volver a cero con dos
> comandos —uno que desinstala, el mismo instalador de siempre— y el instalador tiene que **decir la
> verdad al final**: "el agente dio señal de vida" o "no la dio, y esto es lo que falta".

---

## 0. Qué se encontró, verificado en el código

### 0.1 Los errores del log del 29/09–30/09

| Lo que dice el log | Qué es | Dónde está la causa |
|---|---|---|
| `ERROR_INESPERADO: claude devolvió 1 y dijo: … "Failed to authenticate: OAuth session expired"` (mac-lautaro, mac-thomas) | La sesión de Claude Code de esa Mac venció. El agente sólo reconoce el texto `"OAuth access token has expired"` o `api_error_status: 401`; **este texto no calza**, así que cae en el mensaje genérico. Se reintenta 3 veces (30 s y 60 s de espera), y en `extension_con_respaldo` se encola un `LISTAR` de respaldo que falla igual: 6 intentos para nada | `agente/agente/jobs/claude_code.py:180-214`; `backend/app/core/cola.py:37,144-154,489` |
| Ningún chequeo lo anticipó | **Ningún chequeo del diagnóstico prueba la sesión de Claude.** `chrome` sólo corre `claude --version`, que no necesita sesión. La única prueba real está en el instalador, y corre una vez | `agente/agente/diagnostico.py:228-251,353-364`; `instalar.sh:108-141` |
| Ninguna alerta lo dijo a tiempo | `maquina_falla_siempre` cuenta **jobs** terminados fallidos (3), no intentos. Una corrida deja 1 o 2 jobs fallidos: la alerta tarda 2 o 3 corridas —días— en aparecer | `backend/app/core/alertas.py:330-378` |
| La corrida quedó "en curso" de 17:00 a 13:57 del día siguiente | **Una corrida no tiene timeout.** Un job `pendiente` de una máquina apagada (windows-julian, windows-ignacio) la mantiene viva hasta que alguien la cancela. La programada del día siguiente **se saltea y ese día se pierde** (`corrida_en_curso`), aunque se cancele la vieja dentro de la gracia | `backend/app/core/corridas.py:204-238`; `programacion.py:18-22,129-130`; `main.py:33-67` |
| `SESION_CAIDA` (windows-ignacio), después `dejados: 8` | La sesión de WhatsApp venció y se re-vinculó. Se recuperó sola. No es un problema del instalador | `RUNBOOK-revincular-whatsapp.md` |
| `respaldo_frenado_por_texto_enviado` (windows-julian) | La tanda reportó `texto_enviado`: **un texto salió enviado en vez de quedar como borrador**. No se reintenta ni se activa el respaldo, a propósito. Hay que abrir ese chat en el WhatsApp del vendedor y ver qué salió. No hay alerta dedicada: sólo este warning | `backend/app/core/pase_unico.py:985-991`; `agente/jobs/borradores.py:56-74` |
| `ingreso_rechazado` | Contraseña del panel equivocada. Nada que hacer | — |

### 0.2 Los instaladores

| # | Defecto | Dónde | Efecto |
|---|---|---|---|
| a | **BOM (`EF BB BF`) al principio de `instalar.ps1` y `actualizar.ps1`.** Con `irm … \| iex` y con `[scriptblock]::Create((irm …))` el BOM queda pegado adelante del primer comentario, `param()` deja de ser la primera instrucción y falla en la línea 37 | los dos `.ps1`, desde `be7c524` | **Ninguno de los comandos de Windows de la documentación funcionaba.** Lo que funcionó en campo: bajar a archivo y correr con `-File` |
| b | `exit 1` adentro de `iex` **cierra la ventana** de PowerShell | `instalar.ps1` (6 lugares) | Se pierde el mensaje que dice qué arreglar, justo en el caso "correrlo dos veces" |
| c | **Sin desinstalación** en ningún sistema | — | No hay forma de "empezar de cero" en una máquina rota |
| d | **La verificación final de Mac no comprueba que el agente esté vivo**: mira que las tres etiquetas estén en `launchctl list` y que exista `agente/VERSION`. Un agente que se cae en bucle pasa. Y dice "INSTALACIÓN COMPLETA" con `exit 0` aunque haya dicho NO QUEDÓ AL DÍA | `instalar.sh:447-476,500` | Se cierra la Terminal creyendo que quedó bien |
| e | **Windows no verifica nada** al final | `instalar.ps1:300-313` | Ídem |
| f | En Windows, cuando llega una versión nueva el agente **se relanza desacoplado** de la tarea. `Stop-ScheduledTask` ya no lo detiene; volver a correr el instalador o `Start-ScheduledTask` levanta **un segundo agente con el mismo token** | `agente/agente/reinicio.py:107-137`; `instalar.ps1:302` | Dos agentes tomando trabajo; "matar el agente" no lo mata |
| g | En Windows, un `.git` viejo se usa "como está" (no aplica D53) y si el proyecto ya existe **no se baja nada** | `instalar.ps1:154-157` | Una PC instalada a mano puede quedar con código viejo hasta que el actualizador corra |
| h | `[8/8]` de Mac importa `agente.adaptadores.conexion` **sin `cd`** al directorio del agente: el import falla siempre, así que **siempre vuelve a ofrecer vincular** aunque ya esté | `instalar.sh:411-419` | Confunde: parece que la vinculación no quedó |
| i | Si una Mac vieja corre `bash ~/centonara-seguimientos/agente/instalador/instalar.sh` (la ruta que el propio script recomienda en el caso "repositorio privado"), `DESARROLLO=si` y **se saltea el arreglo D53** | `instalar.sh:56-61,147-155` | Vuelve a instalar el `instalar-mac.sh` viejo y termina en NO QUEDÓ AL DÍA |
| j | **No revisa la versión de macOS.** En macOS < 13 el instalador de Claude Code aborta con error 134 y `set -e` corta sin explicar | `instalar.sh:79-91` | La persona no sabe que existe el apartado "macOS viejo" |
| k | **El `.env` se regenera con sólo las claves fijas**: se pierde cualquier otra (`AGENTE_NAVEGADOR_DIR`, `AGENTE_REPO_GITHUB`…) | `instalar.sh:330-340`; `instalar.ps1:253-266` | Una máquina configurada a mano se resetea al reinstalar |
| l | **Encoding en Windows:** `actualizar.py` no reconfigura stdout (bajo la tarea, cp1252 → `UnicodeEncodeError` en el `print` final, que se registra como "ERROR inesperado" con la actualización ya hecha); y `*>>` escribe los logs en UTF-16 mientras el agente relanzado escribe UTF-8 en el mismo archivo | `actualizar.py:564`; `instalar.ps1:91,291` | Logs mezclados e ilegibles; "falló" una actualización que salió bien |
| m | Hay que correr el instalador **dos veces** en una máquina nueva (login de Claude) | `instalar.sh:133-142`; `instalar.ps1:140-149` | Documentado ahora; no es una falla |
| n | `actualizar.sh` cae al `python3` del sistema si no hay venv; en Macs viejas es 3.9 y `actualizar.py` necesita 3.12 | `actualizar.sh:19` | Sólo afecta a una Mac sin venv |
| o | La página de Comandos del panel **no tiene Windows**, dice "los dos servicios" (son tres) y "correrlo de nuevo es la forma de actualizar" (D46 dice lo contrario) | `frontend/lib/comandos.ts` | Quien está frente a la PC no tiene los comandos |
| p | `sop.html` en la raíz es del 26/08: no conoce el actualizador ni Windows | `sop.html` | Alguien lo sigue y hace lo viejo |

### 0.3 Lo que anda bien y no se toca

El actualizador (D45–D48): decide versión contra el backend, hace respaldo, sincroniza, prueba
de humo, espera la vuelta del agente y deshace si no vuelve. La `vigía` de la sesión del
navegador de envío. El `--diagnostico`. El `--vincular`. La lógica de perfiles y deviceId.

---

## 1. Sprint 0 — Instaladores que dicen la verdad *(implementado)*

**Windows (`instalar.ps1`, `actualizar.ps1`)**
- El comando oficial pasa a ser **bajar y correr con `-File`**: permite flags (`-SoloActualizador`,
  `-Repo`), un `exit` no cierra la ventana, y el BOM no le molesta. `irm | iex` deja de estar en
  la documentación, y un test en `agente/tests/test_instalador.py` falla si vuelve a aparecer.
- **El BOM se queda, a propósito.** La primera idea era sacarlo; al revisar, no: Windows PowerShell
  5.1 lee un `.ps1` sin BOM como ANSI y todos los acentos de los mensajes salen rotos con `-File`.
  El BOM sólo rompía `iex`. El mismo test vigila que los dos `.ps1` lo conserven.
- `[3/8]`: un `.git` en `~\centonara-seguimientos` es una instalación vieja (D53, igual que Mac):
  se aparta a `~\.centonara\git-viejo-<fecha>` y se baja `main`. Y se baja **siempre**, encima de
  lo que haya: el `.env` y el `.venv` no están en el zip, así que se conservan.
- `[7/8]`: antes de arrancar, **`DetenerAgente`** para la tarea **y** mata todo `python` con
  `agente.main` en la línea de comandos (los relanzados desacoplados). Sin esto había dos agentes.
- **Verificación final**: espera hasta 90 s la señal de vida en `~\.centonara\estado\vivo.json`
  (`cuando` de menos de 120 s) y dice `QUEDÓ AL DÍA: <sha>` o `NO QUEDÓ AL DÍA: <qué falta>`, con
  `exit 1` en ese caso.
- El `.env` conserva las claves que no son del instalador.
- Encoding: las tareas fijan `[Console]::OutputEncoding` y `Out-File:Encoding` en UTF-8;
  `actualizar.py` reconfigura stdout a UTF-8.

**Mac (`instalar.sh`)**
- `DESARROLLO=si` sólo si el script corre desde un repositorio **que no es**
  `~/centonara-seguimientos`: la Mac de un vendedor recibe el arreglo D53 aunque se corra por ruta.
- Antes de instalar Claude Code, **comprueba macOS ≥ 13**; con menos, dice que hay que seguir el
  apartado "macOS anterior a 13" del panel y se detiene. Si `claude` ya está (el camino de la Mac
  vieja), no revisa nada.
- `[8/8]` hace `cd` al agente antes de importar: "ya estaba vinculado" vuelve a funcionar.
- El `.env` conserva las claves que no son del instalador.
- **Verificación final** con `vivo.json` (hasta 90 s), y termina en `INSTALACIÓN INCOMPLETA` con
  `exit 1` si algo falta. `INSTALACIÓN COMPLETA` sólo se imprime cuando es verdad.

**Desinstalar (nuevo: `desinstalar.sh`, `desinstalar.ps1`)**
- Para, descarga los servicios/tareas, mata los procesos (agente, relanzados, navegador dedicado),
  borra `~/centonara-seguimientos`, `~/.centonara` y los logs. Imprime qué borró y el identificador
  de la máquina (no el token).
- **Conserva** la sesión de WhatsApp del navegador de envío y el login de Claude Code, salvo
  `--todo` / `-Todo`: así "reinstalar" no obliga a escanear el QR de nuevo.
- Se corre desde GitHub (no desde el repositorio, que puede estar roto). Reinstalar es: desinstalar
  + el instalador de siempre + activar en el panel.

---

## 2. Sprint 1 — La guía adentro del panel *(implementado)*

`/comandos` pasa a ser **"Instalar y reparar"**: una pestaña por computadora —**Mac**, **Mac con
macOS anterior a 13**, **Windows**— y una cuarta con lo que se hace en el panel. Cada pestaña
tiene los mismos pasos, en el mismo orden:

1. Antes de empezar (qué tener a mano, qué confirmar).
2. Preparar Chrome (con el mouse).
3. Instalar (el comando, "se pega dos veces", qué tiene que decir al final).
4. Vincular el navegador que escribe.
5. Comprobar que quedó bien (estado, señal de vida, versión, logs).
6. **Reinstalar desde cero** (cuándo conviene, qué se conserva, los dos comandos).
7. Cuando vence algo (Claude Code, WhatsApp del motor, WhatsApp del vendedor).
8. Actualizar a mano y volver atrás.
9. Si algo no anda: síntoma → qué es → qué hacer.

Los comandos siguen viviendo en `frontend/lib/comandos.ts` (ahora `guia.ts`), con el mismo
invariante: **cada comando existe tal cual en el repositorio**, y el test lo comprueba contra los
scripts (`instalar.sh`, `instalar.ps1`, `desinstalar.*`, `actualizar.*`).

---

## 3. Sprint 2 — La documentación en `docs/` *(implementado)*

- `SOP-instalar-windows.md`: el comando corregido, la sección "Reinstalar desde cero", la
  verificación final, energía (`powercfg`), y "no arrancar el agente a mano si existe la tarea".
- `SOP-instalar-mac.md`: macOS ≥ 13 antes de empezar, "se pega dos veces", reinstalar desde cero,
  los tres servicios, y las tres sesiones que vencen con su comando.
- `COMANDOS-MAQUINAS.md`: Windows con los comandos que funcionan; desinstalar en los dos sistemas.
- `agente/instalador/README.md`: los dos scripts nuevos.
- `sop.html` se borra: era del 26/08 y no conocía el actualizador ni Windows. La guía viva es la
  del panel.

---

## 4. Lo que NO cambia

- El agente en producción no cambia de comportamiento en estos tres sprints: sólo cambian los
  instaladores, el desinstalador, el `actualizar.py` (stdout en UTF-8) y la documentación. Las
  máquinas que ya andan no se enteran hasta que alguien corra el instalador.
- Abrir la lista de destinos sigue pidiendo `ABRIR`; empezar de cero, `BORRAR`.

---

## 5. Sprint 3 — Que el sistema avise antes de fallar *(pendiente de aprobación: toca el agente y el backend)*

Son cambios chicos, con test, pero cambian lo que hacen el agente y el backend en producción.

| # | Cambio | Dónde | Por qué |
|---|---|---|---|
| 3.1 | Reconocer **todos** los textos de sesión vencida de Claude Code (`OAuth session expired`, `Failed to authenticate`, `Please run /login`, `api_error_status: 401`) y devolver un código propio, **`CLAUDE_SESION_VENCIDA`, que no se reintenta** | `agente/jobs/claude_code.py`; `backend/core/cola.py` | Hoy se reintenta 3 veces (6 con respaldo) algo que no se arregla solo, y el motivo queda enterrado en 300 caracteres de JSON |
| 3.2 | **Alerta urgente propia**: "Venció la sesión de Claude Code de *Lautaro*. En esa Mac: `claude`, iniciar sesión, `/exit`". Con `maquina` para el filtro del panel | `backend/core/alertas.py` | Con el código propio, la alerta sale al primer fallo, no al tercer job |
| 3.3 | **Sonda diaria de la sesión de Claude** en la vigía: al arrancar y una vez por día, una hora antes de la corrida programada (o a las 16 si no hay), `claude -p` con un prompt de una palabra. Si falla, el chequeo `claude_sesion` pasa a `falla` y el panel lo muestra **antes** de la corrida | `agente/vigia_sesion.py`; `diagnostico.py` | Cuesta centavos por día y evita perder la corrida entera. La expiración no se puede leer del archivo de credenciales: el refresh token puede vencer sin que el `expiresAt` lo diga |
| 3.4 | **Una corrida vence**: al final de la ventana horaria del día (o a las 4 h si la ventana es 24/7) los jobs `pendiente`/`tomado` pasan a `fallido/VENCIDO` y la corrida termina, con evento en el historial. Así la programada del día siguiente no se saltea | `backend/core/mantenimiento` (el watchdog de `main.py`) | La del 29/09 estuvo 21 h en curso por dos PC apagadas |
| 3.5 | `maquina_falla_siempre` cuenta **intentos** además de jobs: 3 intentos fallidos seguidos con el mismo código ya alcanzan | `backend/core/alertas.py` | Hoy tarda días |
| 3.6 | En Windows, cuando el agente se relanza por versión nueva, **no se desacopla**: sale con 75 y deja que la tarea lo levante al minuto (como ya hace si no puede lanzarlo). La tarea vuelve a ser la dueña del proceso | `agente/reinicio.py` | Es la causa de los agentes duplicados y de que `Stop-ScheduledTask` no frene nada |
| 3.7 | Alerta `texto_enviado`: "En *Julián* salió un texto enviado en vez de quedar como borrador. Abrí ese chat en su WhatsApp" | `backend/core/alertas.py` | Hoy es un warning en el log del servidor que nadie ve |

**Recomendación:** hacer 3.1, 3.2 y 3.3 juntos (es un solo problema: la sesión de Claude) y 3.4
solo; 3.5–3.7 después. Ninguno cambia lo que el agente escribe en un chat.

---

## 6. Cómo se prueba

- `agente/tests/test_instalador.py`: sin BOM en ningún `.ps1`/`.sh`, `bash -n` de los `.sh`,
  y que los comandos de `frontend/lib/guia.ts` y de los SOP apunten a scripts que existen.
- `frontend/tests/comandos.test.ts`: los invariantes de siempre (ids únicos, sin saltos de línea,
  huecos declarados) sobre la guía nueva, más: cada sistema tiene los nueve pasos, y todo comando
  de Windows va con `-File` (nunca `| iex`).
- A mano, en una máquina real de cada tipo: desinstalar → instalar → "QUEDÓ AL DÍA" → activar →
  corrida de diagnóstico. **Esto no se puede probar desde acá**: queda en
  `PENDIENTE-CON-MAQUINA.md`.
