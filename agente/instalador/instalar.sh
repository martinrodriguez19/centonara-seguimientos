#!/usr/bin/env bash
#
# Instala TODO el agente en la Mac de un vendedor, con un solo comando:
#
#   curl -fsSL https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.sh | bash
#
# Es seguro correrlo las veces que haga falta: lo que ya está hecho lo saltea,
# lo que falta lo dice en castellano, y correrlo de nuevo es además la forma de
# actualizar el programa. Cuando algo corta la instalación, la respuesta es
# siempre la misma: arreglar lo que dijo y volver a correr el mismo comando.
#
# Qué hace:
#   1. Instala las herramientas que falten (uv y Claude Code). Sin npm, sin
#      Node, sin Xcode: los instaladores nativos alcanzan.
#   2. Comprueba que Claude Code tenga una sesión iniciada
#   3. Baja el proyecto a ~/centonara-seguimientos, o lo actualiza
#   4. Averigua solo el perfil de Chrome, el deviceId y la ruta de claude
#   5. Escribe el .env — sólo pregunta el identificador y el token del panel,
#      y si ya estaban, no pregunta nada
#   6. Configura el arranque automático (delegando en instalar-mac.sh)
#   7. Arranca Chrome con el puerto y el agente, y comprueba que quedaron vivos
#
# Qué NO hace, a propósito:
#   - No da el permiso de sitio de la extensión: es una puerta de
#     consentimiento y la abre una persona, en la extensión. El SOP dice cómo.
#   - No activa la máquina. Instalar no es activar: eso se decide en el panel.
#
# Todo el script vive adentro de una función que se llama al final. No es
# estilo: el paso 3 puede sobrescribir ESTE archivo mientras corre, y bash lee
# los scripts de a pedazos; con la función, ya está todo leído antes de empezar.

set -Eeuo pipefail

