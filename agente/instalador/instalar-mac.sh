#!/usr/bin/env bash
#
# Instala el agente en la Mac de un vendedor (F5.3).
#
# Se corre UNA VEZ por máquina, desde la carpeta del repositorio ya clonado:
#
#     bash agente/instalador/instalar-mac.sh
#
# Qué hace, y nada más que esto:
#   1. Verifica que estén las herramientas
#   2. Crea el entorno del agente
#   3. Escribe el LaunchAgent del agente, con rutas ABSOLUTAS
#   4. Escribe el LaunchAgent de Chrome, con el puerto de depuración
#   5. Corre el diagnóstico y dice qué falta
#
# Qué NO hace, a propósito:
#   - No pide contraseñas ni tokens. El token de la máquina lo pega una persona
#     en el `.env`, y se muestra una sola vez en el panel.
#   - No concede permisos. Los de macOS y el de sitio de la extensión se dan a
#     mano, y el script dice cuáles y cuándo.
#   - No arranca el agente. Instalar no es activar: eso se decide en el panel.

set -Eeuo pipefail

# ---------------------------------------------------------------------------
# Dónde está todo
# ---------------------------------------------------------------------------

AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
AGENTE=$(cd "$AQUI/.." && pwd)
REPO=$(cd "$AGENTE/.." && pwd)
LOGS="$HOME/Library/Logs/centonara"
PLIST="$HOME/Library/LaunchAgents/com.centonara.agente.plist"
ETIQUETA="com.centonara.agente"
PLIST_CHROME="$HOME/Library/LaunchAgents/com.centonara.chrome.plist"
ETIQUETA_CHROME="com.centonara.chrome"
CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_PERFIL="$HOME/Library/Application Support/Google/Chrome"
# El perfil DENTRO de User Data. Se puede pasar por variable de entorno:
#   CHROME_PERFIL_DIR="Profile 3" bash instalar-mac.sh
CHROME_PERFIL_DIR="${CHROME_PERFIL_DIR:-Default}"
CHROME_PUERTO="${CHROME_PUERTO:-9222}"

echo "repositorio: $REPO"
echo "agente:      $AGENTE"
echo

# ---------------------------------------------------------------------------
# 1. Las herramientas
# ---------------------------------------------------------------------------

echo "[1/5] verificando herramientas"

falta=0
requerir() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "      ok   $1 → $(command -v "$1")"
  else
    echo "      MAL  falta $1 — $2" >&2
    falta=1
  fi
}

requerir uv     "https://docs.astral.sh/uv/  ·  curl -LsSf https://astral.sh/uv/install.sh | sh"
requerir claude "npm install -g @anthropic-ai/claude-code"

[ "$falta" -eq 0 ] || { echo; echo "Instalá lo que falta y volvé a correr esto." >&2; exit 1; }

# ⚠️ La ruta COMPLETA, no `claude` a secas. El PATH de launchd no es el de esta
# terminal: es el problema #2 del MVP, y es el que hace que ande a mano y falle
# cuando arranca solo. `claude` suele ser un shim de npm; se resuelve al .exe/bin real.
CLAUDE_BIN=$(command -v claude)
if [ -L "$CLAUDE_BIN" ]; then
  CLAUDE_BIN=$(readlink -f "$CLAUDE_BIN" 2>/dev/null || python3 -c "import os,sys;print(os.path.realpath(sys.argv[1]))" "$CLAUDE_BIN")
fi
echo "      claude real: $CLAUDE_BIN"

# ---------------------------------------------------------------------------
# 2. El entorno
# ---------------------------------------------------------------------------

echo "[2/5] creando el entorno del agente"
uv sync --directory "$AGENTE"
PYTHON="$AGENTE/.venv/bin/python"
[ -x "$PYTHON" ] || { echo "MAL: no quedó $PYTHON" >&2; exit 1; }
echo "      python: $PYTHON"

mkdir -p "$LOGS" "$HOME/Library/LaunchAgents"

# ---------------------------------------------------------------------------
# 3. El LaunchAgent
# ---------------------------------------------------------------------------
#
# ⚠️ LaunchAgent y NO LaunchDaemon (D16). Chrome, la extensión y el native
# messaging viven en la sesión interactiva del usuario; un daemon corre fuera de
# esa sesión y no ve ese Chrome. Si alguien propone moverlo a
# /Library/LaunchDaemons, la respuesta es no.

echo "[3/5] escribiendo el LaunchAgent"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${ETIQUETA}</string>

  <!-- Rutas absolutas: launchd no tiene el PATH de una terminal. -->
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>-m</string>
    <string>agente.main</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${AGENTE}</string>

  <!-- Arranca al iniciar sesión, y si el proceso muere launchd lo vuelve a
       levantar. El agente ya reintenta solo ante fallos de red; esto cubre que
       el proceso se caiga entero. -->
  <key>RunAtLoad</key>  <true/>
  <key>KeepAlive</key>  <true/>

  <!-- Sin esto, un proceso que muere al arrancar entra en bucle cerrado. -->
  <key>ThrottleInterval</key> <integer>30</integer>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>CLAUDE_BIN</key>
    <string>${CLAUDE_BIN}</string>
  </dict>

  <key>StandardOutPath</key>  <string>${LOGS}/agente.log</string>
  <key>StandardErrorPath</key><string>${LOGS}/agente.err</string>
