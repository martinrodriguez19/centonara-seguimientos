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
    titulo: "Seguimiento Comercial",
    subtitulo: "Ingresá la contraseña del panel.",
    clave: "Contraseña",
    entrar: "Entrar",
    entrando: "Entrando…",
    incorrecta: "Contraseña incorrecta.",
    sinBackend: "No se pudo hablar con el servidor. Probá de nuevo en un momento.",
  },

  panel: {
    titulo: "Panel",
    salir: "Salir",
    maquinas: "Máquinas",
    sinMaquinas: "Todavía no hay ninguna máquina dada de alta.",
    enviadosHoy: "Mensajes enviados hoy",
    configuracion: "Configuración",
    historial: "Historial",
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
    confirmar:
      "Las máquinas van a dejar de recibir trabajo en menos de 10 segundos. ¿Frenamos?",
  },

  boton: {
    disparar: "Generar seguimientos",
    disparando: "Arrancando…",
    diagnostico: "Correr diagnóstico",
    sinMaquinas: "No hay ninguna máquina activa y sin pausar.",
    enCurso: "Corrida en curso",
    progreso: (hechos: number, total: number) => `${hechos} de ${total} listos`,
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
    activar: "Activar",
    desactivar: "Desactivar",
    rotarToken: "Rotar token",
    darDeBaja: "Dar de baja",
    ultimoLatido: "Último latido",
    nunca: "nunca",
    version: "Versión",
    fallando: "Chequeos que fallan",
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

    // Liberar de a muchos pide escribir el número. Vetar de a uno, no: frenar
    // de más no le hace daño a nadie.
    liberarTodos: (cuantos: number) => `Liberar los ${cuantos}`,
    liberarTodosConfirmar: (cuantos: number) =>
      `Van a salir ${cuantos} mensajes que el sistema apartó. Escribí ${cuantos} para confirmar.`,
  },

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
    crear: "Dar de alta",
    creando: "Creando…",
    duplicada: "Ya existe una máquina con ese identificador.",
    tokenTitulo: "Token de la máquina",
    tokenAviso: "Copialo ahora: no se va a volver a mostrar.",
    tokenListo: "Ya lo copié",
    naceInactiva: "La máquina nace inactiva. Instalar no es activar.",
  },


} as const;