principal() {

[ "$(uname)" = "Darwin" ] || { echo "Este instalador es para macOS." >&2; exit 1; }

TARBALL="https://github.com/martinrodriguez19/centonara-seguimientos/archive/refs/heads/main.tar.gz"
REPO="$HOME/centonara-seguimientos"
BACKEND_POR_DEFECTO="https://backend-produccion-7yqr.onrender.com"

# uv y Claude Code se instalan ahí; que se encuentren aunque la terminal sea nueva.
export PATH="$HOME/.local/bin:$PATH"

# Si el script se está corriendo desde un repositorio ya clonado en otro lado
# (una máquina de desarrollo), se usa ese y no ~/centonara-seguimientos.
if [ -f "${BASH_SOURCE[0]:-}" ]; then
  posible=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
  [ -f "$posible/agente/instalador/instalar-mac.sh" ] && REPO="$posible"
fi

titulo() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# Leer del teclado aunque el script llegue por `curl | bash`: ahí stdin es el
# pipe del curl, y lo que escribe la persona está en /dev/tty.
if : </dev/tty >/dev/null 2>&1; then TECLADO=si; else TECLADO=no; fi
preguntar() {
  local respuesta
  printf '%s' "$1" >/dev/tty
  IFS= read -r respuesta </dev/tty
  printf '%s' "$respuesta"
}

# ---------------------------------------------------------------------------
titulo "[1/7] Las herramientas"

if command -v uv >/dev/null 2>&1; then
  echo "  ok  uv"
else
  echo "  instalando uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

if command -v claude >/dev/null 2>&1; then
  echo "  ok  claude"
else
  echo "  instalando Claude Code..."
  curl -fsSL https://claude.ai/install.sh | bash
fi
command -v claude >/dev/null 2>&1 || {
  echo "  Claude Code no quedó instalado. Cerrá esta Terminal, abrí una nueva" >&2
  echo "  y volvé a correr este instalador." >&2
  exit 1
}

# La ruta REAL, no el atajo: bajo launchd el PATH no es el de esta terminal y
# un atajo puede no resolver (problema #2 del MVP).
CLAUDE_BIN=$(command -v claude)
if [ -L "$CLAUDE_BIN" ]; then
  CLAUDE_BIN=$(readlink -f "$CLAUDE_BIN" 2>/dev/null \
    || perl -MCwd=abs_path -e 'print abs_path(shift)' "$CLAUDE_BIN")
fi
echo "  claude: $CLAUDE_BIN"

# ---------------------------------------------------------------------------
titulo "[2/7] La sesión de Claude Code"
#
# El agente corre `claude` sin nadie mirando: si la sesión no sirve, todo lo
# demás se instala bien y después nada funciona. Mejor cortarlo acá.
#
# Dos chequeos, porque fallan distinto: sin credencial en el Llavero nunca
# hubo sesión; y con credencial igual puede estar VENCIDA — el token OAuth
# caduca cada tanto, y pasó en la primera Mac con todo lo demás en verde. Lo
# segundo sólo se sabe preguntando de verdad: una llamada mínima, que tarda
# unos segundos y cuesta centavos.

sesion_ok=no
if security find-generic-password -s "Claude Code-credentials" >/dev/null 2>&1 \
   || [ -f "$HOME/.claude/.credentials.json" ]; then
  echo "  comprobando que la sesión siga viva (unos segundos)..."
  if printf 'Contestá una sola palabra: ok' | "$CLAUDE_BIN" -p >/dev/null 2>&1; then
    sesion_ok=si
    echo "  ok  sesión iniciada y viva"
  else
    echo "  Hay una sesión guardada, pero está VENCIDA: el token caduca cada tanto."
  fi
else
  echo "  Nunca se inició sesión en Claude Code en esta máquina."
fi

if [ "$sesion_ok" = no ]; then
  echo
  echo "  Cómo se arregla:"
  echo "    1. En esta Terminal, corré:  claude"
  echo "    2. Iniciá sesión (si no la ofrece, escribí /login) con la cuenta"
  echo "       de Claude de ESTA máquina"
  echo "    3. Salí escribiendo:  /exit"
  echo "    4. Volvé a correr este instalador, el mismo comando de antes"
  exit 1
fi

# ---------------------------------------------------------------------------
titulo "[3/7] El proyecto"

if [ -d "$REPO/.git" ]; then
  # Un repositorio git es de alguien que desarrolla: no se le pisa nada.
  echo "  ok  ya está clonado con git en $REPO — se usa como está"
  git -C "$REPO" pull --ff-only 2>/dev/null || true
else
  echo "  bajando la última versión a $REPO"
  mkdir -p "$REPO"
  # El tarball trae el código y nada más: el .env y el entorno de esta máquina
  # no están adentro, así que sobreescribir actualiza sin borrarlos.
  #
  # Y si no se puede bajar —repositorio privado, o sin internet— pero la
  # carpeta ya tiene el proyecto (llegó por AirDrop o USB), se sigue con esa:
  # no poder actualizar no es no poder instalar.
  if curl -fsSL "$TARBALL" | tar -xz --strip-components=1 -C "$REPO"; then
    echo "  ok  proyecto en $REPO"
  elif [ -f "$REPO/agente/pyproject.toml" ]; then
    echo "  aviso: no se pudo bajar la última versión desde GitHub."
    echo "  Se sigue con la copia que ya está en $REPO."
  else
    echo "  MAL: no se pudo bajar el proyecto desde GitHub, y en $REPO" >&2
    echo "  no hay una copia." >&2
    echo >&2
    echo "  Si el repositorio es privado: copiá la carpeta del proyecto a" >&2
    echo "  esta Mac (AirDrop o USB) como ~/centonara-seguimientos y corré:" >&2
    echo >&2
    echo "    bash ~/centonara-seguimientos/agente/instalador/instalar.sh" >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
titulo "[4/7] El entorno del agente"

uv sync --directory "$REPO/agente"
PYTHON="$REPO/agente/.venv/bin/python"
[ -x "$PYTHON" ] || { echo "  MAL: no quedó $PYTHON" >&2; exit 1; }
echo "  ok  entorno listo"

# ---------------------------------------------------------------------------
titulo "[5/7] Los datos de esta máquina"
#
# Lo que la máquina puede saber sola, se averigua solo: qué perfil de Chrome
# tiene la extensión Y la sesión de WhatsApp, y el deviceId de la extensión.
# Es la misma lógica de `--datos`, sin pedirle a nadie que copie nada.
#
# El `cd` no es decorativo: el paquete `agente` no se instala en el venv (el
# pyproject no tiene build-system, a propósito), así que sólo se puede importar
# parado en esa carpeta — igual que hace `uv run --directory agente` en todos
# los comandos del proyecto, y el launchd con su WorkingDirectory.

datos=$(cd "$REPO/agente" && "$PYTHON" - <<'PY'
from agente.perfiles import listar, recomendar
r = recomendar(listar())
if r.listo:
    print("LISTO"); print(r.perfil.nombre); print(r.perfil.device_id or "")
else:
    print("FALTA"); print(r.problema); print(r.solucion)
PY
)
estado=$(printf '%s\n' "$datos" | sed -n '1p')
linea2=$(printf '%s\n' "$datos" | sed -n '2p')
linea3=$(printf '%s\n' "$datos" | sed -n '3p')

if [ "$estado" != "LISTO" ]; then
  echo "  Todavía no se puede seguir: $linea2"
  echo
  echo "  Qué hacer: $linea3"
  echo "  Después, volvé a correr este instalador."
  exit 1
fi
PERFIL="$linea2"
DEVICE_ID="$linea3"

if [ -z "$DEVICE_ID" ]; then
  echo "  La extensión está instalada pero nunca se usó en esta máquina."
  echo
  echo "  Qué hacer: abrí Chrome, apretá el ícono de Claude y pedile cualquier"
  echo "  cosa. Después volvé a correr este instalador."
  exit 1
fi
echo "  ok  perfil de Chrome: $PERFIL"
echo "  ok  deviceId: $DEVICE_ID"

# Lo que ya estaba en el .env se conserva: el token no se vuelve a pedir, y una
# máquina puesta a propósito en otro modo o contra otro backend no se resetea.
ENV_ARCHIVO="$REPO/.env"
viejo() {
  [ -f "$ENV_ARCHIVO" ] || return 0
  sed -n "s/^$1=//p" "$ENV_ARCHIVO" | head -1 | sed 's/[[:space:]]*#.*$//; s/[[:space:]]*$//'
}
BACKEND_URL=$(viejo AGENTE_BACKEND_URL); BACKEND_URL="${BACKEND_URL:-$BACKEND_POR_DEFECTO}"
MODO=$(viejo AGENTE_MODO);               MODO="${MODO:-simulado}"
PUERTO=$(viejo CHROME_PUERTO);           PUERTO="${PUERTO:-9222}"
MACHINE_ID=$(viejo AGENTE_MACHINE_ID)
TOKEN=$(viejo AGENTE_TOKEN)

echo "  comprobando el servidor (si estaba dormido tarda un minuto)..."
salud=$(curl -s -m 120 "$BACKEND_URL/health" || true)
case "$salud" in
  *'"ok":true'*) echo "  ok  el servidor contesta: $BACKEND_URL" ;;
  *)
    echo "  MAL el servidor no contesta: $BACKEND_URL" >&2
    echo "      ¿Hay internet? Esperá un minuto y volvé a correr este instalador." >&2
    exit 1
    ;;
