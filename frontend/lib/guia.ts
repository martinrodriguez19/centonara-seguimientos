/**
 * La guía de instalación y reparación que se muestra en `/comandos`.
 *
 * **Por qué vive acá y no en `textos.ts`.** La convención del panel es que todo
 * texto que lee una persona va en `textos.ts`. Esto es la excepción, y con
 * motivo: un comando y su explicación son **una sola cosa**. Si mañana el
 * agente cambia una opción, lo que cambia es el comando *y* la línea que dice
 * qué hace. Separarlos garantiza que en algún momento el panel muestre un
 * comando nuevo con la explicación vieja — y alguien lo va a pegar en una
 * Terminal. La cáscara de la página (título, pestañas, botones) sí está en
 * `textos.ts`.
 *
 * **Cómo está armada.** Una pestaña por computadora —Mac, Mac con macOS
 * anterior a 13, Windows— y una cuarta con lo que se hace desde el panel. Las
 * tres de computadora tienen **los mismos nueve pasos en el mismo orden**:
 * antes de empezar, preparar Chrome, instalar, vincular, comprobar, reinstalar
 * desde cero, cuando vence algo, actualizar, y si algo no anda. Quien ya
 * instaló una Mac sabe dónde buscar en Windows.
 *
 * ⚠️ **Cada comando de acá tiene que existir tal cual en el repositorio.** Las
 * fuentes son `instalar.sh`, `desinstalar.sh`, `agente/instalador/*.ps1`,
 * `actualizar.*` y `agente/agente/main.py`. El test `tests/comandos.test.ts`
 * comprueba los invariantes, y `agente/tests/test_instalador.py` que los
 * scripts nombrados existen. Un comando que se copia del panel y no anda es
 * peor que no tenerlo, porque quien lo pega no tiene forma de saber si se
 * equivocó él.
 */