</dict>
</plist>
PLIST_EOF

plutil -lint "$PLIST" >/dev/null || { echo "MAL: el plist quedó inválido" >&2; exit 1; }
echo "      $PLIST"

# ---------------------------------------------------------------------------
# 4. Chrome, arrancando con el puerto al iniciar sesión
# ---------------------------------------------------------------------------
#
# El motor de envío se engancha a Chrome por CDP, y para eso el navegador tiene
# que estar abierto con tres flags. Desde Chrome 136 el puerto **se ignora en
# silencio** si no se pasa `--user-data-dir` explícito: arranca, acepta el flag,
# y no abre nada.
#
# Se hace con un LaunchAgent y no pidiéndole al vendedor que abra Chrome de una
# forma especial, por el motivo de siempre: el vendedor no tiene que saber que
# esto existe. Y como Chrome ya está abierto cuando él hace click en el Dock,
# esa ventana se engancha a la instancia que tiene el puerto.

echo "[4/5] Chrome al iniciar sesión"

if [ ! -x "$CHROME_APP" ]; then
  echo "      MAL  no está $CHROME_APP" >&2
  echo "           Instalá Chrome y volvé a correr esto." >&2
  exit 1
fi

cat > "$PLIST_CHROME" <<CHROME_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${ETIQUETA_CHROME}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${CHROME_APP}</string>
    <string>--remote-debugging-port=${CHROME_PUERTO}</string>
    <string>--user-data-dir=${CHROME_PERFIL}</string>
    <string>--profile-directory=${CHROME_PERFIL_DIR}</string>
  </array>

  <!-- Al iniciar sesión, y una sola vez. KeepAlive NO: si el vendedor cierra
       Chrome a propósito, volvérselo a abrir es pelearse con él. El agente lo
       abre solo cuando llega trabajo. -->
  <key>RunAtLoad</key> <true/>

  <key>StandardOutPath</key>  <string>${LOGS}/chrome.log</string>
  <key>StandardErrorPath</key><string>${LOGS}/chrome.err</string>
</dict>
</plist>
CHROME_EOF

plutil -lint "$PLIST_CHROME" >/dev/null || { echo "MAL: el plist de Chrome quedó inválido" >&2; exit 1; }
echo "      $PLIST_CHROME"
echo "      perfil: ${CHROME_PERFIL_DIR}  ·  puerto: ${CHROME_PUERTO}"

# ---------------------------------------------------------------------------
# 5. Qué falta
# ---------------------------------------------------------------------------

echo "[5/5] diagnóstico"
echo
"$PYTHON" -m agente.main --diagnostico || true

cat <<FIN

---------------------------------------------------------------------------
Instalado. Lo que sigue NO lo puede hacer este script:

  1. Completar ${REPO}/.env con:
       AGENTE_BACKEND_URL   la URL del backend
       AGENTE_TOKEN         el token que muestra el panel al dar de alta la
                            máquina. Se muestra UNA sola vez.
       AGENTE_MACHINE_ID    el mismo identificador con el que se dio de alta
       AGENTE_DEVICE_ID     ver abajo

  2. El deviceId de ESTE Chrome:

       grep -ao 'bridgeDeviceId.\\{0,60\\}' \\
         ~/Library/Application\\ Support/Google/Chrome/*/Local\\ Extension\\ Settings/fcoeoabgfenejglbffodgkkbkcdhcgfn/*.log

  3. En la extensión de Claude en Chrome: configuración -> permisos de sitios
     -> habilitar web.whatsapp.com. Es MANUAL y es una capa distinta del
     permiso de Chrome, que ya viene dado. Sin esto falla con
     "requires permission" y no aparece en ningún log del agente.

  4. Dejar la sesión de WhatsApp Web iniciada en ese Chrome.

  5. Comprobar que 3 y 4 quedaron bien, que es lo único que los verifica:

       ${PYTHON} -m agente.main --sonda

  6. Verificar que la extensión y la sesión de WhatsApp estén en el MISMO
     perfil de Chrome, y que sea el que quedó configurado arriba
     (${CHROME_PERFIL_DIR}). Ver docs/SOP-instalar-mac.md §2.5:

       ls -d ~/Library/Application\\ Support/Google/Chrome/*/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn
       ls -d ~/Library/Application\\ Support/Google/Chrome/*/IndexedDB/*whatsapp*

     Si no coinciden, el sistema no funciona: LISTAR usa la extensión y ENVIAR
     usa esa misma ventana. Se corrige con:

       CHROME_PERFIL_DIR="Profile N" bash agente/instalador/instalar-mac.sh

  7. Recién ahí, arrancar las dos cosas:

       launchctl bootstrap gui/\$(id -u) ${PLIST_CHROME}
       launchctl bootstrap gui/\$(id -u) ${PLIST}

     Comprobar que Chrome levantó el puerto:

       curl http://localhost:${CHROME_PUERTO}/json/version

     Y el estado del agente:

       launchctl print gui/\$(id -u)/${ETIQUETA} | head -20

     Para parar:

       launchctl bootout gui/\$(id -u)/${ETIQUETA}
       launchctl bootout gui/\$(id -u)/${ETIQUETA_CHROME}

  Los logs quedan en ${LOGS}/

  La máquina nace INACTIVA. Instalar no es activar: para que tome trabajo hay
  que activarla desde el panel.
---------------------------------------------------------------------------
FIN