esac

if [ -z "$MACHINE_ID" ] || [ -z "$TOKEN" ]; then
  if [ "$TECLADO" = no ]; then
    echo "  Faltan el identificador y el token, y no hay teclado para" >&2
    echo "  preguntarlos. Corré este instalador desde una Terminal común." >&2
    exit 1
  fi
  echo
  echo "  Dos datos salen del panel, de cuando se dio de alta esta máquina:"
  while [ -z "$MACHINE_ID" ]; do
    MACHINE_ID=$(preguntar "    Identificador de la máquina (ej: mac-rocio): ")
    case "$MACHINE_ID" in
      *[!a-z0-9-]*|"")
        echo "    Sólo minúsculas, números y guiones — idéntico al del panel."
        MACHINE_ID="" ;;
    esac
  done
  while [ -z "$TOKEN" ]; do
    TOKEN=$(preguntar "    Token de la máquina (empieza con sgc_): ")
    case "$TOKEN" in
      sgc_?*) ;;
      *)
        echo "    Tiene que empezar con sgc_. Si se perdió, en el panel se rota"
        echo "    y sale uno nuevo."
        TOKEN="" ;;
    esac
  done
else
  echo "  ok  identificador y token ya estaban en el .env: se conservan"
fi

cat > "$ENV_ARCHIVO" <<ENV_EOF
# Escrito por agente/instalador/instalar.sh. Volver a correr el instalador lo
# regenera conservando estos valores. NO se comparte: tiene el token.
AGENTE_BACKEND_URL=$BACKEND_URL
AGENTE_MODO=$MODO
CLAUDE_BIN=$CLAUDE_BIN
CHROME_PERFIL_DIR=$PERFIL
CHROME_PUERTO=$PUERTO
AGENTE_DEVICE_ID=$DEVICE_ID
AGENTE_MACHINE_ID=$MACHINE_ID
AGENTE_TOKEN=$TOKEN
ENV_EOF
echo "  ok  .env escrito: $ENV_ARCHIVO"