export type Comando = {
  /** Ancla del índice. Único en toda la guía. */
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

export type Paso = {
  /** Ancla. Único dentro del sistema. */
  id: string;
  titulo: string;
  /** Un párrafo de contexto, antes de todo. */
  intro?: string;
  /** Instrucciones que no son comandos: con el mouse, en el teléfono, en el panel. */
  items?: string[];
  comandos?: Comando[];
  /** Lo que hay que leer antes de correr nada del paso. Va destacado, arriba. */
  aviso?: string;
  /** Cómo sigue, o qué se está aceptando. Va al final. */
  pie?: string;
};

export type Problema = {
  sintoma: string;
  queEs: string;
  queHacer: string;
};

export type Sistema = {
  id: "mac" | "mac-viejo" | "windows" | "panel";
  /** El nombre de la pestaña. */
  titulo: string;
  descripcion: string;
  /** Dónde se pegan los comandos. Vacío para la pestaña del panel. */
  donde?: string;
  pasos: Paso[];
  problemas?: Problema[];
};

// ---------------------------------------------------------------------------
// Los comandos que se repiten. Escritos una vez: si cambia la URL o una
// opción, cambia en todos lados.
// ---------------------------------------------------------------------------

const GITHUB = "https://github.com/martinrodriguez19/centonara-seguimientos";
const RAW = "https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main";

/** Dónde queda el proyecto en la computadora del vendedor. Lo fija el instalador. */
const REPO_MAC = "~/centonara-seguimientos";
const REPO_WIN = "~\\centonara-seguimientos";

const EN_EL_AGENTE_MAC = `cd ${REPO_MAC} && uv run --directory agente python -m agente.main`;
const EN_EL_AGENTE_WIN = `cd ${REPO_WIN}; uv run --directory agente python -m agente.main`;

// `--http1.1` va siempre: en macOS 10.15 el curl del sistema contesta 503 a
// GitHub sin él, y el error parece de la red.
const INSTALAR_MAC = `curl -fsSL --http1.1 ${GITHUB}/raw/main/instalar.sh | bash`;
const DESINSTALAR_MAC = `curl -fsSL --http1.1 ${GITHUB}/raw/main/desinstalar.sh | bash`;
const DESINSTALAR_MAC_TODO = `${DESINSTALAR_MAC} -s -- --todo`;

// Bajar y correr con -File, nunca `irm | iex`: con `iex` un `exit` cierra la
// ventana, no se pueden pasar opciones, y el BOM del archivo rompe el
// `param()` (pasó el 25/09/2026: ningún comando de Windows funcionó).
const bajarYCorrer = (script: string, opciones = "") =>
  `irm ${RAW}/agente/instalador/${script} -OutFile "$env:TEMP\\${script}"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\\${script}"${opciones}`;
const INSTALAR_WIN = bajarYCorrer("instalar.ps1");
const SOLO_ACTUALIZADOR_WIN = bajarYCorrer("instalar.ps1", " -SoloActualizador");
const DESINSTALAR_WIN = bajarYCorrer("desinstalar.ps1");
const DESINSTALAR_WIN_TODO = bajarYCorrer("desinstalar.ps1", " -Todo");

const LOGS_WIN = "$env:LOCALAPPDATA\\Centonara\\logs";

// ---------------------------------------------------------------------------
// Lo que se repite entre Mac y Windows, escrito una vez.
// ---------------------------------------------------------------------------

const ANTES_COMUN = [
  "La computadora del vendedor, con Google Chrome instalado y el vendedor cerca: hay que escanear dos QR con su teléfono y explicarle qué hace el sistema.",
  "Una cuenta de Claude por máquina, del Enterprise de la empresa. Una API key no sirve.",
  "El identificador y el token de la máquina, de cuando se dio de alta en el panel (pestaña «En el panel», paso 1). El token se muestra una sola vez: si se perdió, se rota y sale otro.",
  "Que la extensión Claude in Chrome esté permitida por la organización. Si está bloqueada por política, no funciona en ninguna máquina.",
];

const PREPARAR_CHROME = [
  "Instalar la extensión Claude in Chrome en el Chrome que el vendedor usa todos los días, e iniciar sesión con la cuenta de Claude de esta máquina.",
  "Usarla una vez: apretar el ícono de Claude y pedirle cualquier cosa. Con eso queda registrada en la computadora (el deviceId). Si se olvida, el agente lo encuentra solo la primera vez que alguien la use.",
  "Abrir web.whatsapp.com y escanear el QR con el teléfono del vendedor.",
  "Dar el permiso de sitio: ícono de Claude → configuración → permisos de sitios → habilitar web.whatsapp.com. NO es el menú de Chrome («Acceso al sitio: todos los sitios» ya está bien y no es ese): es el de adentro de la extensión. Es el único paso que no se puede automatizar, a propósito.",
];

const INSTALAR_ITEMS = [
  "Pregunta el identificador y el token de la máquina.",
  "Si Claude Code no tiene sesión iniciada, se detiene y dice cómo iniciarla: correr «claude», entrar con la cuenta de esta máquina, salir con /exit, y volver a pegar el mismo comando. En una máquina nueva esto pasa siempre: se pega dos veces y no es una falla.",
  "Al final ofrece vincular el navegador que escribe los mensajes (paso 4). Conviene decir que sí ahí mismo, con el teléfono a mano.",
  "Termina diciendo QUEDÓ AL DÍA con el commit y INSTALACIÓN COMPLETA. Si dice NO QUEDÓ AL DÍA, dice qué falta: hacer eso y volver a pegar el mismo comando. Recién con «completa» se sigue con la pestaña «En el panel», paso 3.",
];

const REINSTALAR_INTRO =
  "Cuando una máquina falla y sigue fallando después de volver a correr el instalador, conviene dejar de arreglarla encima: el instalador conserva el .env, el entorno y lo que sea que esté roto. Reinstalar desde cero son dos comandos —desinstalar, y el instalador de siempre— más activar en el panel.";

const REINSTALAR_ITEMS = [
  "Conviene cuando: la máquina figura sin conexión y el agente no arranca aunque se lo reinicie; hay más de un agente corriendo; el instalador dice NO QUEDÓ AL DÍA dos veces seguidas por lo mismo; o se cambió de vendedor o de cuenta en esa computadora.",
  "Lo que se conserva: la sesión de WhatsApp del navegador que escribe (no hay que volver a escanear ese QR), el login de Claude Code, y el Chrome del vendedor, que no se toca nunca. Lo que se borra: el agente, sus servicios o tareas, el proyecto, el estado y los logs.",
  "En el panel no hay que hacer nada antes: la máquina sigue dada de alta y va a figurar «sin conexión» hasta que se reinstale. Si el token no está anotado, Máquinas → la máquina → ⋯ → Rotar token, y usar el nuevo al instalar.",
  "Después de instalar: comprobar que dijo QUEDÓ AL DÍA, y en el panel ver que la máquina vuelva a estar conectada. Si estaba pausada o desactivada, sigue estándolo.",
];

const VENCEN_INTRO =
  "Tres cosas vencen cada tanto y hay que rehacerlas. No son fallas, y ninguna necesita reinstalar.";

// ---------------------------------------------------------------------------
// Mac
// ---------------------------------------------------------------------------

const MAC: Sistema = {
  id: "mac",
  titulo: "Mac",
  descripcion: "Una Mac con macOS 13 o más nuevo. Es el camino normal.",
  donde: "Los comandos se pegan en la Terminal de esa Mac (Cmd + barra espaciadora, escribir «Terminal», Enter). Ninguno de estos envía mensajes.",
  pasos: [
    {
      id: "antes",
      titulo: "Antes de empezar",
      items: [
        ...ANTES_COMUN,
        "Que la Mac tenga macOS 13 o más nuevo. Con menos, el instalador se detiene y dice que hay que seguir la pestaña «Mac con macOS anterior a 13».",
      ],
      comandos: [
        {
          id: "mac-version",
          titulo: "Ver qué macOS tiene esta Mac",
          comando: "sw_vers -productVersion",
          queHace: "Imprime la versión. 13 o más: seguir acá. 10.15, 11 o 12: pestaña «Mac con macOS anterior a 13».",
        },
      ],
    },
    {
      id: "chrome",
      titulo: "Preparar Chrome (con el mouse)",
      intro: "En el Chrome que el vendedor usa todos los días, en este orden:",
      items: PREPARAR_CHROME,
    },
    {
      id: "instalar",
      titulo: "Instalar",
      intro: "Un comando. Instala lo que falte (uv y Claude Code), baja el programa a ~/centonara-seguimientos, averigua solo los datos de la máquina, deja tres servicios de arranque automático (Chrome, el agente y el actualizador) y lo enciende. Es seguro repetirlo las veces que haga falta.",
      items: INSTALAR_ITEMS,
      comandos: [
        {
          id: "mac-instalar",
          titulo: "Instalar el agente",
          comando: INSTALAR_MAC,
          queHace: "Instala todo, o arregla lo que falte en una Mac ya instalada. Va a pedir el identificador y el token la primera vez; si ya estaban, no pregunta nada.",
          cuando: "En una Mac nueva, y cuando algo se rompió y se quiere arreglar encima. Para actualizar no hace falta: el actualizador lo hace solo, cada hora.",
          aviso: "Si una Mac vieja tenía el proyecto clonado con git (la guía original), el instalador aparta ese .git a ~/.centonara/git-viejo-<fecha> y sigue solo. No hay que hacer nada a mano.",
        },
        {
          id: "mac-claude",
          titulo: "Iniciar sesión en Claude Code",
          comando: "claude",
          queHace: "Abre Claude Code para iniciar sesión con la cuenta de esta máquina (si no la ofrece, escribir /login). Se sale escribiendo /exit.",
          cuando: "Cuando el instalador se detiene en el paso [2/8] pidiéndolo, y cuando el panel avisa que la sesión de Claude Code venció.",
        },
      ],
    },
    {
      id: "vincular",
      titulo: "Vincular el navegador que escribe los mensajes",
      intro: "Para escribir, el sistema usa un navegador aparte del que el vendedor usa todos los días, con su propia sesión de WhatsApp: así nunca le toca las pestañas ni la sesión. Se vincula escaneando un QR: WhatsApp del teléfono → Dispositivos vinculados → Vincular un dispositivo.",
      comandos: [
        {
          id: "mac-vincular",
          titulo: "Vincular el navegador de envío",
          comando: `${EN_EL_AGENTE_MAC} --vincular`,
          queHace: "Abre el navegador dedicado para escanear el QR con el teléfono del vendedor y guarda la sesión.",
          cuando: "El instalador lo ofrece al final. Se corre a mano si se dijo que no, y cuando el panel avisa que esa sesión venció.",
          aviso: "Límite de cuatro dispositivos vinculados por línea: si está lleno hay que liberar uno, y no el del Chrome del vendedor sin avisarle.",
        },
      ],
    },
    {
      id: "comprobar",
      titulo: "Comprobar que quedó bien",
      intro: "El instalador ya lo comprueba al final (QUEDÓ AL DÍA). Esto es para volver a mirarlo después, y para cuando el panel dice «sin conexión» con la Mac prendida.",
      comandos: [
        {
          id: "mac-estado",
          titulo: "¿Están los tres servicios?",
          comando: "launchctl list | grep centonara",
          queHace: "Lista los tres servicios de arranque automático (chrome, agente, actualizador) con su número de proceso y el resultado de la última vez que corrieron. Un 0 en el medio es que salió bien; un guion en vez de número es que no está corriendo.",
        },
        {
          id: "mac-vivo",
          titulo: "¿El agente está vivo?",
          comando: "cat ~/.centonara/estado/vivo.json",
          queHace: "La señal de vida que el agente escribe cada 30 segundos: versión, si está ocupado con un trabajo, y cuándo fue la última. Si «cuando» es de hace más de dos minutos, el agente no está corriendo aunque el servicio figure.",
        },
        {
          id: "mac-diagnostico",
          titulo: "Qué le falta a esta máquina",
          comando: `${EN_EL_AGENTE_MAC} --diagnostico`,
          queHace: "Corre los chequeos, marca en rojo lo que hay que resolver y «n/a» lo que no aplica. No consulta al servidor ni abre ningún navegador. Es lo mismo que se ve en el panel, en Máquinas → la máquina → Chequeos.",
          cuando: "Es el primero que hay que correr cuando algo no anda. No cuesta nada.",
        },
        {
          id: "mac-sonda",
          titulo: "Probar que llega a WhatsApp Web",
          comando: `${EN_EL_AGENTE_MAC} --sonda`,
          queHace: "Contesta lo que el diagnóstico no puede: si la extensión tiene el permiso de sitio y si la sesión de WhatsApp del Chrome del vendedor está iniciada. Cuenta cuántos chats ve y nada más.",
          cuando: "Cuando la generación falla y el diagnóstico da todo verde.",
          aviso: "Abre el navegador y consume saldo de Claude. Tarda minutos.",
        },
        {
          id: "mac-logs",
          titulo: "Ver qué está haciendo el agente",
          comando: "tail -f ~/Library/Logs/centonara/agente.log",
          queHace: "El registro del agente en vivo, línea por línea. Se corta con Control + C.",
        },
        {
          id: "mac-logs-error",
          titulo: "Ver los errores del agente",
          comando: "tail -n 50 ~/Library/Logs/centonara/agente.err",
          queHace: "Las últimas cincuenta líneas de error. Es lo que hay que copiar y mandar cuando algo se rompe.",
        },
      ],
    },
    {
      id: "reinstalar",
      titulo: "Reinstalar desde cero",
      intro: REINSTALAR_INTRO,
      items: REINSTALAR_ITEMS,
      comandos: [
        {
          id: "mac-desinstalar",
          titulo: "1. Desinstalar",
          comando: DESINSTALAR_MAC,
          queHace: "Para y borra los tres servicios, mata el agente (también los que hayan quedado de versiones anteriores) y el navegador de envío, y borra el proyecto, el estado y los logs. Pide escribir SI antes de tocar nada, e imprime el identificador de la máquina para tenerlo a mano.",
          cuando: "Sólo en una máquina que hay que rehacer. No es la forma de detener el agente un rato: para eso está el freno del panel, o «Detener el agente» más abajo.",
          aviso: "Conserva la sesión de WhatsApp del navegador de envío y el login de Claude Code. Se baja de GitHub y no del proyecto de la Mac a propósito: el proyecto puede ser justo lo que está roto.",
        },
        {
          id: "mac-desinstalar-todo",
          titulo: "1b. Desinstalar borrando también la sesión de WhatsApp del motor",
          comando: DESINSTALAR_MAC_TODO,
          queHace: "Lo mismo, y además borra la sesión del navegador que escribe: al reinstalar hay que volver a escanear ese QR.",
          cuando: "Cuando la computadora cambia de vendedor o de línea de WhatsApp.",
        },
        {
          id: "mac-reinstalar",
          titulo: "2. Instalar de nuevo",
          comando: INSTALAR_MAC,
          queHace: "El instalador de siempre. Va a pedir el identificador y el token, y como es una Mac limpia puede pedir iniciar sesión en Claude Code una vez.",
          aviso: "Tiene que terminar en QUEDÓ AL DÍA e INSTALACIÓN COMPLETA. Si no, no está instalada por más que diga cosas en verde arriba.",
        },
      ],
      pie: "Y en el panel: la máquina vuelve sola a «conectada». No hay que darla de alta de nuevo.",
    },
    {
      id: "vence",
      titulo: "Cuando vence algo",
      intro: VENCEN_INTRO,
      items: [
        "La sesión de WhatsApp del vendedor: Chrome muestra el QR. Escanearlo de nuevo, con el teléfono del vendedor. Nada más.",
        "La sesión del navegador que escribe: el panel avisa «venció la sesión del motor». Correr el comando de vincular del paso 4.",
        "La sesión de Claude Code: la corrida falla con «la sesión de Claude Code venció» o «OAuth session expired». En la Terminal de esa Mac: claude, iniciar sesión, /exit. No hace falta reiniciar nada: el próximo trabajo ya la usa.",
      ],
      comandos: [
        {
          id: "mac-claude-vencio",
          titulo: "Volver a iniciar sesión en Claude Code",
          comando: "claude",
          queHace: "Abre Claude Code; si no ofrece iniciar sesión, escribir /login. Entrar con la cuenta de esta máquina y salir con /exit.",
          aviso: "Con el mismo usuario de macOS que corre el agente: es el que inició sesión en esa Mac.",
        },
        {
          id: "mac-vincular-vencio",
          titulo: "Volver a vincular el navegador de envío",
          comando: `${EN_EL_AGENTE_MAC} --vincular`,
          queHace: "Escanear el QR de nuevo. El agente toma la sesión nueva solo: no hay que reiniciarlo.",
        },
      ],
    },
    {
      id: "actualizar",
      titulo: "Actualizar y volver atrás",
      intro: "No hace falta hacer nada: el actualizador corre al iniciar sesión y cada hora, pregunta al panel qué versión toca, la instala y espera que el agente vuelva con ella; si no vuelve, restaura la anterior. Esto es para no esperar, o para ver por qué no pudo.",
      comandos: [
        {
          id: "mac-actualizar",
          titulo: "Actualizar ahora, sin esperar la hora",
          comando: "bash ~/centonara-seguimientos/agente/instalador/actualizar.sh",
          queHace: "Corre el actualizador una vez y dice qué hizo.",
        },
        {
          id: "mac-version-instalada",
          titulo: "Qué versión tiene instalada",
          comando: "cat ~/centonara-seguimientos/agente/VERSION",
          queHace: "El commit y la fecha. Es lo mismo que muestra el panel en la tarjeta de la máquina.",
        },
        {
          id: "mac-log-actualizador",
          titulo: "Por qué no se actualizó",
          comando: "tail -n 40 ~/Library/Logs/centonara/actualizador.log",
          queHace: "Lo último que dijo el actualizador. Cuando el panel marca la máquina «atrasada», acá está el motivo.",
        },
      ],
      pie: "Para volver atrás no se toca ninguna máquina: en el panel, Ajustes → Sistema → Versión del agente, pegar el commit. Todas van a ése en menos de una hora.",
    },
    {
      id: "mantenimiento",
      titulo: "Para quien mantiene el sistema",
      comandos: [
        {
          id: "mac-reiniciar",
          titulo: "Reiniciar el agente",
          comando: "launchctl kickstart -k gui/$(id -u)/com.centonara.agente",
          queHace: "Lo frena y lo vuelve a levantar, con la configuración nueva.",
          cuando: "Después de tocar cualquier cosa del archivo .env.",
        },
        {
          id: "mac-detener",
          titulo: "Detener el agente",
          comando: "launchctl bootout gui/$(id -u)/com.centonara.agente",
          queHace: "Lo frena y no lo vuelve a levantar hasta el próximo inicio de sesión.",
          aviso: "Para frenar todo el sistema está el botón del panel, que es inmediato y queda registrado. Esto es sólo para trabajar sobre una máquina.",
        },
        {
          id: "mac-arrancar",
          titulo: "Volver a arrancar el agente",
          comando: "launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.centonara.agente.plist",
          queHace: "Deshace el comando anterior sin tener que reiniciar la Mac.",
        },
        {
          id: "mac-selectores",
          titulo: "Verificar los selectores de WhatsApp",
          comando: `${EN_EL_AGENTE_MAC} --verificar-selectores --chat +549XXXXXXXXXX`,
          queHace: "Abre el chat de ese número en el navegador dedicado y comprueba, uno por uno, que el encabezado, el campo de escritura y el botón de enviar sigan donde el sistema los busca. Dice exactamente cuál se rompió.",
          cuando: "Cuando WhatsApp cambia por dentro y los mensajes dejan de salir sin un error claro.",
          hueco: "+549XXXXXXXXXX — el número de PRUEBA cuyo chat se abre.",
          aviso: "Se abre un chat real. No envía nada, pero que sea una línea de prueba y no la de un cliente.",
        },
        {
          id: "mac-datos",
          titulo: "Los datos de esta máquina, listos para el .env",
          comando: `${EN_EL_AGENTE_MAC} --datos`,
          queHace: "Averigua qué perfil de Chrome usar y cuál es su deviceId, e imprime las líneas del .env listas para pegar.",
          cuando: "El instalador lo hace solo. A mano, cuando el vendedor cambió de perfil de Chrome.",
        },
      ],
    },
  ],
  problemas: [
    {
      sintoma: "El instalador dice «macOS 13 o más» y se detiene",
      queEs: "La Mac tiene un sistema más viejo y Claude Code no corre ahí tal cual.",
      queHacer: "Seguir la pestaña «Mac con macOS anterior a 13» y después volver a pegar el instalador.",
    },
    {
      sintoma: "El instalador se detiene en [2/8] pidiendo iniciar sesión",
      queEs: "Claude Code no tiene sesión en esta Mac. Es lo normal en una máquina nueva.",
      queHacer: "claude → iniciar sesión → /exit → volver a pegar el mismo comando.",
    },
    {
      sintoma: "Termina en NO QUEDÓ AL DÍA: el agente no dio señal de vida",
      queEs: "Los servicios quedaron, pero el agente se cae al arrancar.",
      queHacer: "Mirar tail -n 50 ~/Library/Logs/centonara/agente.err. Si no se entiende, reinstalar desde cero (paso 6).",
    },
    {
      sintoma: "La máquina figura «sin conexión» en el panel y está prendida",
      queEs: "El agente no está mandando latidos, o no llega al servidor.",
      queHacer: "Paso 5: launchctl list | grep centonara y cat ~/.centonara/estado/vivo.json. Si el servicio está pero la señal es vieja, «Reiniciar el agente». Si sigue, reinstalar desde cero.",
    },
    {
      sintoma: "La corrida falla con «la sesión de Claude Code venció» o «OAuth session expired»",
      queEs: "Una de las tres sesiones que vencen. No es una falla del sistema.",
      queHacer: "En esa Mac: claude, iniciar sesión, /exit. Después, cancelar la corrida frenada en el panel y volver a disparar.",
    },
    {
      sintoma: "El panel avisa «venció la sesión del motor»",
      queEs: "La sesión de WhatsApp del navegador que escribe los mensajes.",
      queHacer: "Correr el comando de vincular (paso 4) con el teléfono del vendedor a mano.",
    },
    {
      sintoma: "«Claude in Chrome requires permission»",
      queEs: "Falta el permiso de sitio de la extensión (paso 2, punto 4). Lo dice el navegador, por eso no aparece en ningún log.",
      queHacer: "Ícono de Claude → configuración → permisos de sitios → web.whatsapp.com.",
    },
    {
      sintoma: "La tarjeta dice «atrasada»",
      queEs: "El actualizador no pudo poner la versión que fija el panel.",
      queHacer: "tail -n 40 ~/Library/Logs/centonara/actualizador.log dice por qué. Si el proyecto era un clon git viejo, volver a correr el instalador lo arregla solo.",
    },
    {
      sintoma: "Una corrida queda «en curso» para siempre",
      queEs: "Una máquina de la corrida está apagada o sin conexión y su trabajo espera.",
      queHacer: "Botón Cancelar corrida en el panel. Lo pendiente se descarta y lo ya generado queda en revisión. Hacerlo ANTES de la hora de la corrida programada: si a esa hora hay una en curso, la programada de ese día se saltea.",
    },
  ],
};

// ---------------------------------------------------------------------------
// Mac con macOS anterior a 13
// ---------------------------------------------------------------------------

const MAC_VIEJO: Sistema = {
  id: "mac-viejo",
  titulo: "Mac con macOS anterior a 13",
  descripcion:
    "Catalina (10.15), Big Sur (11) o Monterey (12). Claude Code pide macOS 13, y en una versión más vieja su instalador aborta con «error 134». Lo que sigue es el rodeo que sí funciona: instalar Claude Code sobre Node 18, y después el instalador normal. Es un puente, no una solución.",
  donde: "Los comandos se pegan en la Terminal de esa Mac (Cmd + barra espaciadora, escribir «Terminal», Enter).",
  pasos: [
    {
      id: "antes",
      titulo: "Antes de empezar",
      aviso:
        "PRIMERO probá la extensión: instalá Claude in Chrome en el Chrome de esa Mac, iniciá sesión y pedile cualquier cosa. Chrome dejó de actualizarse en esos macOS hace más de un año, y si la extensión no anda ahí, nada de lo que sigue sirve. Son cinco minutos y ahorran la tarde entera.",
      items: [
        ...ANTES_COMUN,
        "Si la Mac entra en la lista de las que aceptan macOS 13 (MacBook Pro desde 2017, MacBook Air desde 2018, iMac desde 2017, Mac mini desde 2018, Mac Pro desde 2019), actualizar el sistema es mejor camino que todo esto. Antes: Time Machine, 40 GB libres, enchufada, y una o dos horas sin la máquina.",
      ],
      comandos: [
        {
          id: "viejo-version",
          titulo: "Confirmar qué macOS tiene esta Mac",
          comando: "sw_vers -productVersion",
          queHace: "Si devuelve 13 o más, esta pestaña no aplica: seguir la de «Mac».",
        },
        {
          id: "viejo-modelo",
          titulo: "Ver si conviene actualizar el sistema en vez de esto",
          comando: 'system_profiler SPHardwareDataType | grep -E "Model Name|Model Identifier"',
          queHace: "El modelo y el año, para compararlo con la lista de arriba.",
        },
      ],
    },
    {
      id: "chrome",
      titulo: "Preparar Chrome (con el mouse)",
      intro: "Igual que en cualquier Mac, en el Chrome que el vendedor usa todos los días:",
      items: PREPARAR_CHROME,
    },
    {
      id: "instalar",
      titulo: "Instalar: primero Claude Code sobre Node 18, después el instalador normal",
      intro:
        "Ocho comandos, en orden, y al final el instalador de siempre. Cuando el instalador encuentra «claude» ya instalado no lo toca ni revisa la versión de macOS, así que sigue de largo.",
      comandos: [
        {
          id: "viejo-node",
          titulo: "1. Bajar Node 18",
          comando: "curl -fsSLO https://nodejs.org/dist/v18.20.8/node-v18.20.8.pkg",
          queHace: "Node 18 es la última rama que corre en macOS 10.15. Sirve para dos cosas: Claude Code, y el motor de envío, cuyo navegador también necesita un Node que corra en este sistema. El agente lo detecta solo.",
          aviso: "Si esta Mac no tiene Node, el envío falla con «dyld: Symbol not found» y una referencia a «playwright/driver/node». Ese error significa exactamente esto.",
        },
        {
          id: "viejo-node-instalar",
          titulo: "2. Instalar Node",
          comando: "sudo installer -pkg node-v18.20.8.pkg -target /",
          queHace: "Instala Node y npm en el sistema.",
          aviso: "Pide la contraseña de administrador de esa Mac.",
        },
        {
          id: "viejo-npm-prefijo",
          titulo: "3. Preparar npm para instalar sin sudo",
          comando: "npm config set prefix ~/.npm-global && echo 'export PATH=$HOME/.npm-global/bin:$PATH' >> ~/.zshrc && source ~/.zshrc",
          queHace: "Mueve los paquetes globales de npm a tu carpeta. Sin esto, el paso siguiente falla con «EACCES: permission denied».",
          aviso: "No lo arregles con «sudo npm install -g»: deja archivos de root en tu carpeta y rompe las actualizaciones. Si esa Mac usa bash en vez de zsh, cambiá ~/.zshrc por ~/.bash_profile. Si lo corrés dos veces, sacá la línea repetida del ~/.zshrc.",
        },
        {
          id: "viejo-claude",
          titulo: "4. Instalar la última versión de Claude Code que no es binario nativo",
          comando: "npm install -g @anthropic-ai/claude-code@2.1.100",
          queHace: "Hasta la 2.1.110, Claude Code era un paquete JavaScript sobre Node; el binario nativo —el que aborta— aparece a partir de la 2.1.120. Esta versión tiene «--chrome» y la extensión, que es lo que el agente necesita.",
          aviso: "npm va a avisar que hay una versión nueva de sí mismo. NO le hagas caso: npm 12 exige Node 22, y esta máquina no puede pasar de Node 18.",
        },
        {
          id: "viejo-sin-updates",
          titulo: "5. Frenar la actualización automática",
          comando: `mkdir -p ~/.claude && echo '{"env":{"DISABLE_AUTOUPDATER":"1"}}' > ~/.claude/settings.json`,
          queHace: "Sin esto, Claude Code se reemplaza por una versión nativa en cuestión de horas y vuelve el error 134.",
          aviso: "Si esa Mac ya tiene un ~/.claude/settings.json, este comando lo pisa. En ese caso abrilo y agregale la clave «env» a mano.",
        },
        {
          id: "viejo-verificar",
          titulo: "6. Comprobar que quedó la versión correcta",
          comando: "claude --version",
          queHace: "Tiene que decir 2.1.100. Si dice otra cosa, la actualización automática ya corrió.",
        },
        {
          id: "viejo-sesion",
          titulo: "7. Iniciar sesión",
          comando: "claude",
          queHace: "Se entra con la cuenta de esta máquina y se sale escribiendo /exit.",
        },
        {
          id: "viejo-extension",
          titulo: "8. Comprobar si puede leer el navegador",
          comando: 'claude -p --chrome "decime cuántas pestañas hay abiertas"',
          queHace: "Es la prueba que decide si esta máquina sirve para leer chats. Cuesta centavos y tarda un minuto.",
          aviso: 'Si contesta «crypto is not defined», probá el mismo comando con NODE_OPTIONS=--experimental-global-webcrypto adelante: en Node 18 el servidor MCP corre en un worker y ahí WebCrypto no está expuesto. El agente pone ese flag solo; esto sólo hace falta al probar a mano.',
        },
        {
          id: "viejo-instalar",
          titulo: "9. Cerrar la Terminal, abrir una nueva, y correr el instalador normal",
          comando: INSTALAR_MAC,
          queHace: "El mismo instalador de la pestaña «Mac». La Terminal nueva es para que vea el PATH que dejó el paso 3. Encuentra «claude» instalado y sigue de largo.",
          aviso: "Va a pedir el identificador y el token. Tiene que terminar en QUEDÓ AL DÍA e INSTALACIÓN COMPLETA.",
        },
      ],
      pie: "Estas Macs funcionan completas —leen chats y escriben— sobre tres piezas congeladas: Node 18 (sin parches desde abril de 2025), Chrome 128 y Claude Code 2.1.100. Anthropic puede dejar de aceptar versiones viejas cuando quiera, y ese día esa máquina deja de funcionar sin aviso. Sirve para desbloquear ahora; el reemplazo va en la lista de cosas a pedir.",
    },
    {
      id: "vincular",
      titulo: "Vincular el navegador que escribe los mensajes",
      intro: "Igual que en cualquier Mac: un navegador aparte, con su propia sesión de WhatsApp.",
      comandos: [
        {
          id: "viejo-vincular",
          titulo: "Vincular el navegador de envío",
          comando: `${EN_EL_AGENTE_MAC} --vincular`,
          queHace: "Abre el navegador dedicado para escanear el QR con el teléfono del vendedor.",
        },
      ],
    },
    {
      id: "comprobar",
      titulo: "Comprobar que quedó bien",
      intro: "Los mismos comandos que en la pestaña «Mac», paso 5. Los dos que más se usan:",
      comandos: [
        {
          id: "viejo-estado",
          titulo: "¿Están los tres servicios?",
          comando: "launchctl list | grep centonara",
          queHace: "Los tres servicios con su número de proceso. Un guion en vez de número es que no está corriendo.",
        },
        {
          id: "viejo-vivo",
          titulo: "¿El agente está vivo?",
          comando: "cat ~/.centonara/estado/vivo.json",
          queHace: "La señal de vida del agente. «cuando» de hace más de dos minutos es un agente caído.",
        },
      ],
    },
    {
      id: "reinstalar",
      titulo: "Reinstalar desde cero",
      intro: `${REINSTALAR_INTRO} En una Mac vieja, el desinstalador no toca Node ni Claude Code: al reinstalar no hay que repetir los ocho pasos, sólo el instalador.`,
      items: REINSTALAR_ITEMS,
      comandos: [
        {
          id: "viejo-desinstalar",
          titulo: "1. Desinstalar",
          comando: DESINSTALAR_MAC,
          queHace: "Para y borra los servicios, mata el agente y borra el proyecto, el estado y los logs. Pide escribir SI. Conserva la sesión de WhatsApp del motor, Node y Claude Code.",
        },
        {
          id: "viejo-reinstalar",
          titulo: "2. Instalar de nuevo",
          comando: INSTALAR_MAC,
          queHace: "El instalador de siempre. Encuentra «claude» y sigue de largo. Tiene que terminar en QUEDÓ AL DÍA.",
        },
      ],
    },
    {
      id: "vence",
      titulo: "Cuando vence algo",
      intro: VENCEN_INTRO,
      items: [
        "La sesión de WhatsApp del vendedor: Chrome muestra el QR. Escanearlo de nuevo.",
        "La sesión del navegador que escribe: el panel avisa «venció la sesión del motor». Correr el comando de vincular del paso 4.",
        "La sesión de Claude Code: la corrida falla con «la sesión de Claude Code venció». En la Terminal: claude, iniciar sesión, /exit.",
        "Y una cuarta, sólo acá: si claude --version deja de decir 2.1.100, la actualización automática corrió y volvió el error 134. Repetir los pasos 4, 5 y 6 de instalar.",
      ],
    },
    {
      id: "actualizar",
      titulo: "Actualizar y volver atrás",
      intro: "Igual que en cualquier Mac: el actualizador corre solo cada hora. Lo que se actualiza es el agente; Node y Claude Code quedan congelados a propósito.",
      comandos: [
        {
          id: "viejo-actualizar",
          titulo: "Actualizar ahora, sin esperar la hora",
          comando: "bash ~/centonara-seguimientos/agente/instalador/actualizar.sh",
          queHace: "Corre el actualizador una vez y dice qué hizo.",
        },
        {
          id: "viejo-log-actualizador",
          titulo: "Por qué no se actualizó",
          comando: "tail -n 40 ~/Library/Logs/centonara/actualizador.log",
          queHace: "Lo último que dijo el actualizador.",
        },
      ],
    },
  ],
  problemas: [
    {
      sintoma: "«error 134» o «Abort trap: 6» al instalar Claude Code",
      queEs: "El binario nativo de Claude Code no carga en este macOS. Homebrew y npm bajan el mismo binario, así que ninguno lo resuelve.",
      queHacer: "Los pasos 1 a 8 de instalar, en orden.",
    },
    {
      sintoma: "«EACCES: permission denied» en npm install",
      queEs: "npm quiere escribir en /usr/local/lib/node_modules, que es de root.",
      queHacer: "El paso 3 (prefijo de npm). No usar sudo.",
    },
    {
      sintoma: "«dyld: Symbol not found» con «playwright/driver/node»",
      queEs: "El motor de envío intenta usar el Node que trae adentro, compilado para macOS 11 o más nuevo.",
      queHacer: "Instalar Node 18 (pasos 1 y 2): el agente lo detecta y lo usa solo.",
    },
    {
      sintoma: "«crypto is not defined» al probar la extensión",
      queEs: "En Node 18 el servidor de la extensión corre en un worker sin WebCrypto.",
      queHacer: "Probar con NODE_OPTIONS=--experimental-global-webcrypto adelante. El agente ya lo pone solo.",
    },
    {
      sintoma: "claude --version dejó de decir 2.1.100",
      queEs: "La actualización automática corrió y volvió a poner el binario nativo.",
      queHacer: "Repetir los pasos 4, 5 y 6 de instalar.",
    },
  ],
};

// ---------------------------------------------------------------------------
// Windows
// ---------------------------------------------------------------------------

const WINDOWS: Sistema = {
  id: "windows",
  titulo: "Windows",
  descripcion: "Una PC con Windows 10 u 11. La Parte «En el panel» es la misma que para Mac.",
  donde: "Los comandos se pegan en PowerShell (tecla Windows, escribir «PowerShell», Enter). NO hace falta «como administrador». Ninguno de estos envía mensajes.",
  pasos: [
    {
      id: "antes",
      titulo: "Antes de empezar",
      items: [
        ...ANTES_COMUN,
        "Que la PC no se suspenda ni hiberne: para la corrida programada de las 17 tiene que estar prendida y con sesión iniciada en Windows. El comando de energía está en el paso 3.",
        "El antivirus puede abrir el binario de Claude Code recién bajado justo cuando el instalador lo quiere mover («Failed to download binary … está siendo utilizado en otro proceso»). Se resuelve repitiendo el comando.",
      ],
    },
    {
      id: "chrome",
      titulo: "Preparar Chrome (con el mouse)",
      intro: "En el Chrome que el vendedor usa todos los días, en este orden:",
      items: PREPARAR_CHROME,
    },
    {
      id: "instalar",
      titulo: "Instalar",
      intro:
        "Un comando. Instala lo que falte (uv y Claude Code), baja el programa a ~\\centonara-seguimientos, averigua solo los datos de la máquina, registra tres tareas programadas (Chrome al iniciar sesión, el agente, y el actualizador) y lo enciende. Es seguro repetirlo las veces que haga falta.",
      items: INSTALAR_ITEMS,
      comandos: [
        {
          id: "win-instalar",
          titulo: "Instalar el agente",
          comando: INSTALAR_WIN,
          queHace: "Baja el instalador a un archivo temporal y lo corre. Instala todo, o arregla lo que falte en una PC ya instalada. Va a pedir el identificador y el token la primera vez.",
          cuando: "En una PC nueva, y cuando algo se rompió y se quiere arreglar encima. Para actualizar no hace falta: el actualizador lo hace solo, cada hora.",
          aviso: "Es una sola línea, con el punto y coma en el medio. Se baja a un archivo y se corre con -File a propósito: el «irm … | iex» de la documentación vieja falla en una PC nueva (cierra la ventana en el primer error y no lee bien el archivo). Si la PC tenía el proyecto clonado con git, el instalador aparta ese .git y sigue solo.",
        },
        {
          id: "win-claude",
          titulo: "Iniciar sesión en Claude Code",
          comando: "claude",
          queHace: "Abre Claude Code para iniciar sesión con la cuenta de esta máquina (si no la ofrece, escribir /login). Se sale escribiendo /exit.",
          cuando: "Cuando el instalador se detiene en el paso [2/8] pidiéndolo, y cuando el panel avisa que la sesión de Claude Code venció.",
        },
        {
          id: "win-energia",
          titulo: "Que la PC nunca se suspenda ni hiberne",
          comando: "powercfg /change standby-timeout-ac 0; powercfg /change standby-timeout-dc 0; powercfg /change hibernate-timeout-ac 0; powercfg /change hibernate-timeout-dc 0; powercfg /change monitor-timeout-ac 15; powercfg /change monitor-timeout-dc 15",
          queHace: "Aplica al plan de energía activo: no se suspende, no hiberna, y la pantalla se apaga sola a los 15 minutos (eso no afecta al agente).",
          aviso: "Si la PC está en un dominio con políticas de energía, puede volver atrás. Apagar la PC sigue siendo manual.",
        },
        {
          id: "win-tapa",
          titulo: "Sólo notebooks: que cerrar la tapa no suspenda",
          comando: "powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0; powercfg /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0; powercfg /setactive SCHEME_CURRENT",
          queHace: "Con la tapa cerrada la notebook sigue prendida y el agente sigue trabajando.",
        },
        {
          id: "win-solo-actualizador",
          titulo: "Una PC instalada a mano que ya funciona: agregarle sólo la actualización automática",
          comando: SOLO_ACTUALIZADOR_WIN,
          queHace: "Registra únicamente la tarea del actualizador y la corre una vez. No toca el .env, ni cómo arranca el agente, ni Chrome.",
          cuando: "Para una máquina instalada antes de que existiera el actualizador y que anda bien. Si el proyecto está en otra carpeta, agregar -Repo \"C:\\la\\carpeta\" al final.",
        },
      ],
    },
    {
      id: "vincular",
      titulo: "Vincular el navegador que escribe los mensajes",
      intro: "Lo mismo que en Mac: un navegador aparte, con su propia sesión de WhatsApp. Se vincula escaneando un QR: WhatsApp del teléfono → Dispositivos vinculados → Vincular un dispositivo.",
      aviso: "En Windows el circuito de envío no está verificado todavía: la PC en producción deja borradores con la extensión, que es el circuito que no lo necesita. Antes de habilitar envíos desde una PC, correr vincular y verificar selectores ahí y mirar que pasen.",
      comandos: [
        {
          id: "win-vincular",
          titulo: "Vincular el navegador de envío",
          comando: `${EN_EL_AGENTE_WIN} --vincular`,
          queHace: "Abre el navegador dedicado para escanear el QR con el teléfono del vendedor y guarda la sesión.",
          cuando: "El instalador lo ofrece al final. Se corre a mano si se dijo que no, y cuando el panel avisa que esa sesión venció.",
        },
      ],
    },
    {
      id: "comprobar",
      titulo: "Comprobar que quedó bien",
      intro: "El instalador ya lo comprueba al final (QUEDÓ AL DÍA). Esto es para volver a mirarlo después, y para cuando el panel dice «sin conexión» con la PC prendida.",
      comandos: [
        {
          id: "win-estado",
          titulo: "¿Están las tres tareas, y corriendo?",
          comando: 'Get-ScheduledTask "Centonara Agente","Centonara Chrome","Centonara Actualizador" | Select-Object TaskName, State',
          queHace: "Las tres tareas con su estado. «Centonara Agente» tiene que decir Running. Las otras dos dicen Ready cuando no están corriendo en ese momento, y está bien.",
          aviso: "Después de una actualización el agente se relanza por su cuenta y la tarea puede quedar en Ready aunque el agente esté vivo: lo que decide es la señal de vida, el comando siguiente.",
        },
        {
          id: "win-vivo",
          titulo: "¿El agente está vivo?",
          comando: "Get-Content ~\\.centonara\\estado\\vivo.json",
          queHace: "La señal de vida que el agente escribe cada 30 segundos: versión, si está ocupado, y cuándo fue la última. Si «cuando» es de hace más de dos minutos, el agente no está corriendo.",
        },
        {
          id: "win-arrancar",
          titulo: "Levantar el agente si no está corriendo",
          comando: 'Start-ScheduledTask "Centonara Agente"',
          queHace: "Arranca la tarea del agente. Al minuto tiene que aparecer la señal de vida.",
          aviso: "No arrancar el agente a mano con «python -m agente.main» mientras exista la tarea: queda atado a la ventana de PowerShell y, si la tarea ya corre, hay dos agentes con el mismo token. Si hay dudas de cuántos hay, reinstalar desde cero los mata a todos.",
        },
        {
          id: "win-diagnostico",
          titulo: "Qué le falta a esta máquina",
          comando: `${EN_EL_AGENTE_WIN} --diagnostico`,
          queHace: "Corre los chequeos, marca en rojo lo que hay que resolver y «n/a» lo que no aplica. Es lo mismo que se ve en el panel, en Máquinas → la máquina → Chequeos.",
          cuando: "Es el primero que hay que correr cuando algo no anda. No cuesta nada.",
        },
        {
          id: "win-sonda",
          titulo: "Probar que llega a WhatsApp Web",
          comando: `${EN_EL_AGENTE_WIN} --sonda`,
          queHace: "Si la extensión tiene el permiso de sitio y si la sesión de WhatsApp del Chrome del vendedor está iniciada. Cuenta cuántos chats ve y nada más.",
          aviso: "Abre el navegador y consume saldo de Claude. Tarda minutos.",
        },
        {
          id: "win-logs",
          titulo: "Qué dice el agente",
          comando: `Get-Content ${LOGS_WIN}\\agente.log -Tail 40`,
          queHace: "Las últimas cuarenta líneas del registro del agente. Es lo que hay que copiar y mandar cuando algo se rompe.",
        },
      ],
    },
    {
      id: "reinstalar",
      titulo: "Reinstalar desde cero",
      intro: `${REINSTALAR_INTRO} En Windows hay un motivo más: cuando llega una versión nueva, el agente se relanza por su cuenta y la tarea deja de ser su dueña; si después alguien vuelve a correr el instalador o arranca la tarea, quedan dos agentes con el mismo token. El desinstalador los mata a todos.`,
      items: REINSTALAR_ITEMS,
      comandos: [
        {
          id: "win-desinstalar",
          titulo: "1. Desinstalar",
          comando: DESINSTALAR_WIN,
          queHace: "Para y borra las tres tareas, mata todo agente que esté corriendo (también los relanzados) y el navegador de envío, y borra el proyecto, el estado y los logs. Pide escribir SI antes de tocar nada, e imprime el identificador de la máquina.",
          cuando: "Sólo en una PC que hay que rehacer. No es la forma de detener el agente un rato: para eso está el freno del panel.",
          aviso: "Conserva la sesión de WhatsApp del navegador de envío y el login de Claude Code. Se baja de GitHub y no del proyecto de la PC a propósito: el proyecto puede ser justo lo que está roto.",
        },
        {
          id: "win-desinstalar-todo",
          titulo: "1b. Desinstalar borrando también la sesión de WhatsApp del motor",
          comando: DESINSTALAR_WIN_TODO,
          queHace: "Lo mismo, y además borra la sesión del navegador que escribe: al reinstalar hay que volver a escanear ese QR.",
          cuando: "Cuando la computadora cambia de vendedor o de línea de WhatsApp.",
        },
        {
          id: "win-reinstalar",
          titulo: "2. Instalar de nuevo",
          comando: INSTALAR_WIN,
          queHace: "El instalador de siempre. Va a pedir el identificador y el token, y como es una PC limpia puede pedir iniciar sesión en Claude Code una vez.",
          aviso: "Tiene que terminar en QUEDÓ AL DÍA e INSTALACIÓN COMPLETA. Si no, no está instalada por más que diga cosas en verde arriba.",
        },
      ],
      pie: "Y en el panel: la máquina vuelve sola a «conectada». No hay que darla de alta de nuevo.",
    },
    {
      id: "vence",
      titulo: "Cuando vence algo",
      intro: VENCEN_INTRO,
      items: [
        "La sesión de WhatsApp del vendedor: Chrome muestra el QR. Escanearlo de nuevo, con el teléfono del vendedor.",
        "La sesión del navegador que escribe: el panel avisa «venció la sesión del motor». Correr el comando de vincular del paso 4.",
        "La sesión de Claude Code: la corrida falla con «la sesión de Claude Code venció» o «OAuth session expired». En PowerShell: claude, iniciar sesión, /exit. No hace falta reiniciar nada.",
      ],
      comandos: [
        {
          id: "win-claude-vencio",
          titulo: "Volver a iniciar sesión en Claude Code",
          comando: "claude",
          queHace: "Abre Claude Code; si no ofrece iniciar sesión, escribir /login. Entrar con la cuenta de esta máquina y salir con /exit.",
          aviso: "Con el mismo usuario de Windows que corre las tareas: el que inició sesión en esa PC.",
        },
        {
          id: "win-vincular-vencio",
          titulo: "Volver a vincular el navegador de envío",
          comando: `${EN_EL_AGENTE_WIN} --vincular`,
          queHace: "Escanear el QR de nuevo. El agente toma la sesión nueva solo.",
        },
      ],
    },
    {
      id: "actualizar",
      titulo: "Actualizar y volver atrás",
      intro: "No hace falta hacer nada: el actualizador corre al iniciar sesión y cada hora. Cuando deja una versión nueva, el agente se cierra solo y vuelve a levantarse al minuto: es normal verlo «sin conexión» un minuto en el panel después de una actualización.",
      comandos: [
        {
          id: "win-actualizar",
          titulo: "Actualizar ahora, sin esperar la hora",
          comando: "powershell -ExecutionPolicy Bypass -File ~\\centonara-seguimientos\\agente\\instalador\\actualizar.ps1",
          queHace: "Corre el actualizador una vez y dice qué hizo.",
        },
        {
          id: "win-version-instalada",
          titulo: "Qué versión tiene instalada",
          comando: "Get-Content ~\\centonara-seguimientos\\agente\\VERSION",
          queHace: "El commit y la fecha. Es lo mismo que muestra el panel en la tarjeta de la máquina.",
        },
        {
          id: "win-log-actualizador",
          titulo: "Por qué no se actualizó",
          comando: `Get-Content ${LOGS_WIN}\\actualizador.log -Tail 40`,
          queHace: "Lo último que dijo el actualizador. Cuando el panel marca la máquina «atrasada», acá está el motivo.",
        },
      ],
      pie: "Para volver atrás no se toca ninguna máquina: en el panel, Ajustes → Sistema → Versión del agente, pegar el commit. Todas —Mac y Windows— van a ése en menos de una hora.",
    },
    {
      id: "mantenimiento",
      titulo: "Para quien mantiene el sistema",
      comandos: [
        {
          id: "win-selectores",
          titulo: "Verificar los selectores de WhatsApp",
          comando: `${EN_EL_AGENTE_WIN} --verificar-selectores --chat +549XXXXXXXXXX`,
          queHace: "Abre el chat de ese número en el navegador dedicado y comprueba, uno por uno, que el encabezado, el campo de escritura y el botón de enviar sigan donde el sistema los busca.",
          hueco: "+549XXXXXXXXXX — el número de PRUEBA cuyo chat se abre.",
          aviso: "Se abre un chat real. No envía nada, pero que sea una línea de prueba y no la de un cliente.",
        },
        {
          id: "win-datos",
          titulo: "Los datos de esta máquina, listos para el .env",
          comando: `${EN_EL_AGENTE_WIN} --datos`,
          queHace: "Averigua qué perfil de Chrome usar y cuál es su deviceId, e imprime las líneas del .env listas para pegar.",
        },
      ],
    },
  ],
  problemas: [
    {
      sintoma: "«La expresión de asignación no es válida» en la línea 37",
      queEs: "Se pegó el comando viejo, «irm … | iex». Ese camino no funciona.",
      queHacer: "Pegar el comando del paso 3 tal cual: baja el archivo y lo corre con -File.",
    },
    {
      sintoma: "El instalador se detiene en [2/8] pidiendo iniciar sesión",
      queEs: "Claude Code no tiene sesión en esta PC. Es lo normal en una máquina nueva.",
      queHacer: "claude → iniciar sesión → /exit → volver a pegar el mismo comando.",
    },
    {
      sintoma: "«Failed to download binary … está siendo utilizado en otro proceso»",
      queEs: "El antivirus escaneó el binario de Claude Code justo cuando el instalador lo quería mover.",
      queHacer: "Volver a pegar el instalador. Si insiste: Remove-Item \"$HOME\\.claude\\downloads\" -Recurse -Force, cerrar la ventana, abrir otra y de nuevo el instalador.",
    },
    {
      sintoma: "Termina en NO QUEDÓ AL DÍA: el agente no dio señal de vida",
      queEs: "Las tareas quedaron, pero el agente se cae al arrancar.",
      queHacer: `Mirar Get-Content ${LOGS_WIN}\\agente.log -Tail 40. Si no se entiende, reinstalar desde cero (paso 6).`,
    },
    {
      sintoma: "La máquina figura «sin conexión» en el panel y está prendida",
      queEs: "El agente no está mandando latidos, o la PC se suspendió.",
      queHacer: "Paso 5: ver las tareas y la señal de vida. Si la tarea dice Ready y la señal es vieja, Start-ScheduledTask. Si se suspende, el comando de energía del paso 3.",
    },
    {
      sintoma: "Hay dos agentes corriendo (dos veces el mismo trabajo, o la tarea no lo frena)",
      queEs: "Un agente relanzado después de una actualización, más otro que arrancó la tarea o alguien a mano.",
      queHacer: "Reinstalar desde cero (paso 6): el desinstalador los mata a todos.",
    },
    {
      sintoma: "La corrida falla con «la sesión de Claude Code venció» o «OAuth session expired»",
      queEs: "Una de las tres sesiones que vencen. No es una falla del sistema.",
      queHacer: "En esa PC: claude, iniciar sesión, /exit. Después, cancelar la corrida frenada en el panel y volver a disparar.",
    },
    {
      sintoma: "Una alerta dice que la máquina «falla todo lo que toma»",
      queEs: "Sus últimos trabajos terminaron en error, con el motivo en la alerta.",
      queHacer: "Si el motivo habla de Chrome o del deviceId: abrir Chrome con el perfil de WhatsApp y usar la extensión una vez. Si habla de la sesión de Claude: paso 7.",
    },
    {
      sintoma: "La tarjeta dice «atrasada»",
      queEs: "El actualizador no pudo poner la versión que fija el panel.",
      queHacer: `Get-Content ${LOGS_WIN}\\actualizador.log -Tail 40 dice por qué.`,
    },
    {
      sintoma: "Una corrida queda «en curso» para siempre",
      queEs: "Una máquina de la corrida está apagada o sin conexión y su trabajo espera.",
      queHacer: "Botón Cancelar corrida en el panel. Hacerlo ANTES de la hora de la corrida programada: si a esa hora hay una en curso, la programada de ese día se saltea.",
    },
  ],
};

// ---------------------------------------------------------------------------
// En el panel (igual para todas las computadoras)
// ---------------------------------------------------------------------------

const PANEL: Sistema = {
  id: "panel",
  titulo: "En el panel",
  descripcion: "Lo que se hace desde acá, sin la computadora del vendedor delante. Es igual para Mac y Windows: antes de instalar, y después.",
  pasos: [
    {
      id: "alta",
      titulo: "1. Antes de instalar: dar de alta la máquina",
      intro: "Máquinas → Dar de alta una máquina.",
      items: [
        "Identificador: minúsculas, números y guiones (mac-rocio, pc-sofia). No «Mac de Rocío».",
        "Nombre del vendedor: acá sí, con mayúsculas y acentos.",
        "Tope de mensajes por día: con una línea nueva conviene empezar bajo.",
        "El token se muestra UNA sola vez. Anotar juntos el identificador y el token: son las dos únicas cosas que la computadora va a preguntar. Si se pierde, ⋯ → Rotar token y sale otro.",
        "La máquina nace inactiva. Instalar no es activar.",
      ],
    },
    {
      id: "config",
      titulo: "2. Antes de la primera corrida: la configuración",
      intro: "Una sola vez por empresa, no por máquina. En Ajustes:",
      items: [
        "Mensajes → Indicaciones para redactar: qué vende la empresa, promociones, tono. Cuanto más concreto, mejores los borradores.",
        "Seguridad → Destinos permitidos: sólo se le escribe a los números de la lista, y vacía significa a nadie. Para las pruebas, dos o tres números propios. Abrir a todos se hace escribiendo ABRIR, y queda registrado.",
        "Qué chats y cuántos: los más recientes (día a día) o el barrido del historial (recuperar clientes viejos). Para el barrido, empezar con 10 chats por máquina.",
        "Envío y horarios: el horario en que pueden salir mensajes (de fábrica 9 a 19, lunes a viernes), la corrida automática (apagada de fábrica) y el envío automático (apagado de fábrica). Si se espera que corra sola a las 17, hay que prender la corrida automática, y a esa hora las computadoras tienen que estar prendidas.",
      ],
    },
    {
      id: "encender",
      titulo: "3. Después de instalar: encender",
      items: [
        "Registrar el consentimiento: el sistema escribe desde la línea del vendedor, con su nombre; eso tiene que estar hablado y aceptado. Máquinas → la máquina → ⋯ → Registrar consentimiento. Sin esto no se le encola ningún envío.",
        "Activar: en la misma máquina, Activar. Recién ahí toma trabajo.",
        "Correr diagnóstico (Inicio): pregunta a cada máquina si está lista. Es gratis y no toca ningún chat. La máquina tiene que quedar «conectada» y sin chequeos fallando.",
        "Generar seguimientos (Inicio): la primera corrida. Lee los chats, redacta, y deja cada mensaje como borrador en su chat. Nada se envía, salvo que el envío automático esté prendido.",
        "Pocos borradores o ninguno no es una falla: casi siempre es la lista de destinos permitidos. Está haciendo lo que se le pidió.",
      ],
    },
    {
      id: "reinstalar",
      titulo: "4. Cuando hay que reinstalar una computadora",
      items: [
        "No hay que dar de baja la máquina ni darla de alta de nuevo: sigue existiendo, y figura «sin conexión» mientras está desinstalada.",
        "Si el token no está anotado: ⋯ → Rotar token, y usar el nuevo al instalar. El viejo deja de servir en ese momento.",
        "Si la máquina estaba a mitad de una corrida: Cancelar corrida en el inicio, antes de desinstalar. Si no, la corrida queda «en curso» esperándola.",
        "Después de instalar: la máquina vuelve sola a «conectada». Si estaba pausada o desactivada, sigue estándolo hasta que se cambie.",
      ],
    },
    {
      id: "errores",
      titulo: "5. Lo que el panel avisa, y qué hacer",
      intro: "Análisis → Errores y avisos junta todo. Los que más se repiten:",
      items: [
        "«X no responde» (urgente): tiene trabajo esperando y no da señales hace más de 10 minutos. Fijarse si la computadora está prendida y con sesión iniciada; en Windows, si no se suspendió.",
        "«Venció la sesión del motor de X»: el navegador que escribe perdió la sesión de WhatsApp. En esa computadora, vincular (pestaña de su sistema, paso 4).",
        "«X está a medias»: un chequeo falla. Máquinas → X → Chequeos dice cuál y qué hacer.",
        "«X falla todo lo que toma»: sus últimos trabajos fallaron, con el motivo en la alerta. Si habla de la sesión de Claude Code: en esa computadora, claude, iniciar sesión, /exit.",
        "«X corre otra versión» / «atrasada»: el actualizador no pudo. En esa computadora, el log del actualizador dice por qué.",
        "«Una corrida se frenó sola»: los primeros envíos fallaron. Mirar por qué antes de reanudar.",
      ],
    },
  ],
};

export const sistemas: Sistema[] = [MAC, MAC_VIEJO, WINDOWS, PANEL];

/** Todos los comandos de la guía, planos: para el test y para el índice. */
export const todosLosComandos = (): Comando[] =>
  sistemas.flatMap((s) => s.pasos.flatMap((p) => p.comandos ?? []));
