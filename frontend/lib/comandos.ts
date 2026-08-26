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
  comandos: Comando[];
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
        cuando: "Después de tocar cualquier cosa del archivo .env — el modo, por ejemplo.",
      },
      {
        id: "estado",
        titulo: "¿Está corriendo el agente?",
        comando: "launchctl list | grep centonara",
        queHace:
          "Lista los dos servicios de arranque automático con su número de proceso y el resultado de la última vez que corrieron. Un 0 en el medio es que salió bien.",
        cuando: "Cuando la máquina figura «sin conexión» en el panel y la Mac está claramente prendida.",
      },
      {
        id: "modo",
        titulo: "Cambiar el modo del agente",
        comando: "open -e ~/centonara-seguimientos/.env",
        queHace:
          "Abre el archivo de configuración de la máquina. La línea AGENTE_MODO admite «simulado» (no toca ningún navegador), «prueba» (escribe el mensaje y lo borra sin enviarlo) y «real» (aprieta enviar).",
        cuando: "Para dejar una máquina en prueba mientras se la calibra.",
        aviso: "Después de guardar hay que reiniciar el agente, si no el cambio no tiene efecto.",
      },
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