# ---------------------------------------------------------------------------
titulo "[6/7] El arranque automático"
#
# instalar-mac.sh escribe los dos LaunchAgents (el agente y Chrome con el
# puerto), pone el permiso del modo headless y corre el diagnóstico. RESUMEN=no
# le apaga el resumen final para pegar a mano: acá el .env ya está escrito.

CHROME_PERFIL_DIR="$PERFIL" CHROME_PUERTO="$PUERTO" RESUMEN=no \
  bash "$REPO/agente/instalador/instalar-mac.sh"

# ---------------------------------------------------------------------------
titulo "[7/7] Arrancar ahora"

uid=$(id -u)
launchctl bootout "gui/$uid/com.centonara.agente" 2>/dev/null || true
launchctl bootout "gui/$uid/com.centonara.chrome" 2>/dev/null || true

# Chrome tiene que estar CERRADO cuando arranca el servicio: si ya hay una
# instancia abierta, macOS ignora los argumentos y el puerto no se abre.
if pgrep -f "Google Chrome" >/dev/null 2>&1; then
  echo "  cerrando Chrome (se vuelve a abrir solo, con la sesión intacta)..."
  # macOS puede preguntar si la Terminal puede controlar Chrome: es que sí.
  osascript -e 'quit app "Google Chrome"' >/dev/null 2>&1 || true
  intentos=0
  while pgrep -f "Google Chrome" >/dev/null 2>&1; do
    intentos=$((intentos + 1))
    if [ "$intentos" -gt 15 ]; then
      if [ "$TECLADO" = si ]; then
        preguntar "  No se cerró solo. Cerralo vos con Cmd+Q y apretá Enter: " >/dev/null
        intentos=0
      else
        echo "  Chrome no se cierra. Cerralo con Cmd+Q y volvé a correr esto." >&2
        exit 1
      fi
    fi
    sleep 1
  done
fi

launchctl bootstrap "gui/$uid" "$HOME/Library/LaunchAgents/com.centonara.chrome.plist"
echo "  esperando a que Chrome levante el puerto..."
puerto_ok=no
for _ in 1 2 3 4; do
  sleep 2
  version=$(curl -s -m 3 "http://localhost:$PUERTO/json/version" || true)
  case "$version" in *'"Browser"'*) puerto_ok=si; break ;; esac
done
if [ "$puerto_ok" = si ]; then
  echo "  ok  Chrome corriendo con el puerto $PUERTO"
else
  # Chrome 136+ rechaza el puerto sobre el perfil normal del usuario
  # ("DevTools remote debugging requires a non-default data directory").
  # No corta la instalación: el puerto lo necesita sólo el envío real
  # (fase 4), que hoy ya está bloqueado por otro motivo. La lectura y los
  # borradores van por la extensión y no lo usan.
  echo "  aviso: Chrome está corriendo, pero sin el puerto $PUERTO."
  echo "  Los Chrome nuevos (136 en adelante) no dejan abrirlo sobre el"
  echo "  perfil normal. Hoy no bloquea nada: lo necesita recién el envío"
  echo "  real (fase 4), y se resuelve en esa fase. Se sigue igual."
fi

launchctl bootstrap "gui/$uid" "$HOME/Library/LaunchAgents/com.centonara.agente.plist"
echo "  ok  agente corriendo"

# ---------------------------------------------------------------------------
titulo "INSTALACIÓN COMPLETA"

cat <<FIN
  A partir de ahora, cada vez que el vendedor prenda esta Mac e inicie sesión,
  Chrome y el agente arrancan solos. Si el agente se cae, se vuelve a levantar
  solo. No hay que tocar nada más en esta computadora.

  Quedan dos cosas, si todavía no se hicieron:

  1. El permiso de la extensión (con el mouse, en Chrome):
     ícono de Claude → configuración → permisos de sitios → web.whatsapp.com

  2. Activar la máquina desde el panel, cuando se decida.
     Instalada no es activada: hasta activarla, no toma trabajo.

  Para comprobar de punta a punta (abre WhatsApp Web una vez, tarda unos
  minutos y cuesta ~USD 0,50):

    cd $REPO && uv run --directory agente python -m agente.main --sonda

  Los logs quedan en ~/Library/Logs/centonara/
FIN

exit 0
}

principal "$@"
