/**
 * El catálogo de comandos que se muestran en `/comandos`.
 *
 * **Por qué vive acá y no en `textos.ts`.** La convención del panel es que todo
 * texto que lee una persona va en `textos.ts`, para poder cambiar palabras sin
 * salir a buscarlas. Esto es la excepción, y con motivo: un comando y su
 * explicación son **una sola cosa**. Si mañana el agente cambia una opción, lo
 * que cambia es el comando *y* la línea que dice qué hace. Separarlos en dos
 * archivos garantiza que en algún momento el panel muestre un comando nuevo con
 * la explicación vieja — y alguien lo va a pegar en una Terminal.
 *
 * La cáscara de la página (título, botones, avisos) sí está en `textos.ts`.
 *
 * ⚠️ **Cada comando de acá tiene que existir tal cual en el repositorio.** Las
 * fuentes son `README.md`, `docs/SOP-instalar-mac.md` y
 * `agente/instalador/instalar.sh`. Un comando que se copia del panel y no anda
 * es peor que no tenerlo, porque quien lo pega no tiene forma de saber si se
 * equivocó él.
 */

export type Comando = {
  /** Ancla del índice. Único en toda la página. */
  id: string;
  titulo: string;
  /** Lo que se copia, exactamente. Una sola línea. */
  comando: string;
  /** Qué hace, en una oración. */
  queHace: string;
  /** Cuándo se usa. Opcional: hay comandos que se explican solos. */
  cuando?: string;
  /** Lo que hay que reemplazar antes de pegarlo. Se muestra en rojo. */
  hueco?: string;
  /** Lo que puede salir mal, o lo que cuesta. */
  aviso?: string;
};

export type Grupo = {
  id: string;
  titulo: string;
  /** Para quién es este grupo y desde dónde se corre. */
  descripcion: string;
  /** Lo que hay que leer ANTES de correr nada del grupo. Se muestra destacado. */
  aviso?: string;
  comandos: Comando[];
  /** Cómo sigue, o qué se está aceptando. Va al final del grupo. */
  pie?: string;
};

/** Dónde queda el proyecto en la Mac del vendedor. Lo fija el instalador. */
const REPO = "~/centonara-seguimientos";

/** El prefijo que llevan casi todos los comandos del agente. */
const EN_EL_AGENTE = `cd ${REPO} && uv run --directory agente python -m agente.main`;

