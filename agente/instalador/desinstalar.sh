#!/usr/bin/env bash
#
# Deja la Mac como si el agente nunca se hubiera instalado. Un comando:
#
#   curl -fsSL --http1.1 https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/desinstalar.sh | bash
#
# (ese desinstalar.sh de la raíz es un atajo que baja y corre éste; las
# opciones se pasan con `| bash -s -- --todo`)
#
# Es la mitad de "reinstalar desde cero": esto, y después el instalador de
# siempre. Existe porque una máquina que falla y sigue fallando no se arregla
# volviendo a correr el instalador encima —que conserva el .env, el entorno y
# lo que sea que esté roto—, y no había forma de matar el agente y traer uno
# nuevo. Se baja de GitHub y no del repositorio de la Mac a propósito: el
# repositorio puede ser justo lo que está roto.
#
# Qué borra:
#   - Los tres servicios de arranque (agente, Chrome, actualizador) y sus plists
#   - Los procesos: el agente, los que quedaron de versiones anteriores, y el
#     navegador dedicado del motor de envío si estaba abierto
#   - ~/centonara-seguimientos entero (incluido el .env con el token)
#   - ~/.centonara (señal de vida, copia del actualizador, respaldos, candado)
#   - ~/Library/Logs/centonara
#
# Qué CONSERVA, salvo que se pida --todo:
#   - La sesión de WhatsApp del navegador que escribe los mensajes
#     (~/Library/Application Support/Centonara/Chrome): así reinstalar no
#     obliga a escanear el QR de nuevo
#   - El login de Claude Code, uv y claude: son de la Mac, no del agente
#   - El Chrome del vendedor: no se toca nunca
#
# Pide confirmación por teclado. Sin teclado (por ejemplo desde un script),
# hace falta --si.
#
# Después de esto, el panel va a mostrar la máquina "sin conexión" —es lo
# esperado— hasta que se vuelva a instalar. El identificador y el token se
# vuelven a pedir en la instalación: el identificador se imprime acá; el token,
# si no está anotado, se rota desde el panel (Máquinas → la máquina → ⋯ →
# Rotar token) y sale uno nuevo.

set -Eeuo pipefail

principal() {

[ "$(uname)" = "Darwin" ] || { echo "Este desinstalador es para macOS." >&2; exit 1; }

REPO="$HOME/centonara-seguimientos"
ESTADO="$HOME/.centonara"
LOGS="$HOME/Library/Logs/centonara"
SESION_ENVIO="$HOME/Library/Application Support/Centonara"
PLISTS="$HOME/Library/LaunchAgents"
TODO=no
SI=no
for arg in "$@"; do
  case "$arg" in
    --todo) TODO=si ;;
    --si) SI=si ;;
    *) echo "Opción desconocida: $arg (las que hay: --todo, --si)" >&2; exit 1 ;;
  esac
done

titulo() { printf '\n\033[1m%s\033[0m\n' "$*"; }

if : </dev/tty >/dev/null 2>&1; then TECLADO=si; else TECLADO=no; fi

# ---------------------------------------------------------------------------
titulo "Qué hay instalado"

MACHINE_ID=""
if [ -f "$REPO/.env" ]; then
  MACHINE_ID=$(sed -n 's/^AGENTE_MACHINE_ID=//p' "$REPO/.env" | head -1 | sed 's/[[:space:]]*#.*$//; s/[[:space:]]*$//')
fi
[ -n "$MACHINE_ID" ] && echo "  identificador de esta máquina en el panel: $MACHINE_ID" \
  || echo "  (no hay un .env con identificador: la instalación no llegó a ese paso)"
for etiqueta in com.centonara.agente com.centonara.chrome com.centonara.actualizador; do
  [ -f "$PLISTS/$etiqueta.plist" ] && echo "  servicio: $etiqueta"
done
[ -d "$REPO" ] && echo "  proyecto: $REPO"
[ -d "$ESTADO" ] && echo "  estado: $ESTADO"
[ -d "$LOGS" ] && echo "  logs: $LOGS"
if [ -d "$SESION_ENVIO/Chrome" ]; then
  if [ "$TODO" = si ]; then
    echo "  sesión del navegador de envío: $SESION_ENVIO/Chrome  ← se borra (--todo)"
  else
    echo "  sesión del navegador de envío: $SESION_ENVIO/Chrome  ← se conserva"
  fi
