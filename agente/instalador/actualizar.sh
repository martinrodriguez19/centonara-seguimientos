#!/usr/bin/env bash
#
# Actualiza el agente en esta Mac al commit que fija el panel. Un comando:
#
#     bash ~/centonara-seguimientos/agente/instalador/actualizar.sh
#
# No es más que un atajo a `actualizar.py`, que es el que hace el trabajo y el
# que corre solo al iniciar sesión y cada hora (`com.centonara.actualizador`).
# Correrlo a mano sirve para no esperar la hora, y para ver qué dice.
#
# Se corre la copia de `~/.centonara/bin/` si existe: es la que usa el sistema,
# y un script no puede pisarse a sí mismo mientras corre.

set -Eeuo pipefail

REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
COPIA="$HOME/.centonara/bin/actualizar.py"
PYTHON="$REPO/agente/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if [ -f "$COPIA" ]; then
  exec "$PYTHON" "$COPIA" --repo "$REPO" "$@"
fi
exec "$PYTHON" "$REPO/agente/instalador/actualizar.py" --repo "$REPO" "$@"