export const grupos: Grupo[] = [
  {
    id: "mac",
    titulo: "En la Mac del vendedor",
    descripcion:
      "Se pegan en la Terminal de esa Mac (Cmd + barra espaciadora, escribir «Terminal», Enter). Ninguno de estos envía mensajes.",
    comandos: [
      {
        id: "instalar",
        titulo: "Instalar el agente, o actualizarlo",
        comando:
          "curl -fsSL https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/instalar.sh | bash",
        queHace:
          "Instala todo lo que hace falta, baja el programa, averigua solo los datos de la máquina, deja configurado el arranque automático y lo enciende. Va a pedir el identificador y el token de la máquina.",
        cuando:
          "En una Mac nueva, y cada vez que haya que actualizar el programa. Correrlo de nuevo es la forma de actualizar, y no vuelve a preguntar nada.",
        aviso:
          "Es seguro repetirlo las veces que haga falta. Si algo falta, se detiene y lo dice en castellano: hacer lo que dice y volver a pegar el mismo comando.",
      },
      {
        id: "vincular",
        titulo: "Vincular el navegador que escribe los mensajes",
        comando: `${EN_EL_AGENTE} --vincular`,
        queHace:
          "Abre el navegador dedicado del motor de envío para escanear el QR con el teléfono del vendedor. Es un navegador aparte del que usa todos los días: por eso el sistema nunca le toca las pestañas ni la sesión.",
        cuando:
          "El instalador lo ofrece solo al final. Se corre a mano si en su momento se dijo que no, o cuando esa sesión vence y un envío falla diciendo que no hay sesión.",
        aviso: "Hay que tener el teléfono del vendedor a mano: WhatsApp → Dispositivos vinculados.",
      },
      {
        id: "diagnostico",
        titulo: "Qué le falta a esta máquina",
        comando: `${EN_EL_AGENTE} --diagnostico`,
        queHace:
          "Corre los nueve chequeos, marca en rojo lo que hay que resolver y «n/a» lo que no aplica acá. No consulta al backend.",
        cuando: "Es el primero que hay que correr cuando algo no anda. No cuesta nada y es instantáneo.",
      },
      {
        id: "sonda",
        titulo: "Probar que llega a WhatsApp Web",
        comando: `${EN_EL_AGENTE} --sonda`,
        queHace:
          "Contesta las dos preguntas que el diagnóstico no puede: si la extensión tiene el permiso de sitio y si la sesión de WhatsApp está iniciada. Cuenta cuántos chats ve y nada más — no abre ninguna conversación ni lee ningún mensaje.",
        cuando:
          "Cuando el diagnóstico da todo verde y las corridas igual fallan. Es lo que distingue «falta el permiso de la extensión» de «venció el QR».",
        aviso: "Abre el navegador y consume saldo de Claude. Tarda minutos, por eso no viene con el diagnóstico.",
      },
      {
        id: "claude",
        titulo: "Iniciar sesión en Claude Code",
        comando: "claude",
        queHace:
          "Abre Claude Code para iniciar sesión con la cuenta de esta máquina. Se sale escribiendo /exit.",
        cuando:
          "Cuando el panel muestra un error que dice que la sesión de Claude Code venció. Es una de las tres sesiones que vencen cada tanto, y no es una falla.",
      },
      {
        id: "logs",
        titulo: "Ver qué está haciendo el agente",
        comando: "tail -f ~/Library/Logs/centonara/agente.log",
        queHace: "Muestra el registro del agente en vivo, línea por línea, a medida que trabaja.",
        cuando: "Para mirar una corrida mientras pasa. Se corta con Control + C.",
      },
      {
        id: "logs-error",
        titulo: "Ver los errores del agente",
        comando: "tail -n 50 ~/Library/Logs/centonara/agente.err",
        queHace: "Las últimas cincuenta líneas de error. Es lo que hay que copiar y mandar cuando algo se rompe.",
      },
      {
        id: "reiniciar",
        titulo: "Reiniciar el agente",
        comando: "launchctl kickstart -k gui/$(id -u)/com.centonara.agente",
        queHace: "Lo frena y lo vuelve a levantar, con la configuración nueva.",
        cuando: "Después de tocar cualquier cosa del archivo .env.",
      },
      {
        id: "estado",
        titulo: "¿Está corriendo el agente?",
        comando: "launchctl list | grep centonara",
        queHace:
          "Lista los dos servicios de arranque automático con su número de proceso y el resultado de la última vez que corrieron. Un 0 en el medio es que salió bien.",
        cuando: "Cuando la máquina figura «sin conexión» en el panel y la Mac está claramente prendida.",
      },
      // El comando "cambiar el modo del agente" se fue con la perilla (D32):
      // el agente instalado está siempre operativo, y si un mensaje queda como
      // borrador o se envía lo decide el botón del panel. Un AGENTE_MODO que
      // haya quedado en un .env viejo se ignora.
    ],
  },

  {
    id: "mantenimiento",
    titulo: "Cuando algo se rompe",
    descripcion: "También en la Mac del vendedor, pero son de quien mantiene el sistema.",
    comandos: [
      {
        id: "selectores",
        titulo: "Verificar los selectores de WhatsApp",
        comando: `${EN_EL_AGENTE} --verificar-selectores --chat +549XXXXXXXXXX`,
        queHace:
          "Abre el chat de ese número en el navegador dedicado y comprueba, uno por uno, que el encabezado, el campo de escritura y el botón de enviar sigan estando donde el sistema los busca. Dice exactamente cuál se rompió.",
        cuando:
          "Cuando WhatsApp cambia por dentro y los mensajes dejan de salir sin que aparezca ningún error claro.",
        hueco: "+549XXXXXXXXXX — el número de PRUEBA cuyo chat se abre.",
        aviso:
          "Elegir el número a propósito: se abre un chat real. No envía nada, pero conviene que sea una línea de prueba y no la de un cliente.",
      },
      {
        id: "datos",
        titulo: "Los datos de esta máquina, listos para el .env",
        comando: `${EN_EL_AGENTE} --datos`,
        queHace:
          "Averigua qué perfil de Chrome usar y cuál es su deviceId, e imprime las líneas del .env listas para pegar.",
        cuando:
          "El instalador lo hace solo. Se corre a mano cuando el vendedor cambió de perfil de Chrome y el agente quedó apuntando al equivocado.",
      },
      {
        id: "detener",
        titulo: "Detener el agente",
        comando: "launchctl bootout gui/$(id -u)/com.centonara.agente",
        queHace: "Lo frena y no lo vuelve a levantar hasta el próximo inicio de sesión.",
        aviso:
          "Para frenar todo el sistema está el botón del panel, que es inmediato y queda registrado. Esto es sólo para trabajar sobre una máquina.",
      },
      {
        id: "arrancar",
        titulo: "Volver a arrancar el agente",
        comando:
          "launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.centonara.agente.plist",
        queHace: "Deshace el comando anterior sin tener que reiniciar la Mac.",
      },
    ],
  },

  {
    id: "macos-viejo",
    titulo: "Si la Mac tiene macOS anterior a 13",
    descripcion:
      "El instalador falla con «error 134» o «Abort trap: 6». No es la descarga: Claude Code pide macOS 13.0 y en una versión más vieja el binario no puede cargarse y se aborta. Homebrew y npm bajan exactamente el mismo binario, así que ninguno lo resuelve. Lo que sigue es el rodeo que sí funciona, y es un puente, no una solución.",
    aviso:
      "PRIMERO probá la extensión: instalá Claude in Chrome en el Chrome de esa Mac, iniciá sesión y pedile cualquier cosa. Chrome dejó de actualizarse en esos macOS hace más de un año, y si la extensión no anda ahí, nada de lo que sigue sirve — el agente necesita el navegador para leer los chats. Son cinco minutos y ahorran la tarde entera.",
    comandos: [
      {
        id: "catalina-version",
        titulo: "1. Confirmar qué macOS tiene esta Mac",
        comando: "sw_vers -productVersion",
        queHace:
          "Si devuelve 13 o más, el problema es otro y este apartado no aplica. 10.15 es Catalina, 11 es Big Sur, 12 es Monterey: las tres están por debajo del mínimo.",
      },
      {
        id: "catalina-modelo",
        titulo: "2. Ver si conviene actualizar el sistema en vez de esto",
        comando: 'system_profiler SPHardwareDataType | grep -E "Model Name|Model Identifier"',
        queHace:
          "El modelo y el año. macOS 13 acepta MacBook Pro desde 2017, MacBook Air desde 2018, iMac desde 2017, Mac mini desde 2018 y Mac Pro desde 2019. Si la máquina entra en esa lista, actualizar el sistema es mejor camino que todo lo que sigue.",
        aviso:
          "Antes de una actualización mayor: copia de seguridad con Time Machine, 40 GB libres, enchufada, y entre una y dos horas en las que el vendedor no va a poder usarla.",
      },
      {
        id: "catalina-node",
        titulo: "3. Bajar Node 18",
        comando: "curl -fsSLO https://nodejs.org/dist/v18.20.8/node-v18.20.8.pkg",
        queHace:
          "Node 18 es la última rama que corre en macOS 10.15; las siguientes piden 13.5 o más. Es la pieza que hace posible todo lo demás, y sirve para dos cosas: Claude Code, que lee los chats, y el motor de envío — el navegador que escribe los mensajes también necesita un Node, y el que trae adentro está compilado para macOS 11 o más nuevo. El agente lo detecta solo y usa éste; no hay que configurar nada.",
        aviso:
          "Si esta Mac no tiene Node instalado, el envío falla con «dyld: Symbol not found» y una referencia a «playwright/driver/node». Ese error significa exactamente esto y se resuelve con este paso.",
      },
      {
        id: "catalina-node-instalar",
        titulo: "4. Instalar Node",
        comando: "sudo installer -pkg node-v18.20.8.pkg -target /",
        queHace: "Instala Node y npm en el sistema.",
        aviso: "Pide la contraseña de administrador de esa Mac.",
      },
      {
        id: "catalina-npm-prefijo",
        titulo: "5. Preparar npm para instalar sin sudo",
        comando:
          "npm config set prefix ~/.npm-global && echo 'export PATH=$HOME/.npm-global/bin:$PATH' >> ~/.zshrc && source ~/.zshrc",
        queHace:
          "Mueve los paquetes globales de npm a tu carpeta personal. Sin esto, el paso siguiente falla con «EACCES: permission denied» sobre /usr/local/lib/node_modules: ese directorio es de root y el instalador de Node no lo cede.",
        aviso:
          "No lo arregles con «sudo npm install -g»: deja archivos de root en tu carpeta y rompe las actualizaciones después. Si esa Mac usa bash en vez de zsh, cambiá ~/.zshrc por ~/.bash_profile. Y si corrés este comando dos veces, sacá la línea repetida del ~/.zshrc.",
      },
      {
        id: "catalina-claude",
        titulo: "6. Instalar la última versión de Claude Code que no es binario nativo",
        comando: "npm install -g @anthropic-ai/claude-code@2.1.100",
        queHace:
          "Hasta la 2.1.110, Claude Code era un paquete JavaScript que corría sobre Node; el binario nativo —el que aborta— aparece a partir de la 2.1.120. Esta versión tiene «--chrome» y la extensión, que es lo que el agente necesita.",
        aviso:
          "npm va a avisar que hay una versión nueva de sí mismo. NO le hagas caso: npm 12 exige Node 22 o superior, y esta máquina no puede pasar de Node 18. Actualizarlo deja la máquina sin npm que funcione.",
      },
      {
        id: "catalina-sin-updates",
        titulo: "7. Frenar la actualización automática",
        comando: `mkdir -p ~/.claude && echo '{"env":{"DISABLE_AUTOUPDATER":"1"}}' > ~/.claude/settings.json`,
        queHace:
          "Deja escrito que no se actualice sola. Sin esto, Claude Code se reemplaza por una versión nativa en cuestión de horas y vuelve el error 134.",
        aviso:
          "Si esa Mac ya tiene un ~/.claude/settings.json, este comando lo pisa. En ese caso abrilo y agregale la clave «env» a mano.",
      },
      {
        id: "catalina-verificar",
        titulo: "8. Comprobar que quedó la versión correcta",
        comando: "claude --version",
        queHace: "Tiene que decir 2.1.100. Si dice otra cosa, la actualización automática ya corrió.",
      },
      {
        id: "catalina-sesion",
        titulo: "9. Iniciar sesión",
        comando: "claude",
        queHace: "Se entra con la cuenta de esta máquina y se sale escribiendo /exit.",
      },
    ],
    pie: "Después de esto, cerrá la Terminal y abrí una nueva —si no, el instalador no ve el PATH que dejó el paso 5— y corré el instalador normal del agente: cuando encuentra «claude» ya instalado no lo toca, así que sigue de largo sin volver a fallar. Lo que se está aceptando: Node 18 dejó de recibir parches en abril de 2025, esta versión de Claude Code queda congelada, y Anthropic puede dejar de aceptar versiones viejas cuando quiera — el día que pase, esa máquina deja de funcionar sin aviso. Sirve para desbloquear ahora; el reemplazo de la máquina va en la lista de cosas a pedir.",
  },

  {
    id: "windows",
    titulo: "Conectar una máquina Windows",
    descripcion:
      "El instalador automático es sólo para Mac, pero el agente en sí ya sabe funcionar en Windows: dónde vive el perfil de Chrome, cómo lanzar el navegador y cómo conectarse tienen su versión para este sistema. Lo que sigue hace a mano lo que en la Mac hace el instalador, sin cambiar nada del sistema actual. Se pega todo en PowerShell.",
    aviso:
      "Este camino todavía no se probó de punta a punta. El agente tiene el código, y el MVP funcionó en Windows, pero ninguna máquina Windows corrió esta versión. Dejala en modo «simulado» y después en «prueba» hasta verla trabajar completa; recién ahí pasala a «real».",
    comandos: [
      {
        id: "windows-git",
        titulo: "1. Instalar Git",
        comando: "winget install Git.Git",
        queHace: "Hace falta para bajar el proyecto. Si ya está instalado, winget lo dice y sigue.",
      },
      {
        id: "windows-uv",
        titulo: "2. Instalar uv",
        comando: 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
        queHace:
          "uv se encarga de Python y de las dependencias del agente. No hace falta instalar Python aparte: uv lo baja solo.",
      },
      {
        id: "windows-claude",
        titulo: "3. Instalar Claude Code",
        comando: "irm https://claude.ai/install.ps1 | iex",
        queHace: "El instalador nativo para Windows. En esta máquina sí funciona: el problema de macOS 13 no aplica acá.",
        aviso:
          "Si te dice que «irm» no se reconoce, estás en CMD y no en PowerShell. El prompt de PowerShell empieza con «PS».",
      },
      {
        id: "windows-sesion",
        titulo: "4. Iniciar sesión en Claude Code",
        comando: "claude",
        queHace: "Se entra con la cuenta de esta máquina y se sale escribiendo /exit. Sin esto, el agente no puede leer ningún chat.",
        aviso: "Cerrá y volvé a abrir PowerShell antes de seguir, para que tome el PATH que dejaron los pasos 2 y 3.",
      },
      {
        id: "windows-clonar",
        titulo: "5. Bajar el proyecto",
        comando:
          "git clone https://github.com/martinrodriguez19/centonara-seguimientos.git $HOME\\centonara-seguimientos",
        queHace: "Deja el proyecto en la carpeta del usuario, igual que en la Mac.",
      },
      {
        id: "windows-datos",
        titulo: "6. Averiguar los datos de esta máquina",
        comando:
          "uv run --directory $HOME\\centonara-seguimientos\\agente python -m agente.main --datos",
        queHace:
          "Lista los perfiles de Chrome, marca cuál tiene la extensión y WhatsApp, y escribe las líneas del .env ya resueltas: el perfil, el deviceId y la ruta de Claude Code.",
        aviso:
          "Antes de correrlo hay que dejar Chrome listo, igual que en la Mac: extensión Claude in Chrome instalada y usada una vez, WhatsApp Web con el QR escaneado, y el permiso de sitio para web.whatsapp.com dado DENTRO de la extensión. Si falta algo, este comando lo dice y se detiene.",
      },
      {
        id: "windows-env",
        titulo: "7. Crear el archivo de configuración",
        comando:
          "Copy-Item $HOME\\centonara-seguimientos\\.env.example $HOME\\centonara-seguimientos\\.env; notepad $HOME\\centonara-seguimientos\\.env",
        queHace:
          "Copia la plantilla y la abre. Hay que pegar lo que imprimió el paso 6, y completar AGENTE_BACKEND_URL con la dirección del backend, más AGENTE_MACHINE_ID y AGENTE_TOKEN con lo que dio el panel al dar de alta la máquina.",
        aviso:
          "En Windows se usa punto y coma para encadenar, no «&&»: ahí «&&» es un error de sintaxis.",
      },
      {
        id: "windows-diagnostico",
        titulo: "8. Ver qué le falta a esta máquina",
        comando:
          "uv run --directory $HOME\\centonara-seguimientos\\agente python -m agente.main --diagnostico",
        queHace:
          "Corre los chequeos y marca en rojo lo que falta. El de permisos de macOS va a decir «no aplica»: es correcto, no es un error.",
        aviso:
          "Los tres que suelen quedar en rojo la primera vez —claude_bin, permiso_mcp y device_id— los resuelven los pasos 9, 10 y 11. Los que quedan en «-» no son fallas: son los que sólo se pueden verificar abriendo el navegador, y eso lo hacen los pasos 12 y 13. Después de completar el .env, volvé a correr este comando: tiene que quedar sin ningún [MAL].",
      },
      {
        id: "windows-permiso-mcp",
        titulo: "9. Poner el permiso que Claude Code necesita",
        comando:
          'uv run --directory $HOME\\centonara-seguimientos\\agente python -c "from agente.permiso_mcp import asegurar; print(asegurar().detalle)"',
        queHace:
          "Agrega «mcp__claude-in-chrome» a la lista de permitidos de ~/.claude/settings.json, conservando todo lo que el archivo ya tuviera. Sin ese permiso, Claude Code sin nadie mirando se auto-deniega las acciones del navegador y el job falla con un 502 que no explica nada.",
        aviso:
          "En la Mac esto lo hace el instalador solo; en Windows hay que correrlo a mano. Es idempotente: si ya estaba, lo dice y no toca el archivo. Y nunca lo pises con un echo: ese archivo suele tener otra configuración adentro.",
      },
      {
        id: "windows-claude-bin",
        titulo: "10. Averiguar la ruta completa de Claude Code",
        comando: '"CLAUDE_BIN=$((Get-Command claude).Source)"',
        queHace:
          "Imprime la línea lista para pegar en el .env. Tiene que ser la ruta completa y no el atajo: el agente arranca desde un proceso cuyo PATH no es el de tu PowerShell, y ahí «claude» a secas no resuelve.",
        aviso:
          "Si dice que no reconoce «claude», cerrá PowerShell y abrí una ventana nueva: el instalador de Claude Code dejó el PATH pero esta sesión no lo tomó.",
      },
      {
        id: "windows-device-id",
        titulo: "11. Confirmar que la extensión ya dejó su identificador",
        comando:
          'uv run --directory $HOME\\centonara-seguimientos\\agente python -c "from agente import perfiles; [print(p.nombre, p.tiene_extension, p.tiene_whatsapp, p.device_id) for p in perfiles.listar()]"',
        queHace:
          "Lista cada perfil de Chrome con cuatro datos: nombre, si tiene la extensión, si tiene WhatsApp, y el deviceId. Si el último sale «None», la extensión está instalada pero todavía no se usó en ese perfil.",
        aviso:
          "El deviceId no se configura: aparece solo la primera vez que alguien usa la extensión. Abrí Chrome, apretá el ícono de Claude, pedile cualquier cosa, y volvé a correr esto. Cuando salga el identificador, pegalo en AGENTE_DEVICE_ID y corré el diagnóstico de nuevo.",
      },
      {
        id: "windows-sonda",
        titulo: "12. Probar que llega a WhatsApp Web",
        comando:
          "uv run --directory $HOME\\centonara-seguimientos\\agente python -m agente.main --sonda",
        queHace:
          "Contesta las dos cosas que el diagnóstico deja en «-»: si la extensión tiene el permiso de sitio para web.whatsapp.com y si la sesión está iniciada. Cuenta cuántos chats ve y nada más — no abre ninguna conversación.",
        aviso:
          "Abre el navegador y consume saldo de Claude. Es el único chequeo que no puede hacerse sin mirar la página, por eso no viene con el diagnóstico.",
      },
      {
        id: "windows-navegador",
        titulo: "13. Bajar el navegador que escribe los mensajes",
        comando:
          "uv run --directory $HOME\\centonara-seguimientos\\agente playwright install chromium",
        queHace:
          "Descarga el navegador propio de Playwright, unos 100 MB. En la Mac este paso no existe porque ahí siempre hay un Chrome instalado y el motor de envío lo usa; en Windows puede no haberlo, o estar en una ruta que el agente no busca.",
        aviso:
          "Si te lo saltás, el paso siguiente falla con «no se pudo abrir el perfil en ...\\Centonara\\Chrome». Ese mensaje significa exactamente esto y no que el perfil esté roto.",
      },
      {
        id: "windows-vincular",
        titulo: "14. Vincular el navegador de envío",
        comando:
          "uv run --directory $HOME\\centonara-seguimientos\\agente python -m agente.main --vincular",
        queHace:
          "Abre el navegador aparte que usa el motor de envío, para escanear el QR con el teléfono del vendedor. Es el mismo navegador dedicado que en la Mac: nunca toca la sesión ni las pestañas del vendedor.",
      },
      {
        id: "windows-arrancar",
        titulo: "15. Arrancar el agente",
        comando: "uv run --directory $HOME\\centonara-seguimientos\\agente python -m agente.main",
        queHace:
          "Lo pone a trabajar. La ventana queda ocupada: mientras esté abierta, la máquina figura online en el panel. Se corta con Control + C.",
      },
      {
        id: "windows-inicio",
        titulo: "15. Que arranque solo al prender la máquina",
        comando: `Set-Content -Path "$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\centonara.bat" -Value '@echo off', 'cd /d %USERPROFILE%\\centonara-seguimientos', ':loop', 'uv run --directory agente python -m agente.main', 'timeout /t 10 >nul', 'goto loop'`,
        queHace:
          "Crea un archivo en la carpeta de Inicio de Windows que arranca el agente cuando el vendedor inicia sesión, y lo vuelve a levantar si se cae. Es el reemplazo del arranque automático que en la Mac hace el sistema.",
        aviso:
          "Más rudimentario que en la Mac: abre una ventana de consola que el vendedor puede cerrar sin querer, y el reintento es cada diez segundos sin importar el motivo de la caída. Sirve, pero si esta máquina se queda, conviene pasarlo al Programador de tareas.",
      },
    ],
    pie: "Nada de esto modifica el sistema actual: no toca el instalador de Mac, ni el código del agente, ni la configuración de las otras máquinas. Es el mismo agente corriendo, con los pasos hechos a mano. En el panel, esta máquina se da de alta y se activa igual que cualquier otra — y el consentimiento del vendedor se registra igual, porque los mensajes también salen de su línea.",
  },

  {
    id: "desarrollo",
    titulo: "Levantar el sistema en una computadora de desarrollo",
    descripcion:
      "Nada de esto va en la Mac de un vendedor. Hacen falta Docker, Python 3.12, uv, y Node 22 con pnpm.",
    comandos: [
      {
        id: "clonar",
        titulo: "Bajar el proyecto",
        comando: "git clone https://github.com/martinrodriguez19/centonara-seguimientos.git",
        queHace: "Un solo clone y está todo: backend, panel, agente e infraestructura.",
      },
      {
        id: "env",
        titulo: "Crear la configuración",
        comando: "cp .env.example .env",
        queHace:
          "Copia la configuración de ejemplo. Hay que completar dos valores: SESION_SECRET, que viene vacío, y PANEL_PASSWORD, que dice «cambiar».",
        aviso:
          "Los dos fallan cerrados: sin secreto no se puede firmar una cookie, y una contraseña vacía nunca valida. No se puede arrancar abierto por olvido, pero tampoco se entra al panel hasta completarlos.",
      },
      {
        id: "secreto",
        titulo: "Generar el secreto de sesión",
        comando: "openssl rand -hex 32",
        queHace: "Imprime un secreto al azar para pegar en SESION_SECRET.",
      },
      {
        id: "mongo",
        titulo: "Levantar la base",
        comando: "docker compose -f infra/docker-compose.dev.yml up -d",
        queHace:
          "Levanta el Mongo local. La primera vez corre solo el script que crea el rol y el usuario de la aplicación.",
        aviso:
          "Ese script sólo corre con el volumen vacío. Si alguna vez cambian los privilegios del rol, hay que borrar el volumen para que se vuelvan a aplicar.",
      },
      {
        id: "backend",
        titulo: "Levantar el backend",
        comando: "uv run --directory backend fastapi dev app/main.py",
        queHace: "La API, en http://localhost:8000/docs. Desde la raíz del repositorio.",
      },
      {
        id: "pnpm-install",
        titulo: "Instalar las dependencias del panel",
        comando: "pnpm install",
        queHace: "Desde frontend/.",
        aviso: "Node 22 o superior, no negociable: es el problema #1 del historial del MVP.",
      },
      {
        id: "pnpm-dev",
        titulo: "Levantar el panel",
        comando: "pnpm dev",
        queHace: "El panel, en http://localhost:3000. Desde frontend/.",
      },
      {
        id: "tests-backend",
        titulo: "Los tests del backend",
        comando:
          "MONGO_URL_TESTS='mongodb://root:root-local@localhost:27017/?authSource=admin' uv run --directory backend pytest -q",
        queHace: "Corre los 553 tests. Tiene que decir «553 passed».",
        aviso:
          "Sin la variable, 242 tests se saltean en silencio y el resumen se lee como si estuviera todo verde. Va con el usuario root y no con app, porque cada test crea y borra su propia base. Si aparece «skipped», la variable no llegó.",
      },
      {
        id: "tests-agente",
        titulo: "Los tests del agente",
        comando: "uv run --directory agente pytest -q",
        queHace: "Los 94 tests del agente. No necesitan base ni navegador.",
      },
      {
        id: "certificados",
        titulo: "Si las descargas fallan con un error de certificado",
        comando: "UV_NATIVE_TLS=1 uv sync --directory backend",
        queHace:
          "Le dice a uv que use el almacén de certificados del sistema. En una red que inspecciona TLS —un antivirus con escudo web, un proxy corporativo— uv no confía en el certificado que le llega y no puede bajar nada.",
        aviso: "Para Node el equivalente es NODE_EXTRA_CA_CERTS apuntando al .pem del antivirus.",
      },
    ],
  },
];
