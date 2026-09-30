# instalador

- **`instalar.sh`** — el de un solo comando, para Mac: instala herramientas, baja el
  proyecto, arma el `.env` (pregunta sólo identificador y token), registra los tres
  LaunchAgents y arranca todo. Idempotente: correrlo de nuevo arregla lo que falte.
  Es el que usa `docs/SOP-instalar-mac.md`.
  Al final espera la señal de vida del agente (`~/.centonara/estado/vivo.json`) y dice
  `QUEDÓ AL DÍA` o `NO QUEDÓ AL DÍA` con lo que falta, con `exit 1` en ese caso.
- **`instalar.ps1`** — lo mismo para Windows, con tareas programadas en lugar de
  LaunchAgents. Con `-SoloActualizador` registra únicamente el actualizador en una PC que
  ya funciona, sin tocar nada más. Es el que usa `docs/SOP-instalar-windows.md`. Se baja a un
  archivo y se corre con `-File`, nunca con `irm | iex` (ver la cabecera del script). Los
  `.ps1` llevan BOM a propósito: sin él, Windows PowerShell 5.1 rompe los acentos.
- **`desinstalar.sh`** / **`desinstalar.ps1`** — dejan la computadora como si el agente nunca
  se hubiera instalado: paran y borran los servicios o tareas, matan todos los procesos del
  agente (también los relanzados por una actualización), y borran el proyecto, el estado y los
  logs. Conservan la sesión de WhatsApp del navegador de envío y el login de Claude Code, salvo
  `--todo` / `-Todo`. Piden escribir `SI`. Son la primera mitad de "reinstalar desde cero"; la
  segunda es el instalador de siempre. Se corren desde GitHub, no desde el repositorio de la
  máquina, que puede ser lo que está roto (`desinstalar.sh` de la raíz es el atajo).
- **`instalar-mac.sh`** — la pieza que escribe los tres LaunchAgents (agente, Chrome,
  actualizador), pone el permiso del modo headless y corre el diagnóstico. `instalar.sh` lo
  llama con `RESUMEN=no`; también se puede correr solo, desde un repositorio clonado.
- **`actualizar.py`** — el actualizador (D45, D46). Un solo archivo, sólo biblioteca
  estándar, igual en Mac y en Windows. Pregunta al backend qué commit toca, y si es otro lo
  baja de GitHub, respalda, sincroniza (borrando lo que arriba ya no existe), hace `uv sync`,
  escribe `agente/VERSION` y espera a que el agente vuelva con esa versión; si no vuelve,
  restaura. El sistema corre la **copia** de `~/.centonara/bin/`, no ésta: un script no puede
  pisarse a sí mismo mientras corre. Se prueba en `tests/test_actualizador.py` sin red, sin
  `uv` y sin launchd.
- **`actualizar.sh`** / **`actualizar.ps1`** — atajos para correr el actualizador a mano, sin
  esperar la hora.

Actualizar **no** es volver a correr el instalador: el actualizador corre solo al iniciar
sesión y cada hora. El agente se reinicia por su cuenta cuando ve que `agente/VERSION` cambió
(`agente/reinicio.py`), entre dos jobs y nunca en el medio de uno.

`tests/test_instalador.py` vigila lo que se puede vigilar sin una máquina real: sintaxis de los
`.sh`, BOM en los `.ps1`, que ninguna guía use `irm | iex`, y que los scripts que nombra la guía
del panel existan.