fi

# ---------------------------------------------------------------------------
titulo "Confirmar"

echo "  Se va a borrar todo lo de arriba. El Chrome del vendedor y el login de"
echo "  Claude Code no se tocan. No se puede deshacer."
if [ "$SI" = si ]; then
  echo "  (--si: sin preguntar)"
elif [ "$TECLADO" = si ]; then
  printf '  Para seguir, escribí SI en mayúsculas: ' >/dev/tty
  IFS= read -r respuesta </dev/tty
  [ "$respuesta" = "SI" ] || { echo "  Cancelado. No se borró nada."; exit 1; }
else
  echo "  No hay teclado para confirmar. Corré esto desde una Terminal común, o" >&2
  echo "  agregá --si al final del comando si estás seguro." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
titulo "[1/4] Parar los servicios"

uid=$(id -u)
for etiqueta in com.centonara.agente com.centonara.chrome com.centonara.actualizador; do
  if launchctl bootout "gui/$uid/$etiqueta" 2>/dev/null; then
    echo "  ok  descargado $etiqueta"
  fi
  if [ -f "$PLISTS/$etiqueta.plist" ]; then
    rm -f "$PLISTS/$etiqueta.plist"
    echo "  ok  borrado $PLISTS/$etiqueta.plist"
  fi
done

# ---------------------------------------------------------------------------
titulo "[2/4] Matar los procesos"
#
# El agente (y cualquiera que haya quedado de una versión anterior), el
# actualizador si estaba corriendo, y el navegador dedicado del motor de envío.
# El Chrome del vendedor no está acá: se lo reconoce por la carpeta de datos
# del navegador dedicado, que es otra.
for patron in "agente.main" "actualizar.py" "Application Support/Centonara/Chrome"; do
  if pkill -f "$patron" 2>/dev/null; then
    echo "  ok  cerrado: $patron"
  fi
done
sleep 2

# ---------------------------------------------------------------------------
titulo "[3/4] Borrar los archivos"

for carpeta in "$REPO" "$ESTADO" "$LOGS"; do
  if [ -d "$carpeta" ]; then
    rm -rf "$carpeta"
    echo "  ok  borrado $carpeta"
  fi
done
if [ "$TODO" = si ] && [ -d "$SESION_ENVIO" ]; then
  rm -rf "$SESION_ENVIO"
  echo "  ok  borrado $SESION_ENVIO (la sesión de WhatsApp del motor: hay que volver a escanear el QR)"
fi

# ---------------------------------------------------------------------------
titulo "[4/4] Comprobar"

QUEDA=""
for etiqueta in com.centonara.agente com.centonara.chrome com.centonara.actualizador; do
  launchctl list 2>/dev/null | grep -q "$etiqueta" && QUEDA="${QUEDA:+$QUEDA; }$etiqueta sigue cargado"
done
pgrep -f "agente.main" >/dev/null 2>&1 && QUEDA="${QUEDA:+$QUEDA; }hay un agente corriendo"
[ -d "$REPO" ] && QUEDA="${QUEDA:+$QUEDA; }sigue $REPO"

if [ -n "$QUEDA" ]; then
  echo "  NO QUEDÓ LIMPIA: $QUEDA" >&2
  echo "  Reiniciá la Mac y volvé a correr este mismo comando." >&2
  exit 1
fi

titulo "DESINSTALACIÓN COMPLETA"
cat <<FIN
  La Mac quedó sin el agente. En el panel va a figurar "sin conexión": es lo
  esperado hasta que se vuelva a instalar.

  Para instalar de nuevo, el comando de siempre:

    curl -fsSL --http1.1 https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/instalar.sh | bash

  Va a pedir el identificador${MACHINE_ID:+ ($MACHINE_ID)} y el token. Si el
  token no está anotado, en el panel: Máquinas → la máquina → ⋯ → Rotar token.
FIN

exit 0
}

principal "$@"
