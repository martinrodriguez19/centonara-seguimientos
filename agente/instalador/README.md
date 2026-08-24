# instalador

- **`instalar.sh`** — el de un solo comando: instala herramientas, baja el
  proyecto, arma el `.env` (pregunta sólo identificador y token), configura el
  arranque automático y arranca todo. Idempotente: correrlo de nuevo actualiza.
  Es el que usa el SOP (`docs/SOP-instalar-mac.md`).
- **`instalar-mac.sh`** — la pieza que escribe los dos LaunchAgents, pone el
  permiso del modo headless y corre el diagnóstico. `instalar.sh` lo llama con
  `RESUMEN=no`; también se puede correr solo, desde un repositorio clonado.
