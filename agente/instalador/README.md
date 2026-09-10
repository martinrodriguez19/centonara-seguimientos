# instalador

- **`instalar.sh`** — el de un solo comando, para Mac: instala herramientas, baja el
  proyecto, arma el `.env` (pregunta sólo identificador y token), registra los tres
  LaunchAgents y arranca todo. Idempotente: correrlo de nuevo arregla lo que falte.
  Es el que usa `docs/SOP-instalar-mac.md`.
- **`instalar.ps1`** — lo mismo para Windows, con tareas programadas en lugar de
  LaunchAgents. Con `-SoloActualizador` registra únicamente el actualizador en una PC que
  ya funciona, sin tocar nada más. Es el que usa `docs/SOP-instalar-windows.md`.
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
