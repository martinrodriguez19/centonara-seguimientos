/**
 * Todos los textos de la interfaz, en un solo archivo (08 §3).
 *
 * El cliente va a querer cambiar palabras, y cuando lo pida no queremos salir a
 * buscarlas por veinte componentes. Regla: si un texto lo lee una persona, vive
 * acá. Los mensajes de error técnicos que sólo van al log, no.
 *
 * `as const` para que los tipos sean los literales y no `string`: si alguien
 * borra una clave que está en uso, lo dice el typecheck y no el navegador.
 */
export const textos = {
  app: {
    titulo: "Seguimiento Comercial",
    descripcion: "Panel de seguimiento comercial.",
  },

  login: {
    // El único lugar de todo el panel donde aparece la marca. Adentro, el
    // encabezado dice qué es la herramienta, no de quién es.
    marca: "centonara",
    marcaBajada: "pietra e porfido",
    titulo: "Seguimiento Comercial",
    subtitulo: "Ingresá la contraseña del panel.",
    clave: "Contraseña",
    entrar: "Entrar",
    entrando: "Entrando…",
    incorrecta: "Contraseña incorrecta.",
    sinBackend: "No se pudo hablar con el servidor. Probá de nuevo en un momento.",
  },

  // Las dos pantallas que aparecen cuando algo sale mal. Escritas para quien
  // vende materiales, no para quien programó: nada de "excepción" ni "cliente".
  error: {
    titulo: "Esta pantalla se rompió",
    detalle:
      "No es algo que hayas hecho mal. Probá de nuevo; si vuelve a pasar, avisale al equipo técnico con el código de abajo.",
    reintentar: "Probar de nuevo",
    codigo: "Código",
  },

  noEncontrado: {
    titulo: "Esta dirección no existe",
    detalle:
      "Puede ser un enlace viejo, o una corrida que ya no está. Desde el panel llegás a todo lo que hay.",
    volver: "Ir al panel",
  },

  // El backend caído no es un error del panel: es un dato que la pantalla tiene
  // que poder mostrar. El proxy ya lo distingue con su propio código.
  sinBackend: {
    titulo: "El servidor no responde",
    detalle:
      "El panel está bien; el que no contesta es el servidor. Suele durar menos de un minuto. No hace falta que toques nada más.",
    reintentar: "Volver a intentar",
  },

  panel: {
    titulo: "Panel",
    salir: "Salir",
    maquinas: "Máquinas",
    sinMaquinas: "Todavía no hay ninguna máquina dada de alta.",
    enviadosHoy: "Mensajes enviados hoy",
    corridas: "Corridas",
    configuracion: "Configuración",
    historial: "Historial",
    comandos: "Comandos",
  },

  // La banda de modo. Es lo primero que se lee y tiene que dejar claro en dos
  // segundos si el sistema puede alcanzar a un cliente real.
  modo: {
    prueba: "MODO PRUEBA",
    pruebaDetalle:
      "El sistema no le puede escribir a nadie fuera de la lista de destinos permitidos.",
    real: "ENVÍO REAL HABILITADO",
    realDetalle: "El sistema puede escribirle a cualquier contacto de los chats leídos.",
  },

  killSwitch: {
    frenar: "Frenar todo",
    reanudar: "Reanudar",
    frenado: "Sistema frenado",
    frenadoDetalle: "Ninguna máquina está recibiendo trabajo.",
    confirmarTitulo: "Frenar todo el sistema",
    confirmar: "Las máquinas van a dejar de recibir trabajo en menos de 10 segundos.",
    // Que frenar es reversible tiene que estar escrito: si alguien duda de eso,
    // duda justo cuando no hay tiempo para dudar.
    confirmarNota: "Se puede reanudar en cualquier momento, con un solo click.",
    avisoFrenado: "Sistema frenado. Las máquinas dejan de recibir trabajo.",
    avisoReanudado: "Sistema reanudado.",
    avisoFallo: "No se pudo cambiar el estado del sistema. Probá de nuevo.",
  },

  boton: {
    disparar: "Generar seguimientos",
    disparando: "Arrancando…",
    diagnostico: "Correr diagnóstico",
    diagnosticoAyuda: "Revisa que las máquinas estén listas. No lee ningún chat ni cuesta nada.",
    sinMaquinas: "No hay ninguna máquina activa y sin pausar.",
    enCurso: "Corrida en curso",
    progreso: (hechos: number, total: number) => `${hechos} de ${total} listos`,
    cancelar: "Cancelar corrida",
    confirmarCancelarTitulo: "Cancelar la corrida en curso",
    confirmarCancelar:
      "Lo que todavía no se hizo se descarta. Lo que ya se generó queda en revisión y no se pierde.",

    // Generar cuesta dinero y abre el navegador en la máquina de cada
    // vendedor: la confirmación dice cuánto trabajo se está pidiendo, porque
    // "¿confirmás?" a secas no deja decidir nada.
    generarConfirmarTitulo: "Vas a generar seguimientos",
    generarConfirmarDetalle: (maquinas: number, chats: number) =>
      `${maquinas === 1 ? "1 máquina va" : `${maquinas} máquinas van`} a abrir WhatsApp y leer ` +
      `hasta ${chats} chats ${maquinas === 1 ? "" : "cada una"}`.trim() +
      ". Tarda unos minutos y tiene costo por chat leído.",
    generarConfirmarNota:
      "Sólo se redactan borradores de los números que estén en destinos permitidos. Nada se envía todavía.",
    generarConfirmar: "Generar",
    revisarBorradores: "Revisar borradores",
  },

  maquina: {
    online: "Conectada",
    offline: "Sin conexión",
    pausada: "Pausada",
    degradada: "Degradada",
    inactiva: "Inactiva",
    sinConsentimiento: "Sin consentimiento registrado",
    sinConsentimientoDetalle:
      "No se le van a encolar envíos hasta que conste que sabe que el sistema escribe en su nombre.",
    registrarConsentimiento: "Registrar consentimiento",
    confirmarConsentimientoTitulo: "Registrar el consentimiento",
    confirmarConsentimiento: (nombre: string) =>
      `¿${nombre} ya tuvo la conversación y aceptó que el sistema escriba desde su línea, con su nombre?`,
    confirmarConsentimientoNota:
      "Queda registrado con fecha en la auditoría. Es lo único que habilita a esta máquina a enviar.",

    activar: "Activar",
    desactivar: "Desactivar",
    // Pausar por hoy es del vendedor sobre su propia máquina; activar es del
    // dueño. Son dos decisiones de dos personas, por eso son dos botones.
    pausarPorHoy: "Pausar por hoy",
    reanudarHoy: "Quitar la pausa",
    rotarToken: "Rotar token",
    darDeBaja: "Dar de baja",
    confirmarBajaTitulo: (nombre: string) => `Dar de baja ${nombre}`,
    confirmarBaja:
      "Se borra la máquina y se revoca su token. Para volver a usarla hay que darla de alta de nuevo e instalarla otra vez.",

    ultimoLatido: "Último latido",
    nunca: "nunca",
    version: "Versión",
    topeDiario: "Tope de mensajes por día",
    topeDiarioAyuda: "Lo que protege la línea de este vendedor en particular.",

    fallando: "Hay algo que resolver en esta máquina",
    verChequeos: "Ver el detalle",
    chequeosDe: "Estado de",
    chequeoOk: "Bien",
    chequeoFalla: "Hay que resolverlo",
    chequeoNoAplica: "No aplica",

    avisoActivada: "Máquina activada.",
    avisoDesactivada: "Máquina desactivada. Deja de recibir trabajo.",
    avisoPausada: "Pausada hasta mañana.",
    avisoDespausada: "Pausa quitada.",
    avisoTope: "Tope diario actualizado.",
    avisoConsentimiento: "Consentimiento registrado.",
    avisoBaja: (nombre: string) => `${nombre} se dio de baja y su token quedó revocado.`,
    avisoFallo: "No se pudo guardar el cambio. Probá de nuevo.",
  },

  revision: {
    titulo: "Revisar borradores",
    volver: "Volver al panel",
    cargando: "Cargando…",
    validando: "Pasando por las reglas…",
    sinMensajes: "Esta corrida todavía no generó borradores.",

    retenidos: "Necesitan tu decisión",
    retenidosAyuda:
      "Algo llamó la atención en estos chats. Miralos antes de que salgan.",
    listos: "Listos para salir",
    descartados: "No van a salir",
    descartadosAyuda: "El sistema los frenó. No hay nada que decidir.",

    editar: "Editar",
    guardar: "Guardar",
    cancelar: "Cancelar",
    vetar: "Frenar",
    liberar: "Liberar",
    vetado: "Frenado",

    // El botón dice el número: "enviar" a secas no deja claro cuántos salen.
    enviar: (cuantos: number) =>
      cuantos === 1 ? "Enviar 1 mensaje" : `Enviar ${cuantos} mensajes`,
    enviando: "Encolando…",
    nadaQueEnviar: "No hay ningún mensaje listo para salir.",
    enviarAyuda:
      "Salen espaciados, en orden aleatorio. Los primeros tres salen y el sistema espera diez minutos antes de soltar el resto.",

    // --- Los dos modos de envío -------------------------------------------
    //
    // La ambigüedad más cara que puede tener esta pantalla es no saber si lo
    // que salió fue de verdad. Por eso el modo se dice ANTES de apretar, en el
    // propio botón, y DESPUÉS en la confirmación.
    modoTitulo: "¿Cómo querés enviarlos?",
    modoPrueba: "Ensayo",
    modoPruebaDetalle:
      "Hace todo el recorrido —abre el chat, verifica el contacto, escribe el texto— pero no aprieta enviar. Nadie recibe nada.",
    modoReal: "Enviar de verdad",
    modoRealDetalle:
      "Los mensajes salen de la línea de cada vendedor y llegan a los contactos. No se puede deshacer.",
    modoRealSinDestinos:
      "No se puede enviar de verdad: la lista de destinos permitidos está vacía, y vacía significa a nadie. Se abre desde Configuración.",

    // Misma fricción que liberar retenidos en lote: escribir el número obliga
    // a leerlo, que es todo lo que hace falta.
    enviarRealConfirmar: (cuantos: number) =>
      `Van a salir ${cuantos} ${cuantos === 1 ? "mensaje" : "mensajes"} de verdad, ` +
      `desde la línea de cada vendedor. Escribí ${cuantos} para confirmar.`,
    enviarRealBoton: (cuantos: number) =>
      cuantos === 1 ? "Enviar 1 mensaje de verdad" : `Enviar ${cuantos} mensajes de verdad`,

    // Y el resultado también dice el modo: "se encolaron 3 mensajes" sin más
    // deja al operador sin saber qué acaba de hacer.
    enviadoPrueba: (cuantos: number) =>
      `Se encolaron ${cuantos} ${cuantos === 1 ? "mensaje" : "mensajes"} en modo ensayo. ` +
      "Nadie va a recibir nada.",
    enviadoReal: (cuantos: number) =>
      `Se encolaron ${cuantos} ${cuantos === 1 ? "mensaje" : "mensajes"} para salir de verdad.`,

    // Liberar de a muchos pide escribir el número. Vetar de a uno, no: frenar
    // de más no le hace daño a nadie.
    liberarTodos: (cuantos: number) => `Liberar los ${cuantos}`,
    liberarTodosConfirmar: (cuantos: number) =>
      `Van a salir ${cuantos} mensajes que el sistema apartó. Escribí ${cuantos} para confirmar.`,
  },

  /**
   * Los diez chequeos que el agente corre sobre su propia máquina.
   *
   * ⚠️ **Esto es la diferencia entre este sistema y el "502 mudo" del MVP.** El
   * panel ya recibía qué chequeo falló, pero mostraba el nombre técnico tal
   * cual: la tarjeta de una máquina decía `claude_bin`, `permiso_mcp`,
   * `device_id`. Para el dueño de una empresa de materiales eso es exactamente
   * tan útil como no decir nada.
   *
   * Cada uno tiene qué es y —lo que importa— **qué hacer**. Siete de los diez
   * vienen de problemas que ya ocurrieron durante la instalación del MVP y van
   * a volver a ocurrir en cada Mac nueva, así que la instrucción tiene que
   * poder seguirse por teléfono.
   */
  chequeos: {
    claude_bin: {
      nombre: "Claude Code",
      detalle: "El programa que lee los chats no está donde el agente lo busca.",
      queHacer: "Correr el instalador de nuevo en esa Mac (paso 2.2 del instructivo).",
    },
    permiso_mcp: {
      nombre: "Permiso del navegador",
      detalle: "Claude no tiene permiso para manejar Chrome en esta máquina.",
      queHacer: "Lo deja listo el instalador. Si sigue en rojo, correrlo de nuevo.",
    },
    permiso_sitio: {
      nombre: "Permiso de WhatsApp Web",
      detalle: "La extensión de Chrome necesita permiso para entrar a WhatsApp Web.",
      queHacer: "Se concede a mano en Chrome, una sola vez (paso 2.1 del instructivo).",
    },
    device_id: {
      nombre: "Chrome de esta máquina",
      detalle: "El agente no sabe cuál de los Chrome abiertos es el de esta computadora.",
      queHacer: "Correr el instalador de nuevo: lo averigua solo.",
    },
    chrome: {
      nombre: "Chrome responde",
      detalle: "Chrome no contestó cuando el agente le habló.",
      queHacer: "Reiniciar la Mac suele alcanzar. Si no, avisar al equipo técnico.",
    },
    navegador_envio: {
      nombre: "Navegador de envío",
      detalle: "La ventana propia que usa para escribir todavía no se vinculó con WhatsApp.",
      queHacer: "Escanear el QR desde el teléfono del vendedor (paso 2.4 del instructivo).",
    },
    whatsapp_sesion: {
      nombre: "Sesión de WhatsApp",
      detalle: "WhatsApp Web cerró la sesión. Pasa cada tantos días y no es una falla.",
      queHacer: "Escanear el QR de nuevo desde el teléfono del vendedor.",
    },
    claude_md: {
      nombre: "Instrucciones de la máquina",
      detalle: "Falta el archivo que le explica al modelo qué hace este sistema.",
      queHacer: "Correr el instalador de nuevo.",
    },
    permisos_macos: {
      nombre: "Permisos de macOS",
      detalle: "macOS no le dio permiso al agente para manejar otros programas.",
      queHacer: "Ajustes del Sistema → Privacidad y seguridad → Automatización.",
    },
    selectores: {
      nombre: "Lectura de WhatsApp",
      detalle: "WhatsApp Web cambió por dentro y el sistema dejó de reconocer la pantalla.",
      queHacer: "Es para el equipo técnico: hay que recalibrar antes de la próxima corrida.",
    },
  } as Record<string, { nombre: string; detalle: string; queHacer: string }>,

  historial: {
    titulo: "Historial",
    filtrar: "Filtrar por tipo",
    grupos: {
      todo: "Todo",
      mensajes: "Mensajes",
      corridas: "Corridas",
      cambios: "Cambios y frenos",
    } as Record<string, string>,
    vacio: "Todavía no pasó nada.",
    vacioFiltrado: "No hay eventos de este tipo.",
    verCorrida: "Ver la corrida",
    anteriores: "Más recientes",
    siguientes: "Más viejos",
    pagina: (actual: number, total: number) => `Página ${actual} de ${total}`,
  },

  metricas: {
    titulo: "Cómo viene",
    periodo: "Período",
    dias: (cuantos: number) => `${cuantos} días`,
    enviados: "Mensajes entregados",
    enviadosAyuda: (corridas: number, mensajes: number) =>
      `${corridas} ${corridas === 1 ? "corrida" : "corridas"}, ${mensajes} ${mensajes === 1 ? "borrador" : "borradores"}`,
    costoPorMensaje: "Costo por mensaje",
    costoTotal: (total: number) => `US$ ${total.toFixed(2)} en total`,
    reescritos: "Reescritos por vos",
    reescritosAyuda: "Si es alto, los borradores no están sirviendo",
    apartados: "Apartados para revisar",
    apartadosAyuda: "Lo esperable es entre 10% y 20%",
    fallidos: (cuantos: number) =>
      cuantos === 1 ? "1 envío no salió" : `${cuantos} envíos no salieron`,
  },

  corrida: {
    tituloGeneracion: "Generación de seguimientos",
    tituloDiagnostico: "Diagnóstico de las máquinas",
    modoReal: "Envío real",
    modoPrueba: "Ensayo",
    terminada: "Terminada",
    enCurso: "En curso",
    verTodas: "Ver todas",
    resumen: "Resumen de la corrida",
    avance: "Avance",
    avanceAyuda: "Trabajos hechos de los que se encolaron",
    maquinas: "Máquinas",
    borradores: "Borradores",
    editados: (cuantos: number) => `${cuantos} reescritos a mano`,
    costo: "Costo",
    costoPorBorrador: (valor: number) => `US$ ${valor.toFixed(3)} por borrador`,
    irARevision: "Revisar los borradores",

    envio: "Qué pasó con cada mensaje",
    envioAyuda:
      "Se actualiza sola mientras haya algo saliendo. Los mensajes salen espaciados, así que esto tarda.",
    sinEnvios: "Todavía no se envió ninguno.",
    reparto: "Cómo quedaron los borradores",
    estado: "Estado",
    cuantos: "Cuántos",
    contacto: "Contacto",
    maquina: "Máquina",
    quePaso: "Qué pasó",
  },

  corridas: {
    titulo: "Corridas",
    cuando: "Cuándo",
    que: "Qué",
    comoTermino: "Cómo terminó",
    maquinas: "Máquinas",
    costo: "Costo",
    generacion: "Generación",
    diagnostico: "Diagnóstico",
    ninguna: "Todavía no se disparó ninguna corrida.",
    conFallas: (cuantas: number) =>
      cuantas === 1 ? "Terminada, 1 con falla" : `Terminada, ${cuantas} con fallas`,
    costoTotal: (total: number, cuantas: number) =>
      `${cuantas} ${cuantas === 1 ? "corrida" : "corridas"}, US$ ${total.toFixed(2)} en total.`,
  },

  /** Los seis estados de un mensaje, dichos como los diría una persona. */
  estados: {
    BORRADOR: "Sin revisar por el sistema",
    RETENIDO: "Apartado para que lo mires",
    EN_ESPERA: "Listo para salir",
    ENVIANDO: "Saliendo",
    ENVIADO: "Entregado",
    DESCARTADO: "No sale",
  } as Record<string, string>,

  /**
   * Por qué falló un envío.
   *
   * Llegan del backend y hasta ahora no se mostraban en ningún lado: el panel
   * dejaba de hablar del tema apenas se apretaba enviar. Son la diferencia
   * entre "algo salió mal" y saber si hay que llamar al vendedor, esperar, o
   * frenar todo.
   *
   * ⚠️ `SIN_CONFIRMAR` es el único que pide una acción de verdad: significa
   * que se apretó enviar y no se pudo confirmar en el chat. **El mensaje puede
   * haber salido.** Por eso no se reintenta —mandarlo dos veces sería peor— y
   * por eso el texto dice que hay que mirar el teléfono.
   */
  motivos: {
    CONTACTO_NO_COINCIDE:
      "El chat no era el de esa persona. El sistema abortó antes de escribir nada.",
    NUMERO_NO_RESOLUBLE: "No se pudo leer el número del contacto con certeza. No se escribió nada.",
    DESTINO_NO_PERMITIDO: "El número no está en la lista de destinos permitidos.",
    SIN_CONFIRMAR:
      "Se apretó enviar y no se pudo confirmar. Puede haber salido: conviene mirar el teléfono del vendedor antes de hacer nada.",
    SELECTOR_ROTO: "WhatsApp Web cambió por dentro. La corrida se frenó a propósito.",
    CAMPO_NO_VACIO: "Había algo escrito en el chat. No se tocó para no pisar lo del vendedor.",
    CHAT_NO_ABRE: "No se pudo abrir el chat.",
    SESION_CAIDA: "La sesión de WhatsApp de esa máquina venció. Hay que escanear el QR de nuevo.",
    TIMEOUT: "WhatsApp tardó demasiado en responder.",
    ERROR_INESPERADO: "Algo falló y no está clasificado. El detalle está en el log de la máquina.",
    rechazado: "Una regla lo frenó.",
    vetado: "Lo frenaste vos.",
    vencido: "Quedó viejo antes de salir.",
    fallido: "El envío falló.",
    sin_confirmar: "Se apretó enviar y no se pudo confirmar.",
  } as Record<string, string>,

  // Los nombres técnicos no se le muestran a nadie.
  senales: {
    PALABRA_CONFLICTO: "El chat tiene un reclamo abierto",
    SIN_RESPUESTA_PREVIA: "Ya le escribimos y no contestó",
    IDENTIDAD_AMBIGUA: "No está claro a quién se le escribiría",
    COMPROMISO_CONCRETO: "El mensaje promete un precio, una fecha o una cantidad",
    CHAT_NO_COMERCIAL: "No parece una conversación de trabajo",
    SIN_CONTEXTO: "No había con qué escribir: hay que redactarlo a mano",
    G1_IDENTIDAD: "El contacto del chat no coincide",
    G2_DESTINO_NO_PERMITIDO: "El número no está en los destinos permitidos",
    G3_TEXTO_INVALIDO: "El texto quedó mal armado",
    G4_TOPE: "Se llegó al tope de mensajes",
    G5_DUPLICADO: "Ya le escribimos hace poco",
    G6_FUERA_DE_VENTANA: "Fuera del horario",
    G7_PAUSA: "La máquina está pausada o sin consentimiento",
    G8_CAMPO_NO_VACIO: "Había algo escrito en el chat",
  } as Record<string, string>,

  alta: {
    titulo: "Dar de alta una máquina",
    identificador: "Identificador",
    identificadorAyuda: "Minúsculas, números y guiones. Ej.: mac-rocio",
    nombre: "Nombre del vendedor",
    linea: "Línea de WhatsApp (opcional)",
    tope: "Tope de mensajes por día",
    topeAyuda:
      "Se puede cambiar después. Con una línea nueva conviene empezar bajo: es lo que la protege.",
    crear: "Dar de alta",
    creando: "Creando…",
    duplicada: "Ya existe una máquina con ese identificador.",
    identificadorInvalido:
      "El identificador sólo admite minúsculas, números y guiones. «PC Principal» no sirve; «pc-principal» sí. El nombre con mayúsculas va en el campo de abajo.",
    errorDesconocido: "No se pudo dar de alta la máquina. Revisá la conexión y probá de nuevo.",
    tokenTitulo: "Token de la máquina",
    tokenAviso: "Copialo ahora: no se va a volver a mostrar.",
    tokenListo: "Ya lo copié",
    naceInactiva: "La máquina nace inactiva. Instalar no es activar.",
  },

  // La página de comandos. El catálogo en sí —cada comando con su explicación—
  // vive en `lib/comandos.ts`, y ahí está escrito por qué.
  comandos: {
    titulo: "Comandos",
    intro:
      "Los comandos que hacen falta para instalar, revisar y arreglar el sistema. Se copian de acá y se pegan tal cual: tipearlos a mano es donde aparecen los errores que después no se encuentran.",
    aviso:
      "Ninguno de estos comandos envía mensajes. Para frenar el sistema está el botón rojo del panel, que es inmediato y queda registrado.",
    indice: "Ir a",
    copiar: "Copiar",
    copiado: "Copiado",
    noSePudoCopiar: "No se pudo copiar solo. Seleccioná el texto y copialo con el mouse.",
    reemplazar: "Reemplazar",
    cuando: "Cuándo",
    pie: "Instalación paso a paso en la guía de puesta en marcha.",
  },

} as const;
