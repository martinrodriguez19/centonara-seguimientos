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
    descripcion: "Panel de seguimiento comercial. Sprint 0: sólo diagnóstico.",
  },

  diagnostico: {
    titulo: "Diagnóstico del sistema",
    subtitulo:
      "Esqueleto del Sprint 0. Todavía no hay pantallas del producto: esta página sólo verifica que el frontend hable con el backend.",

    backend: {
      titulo: "Backend",
      descripcion: "Respuesta de GET /health",
    },

    // Los tres estados posibles. Son distintos a propósito: "no contesta" y
    // "contesta pero está degradado" se arreglan de formas distintas, y quien
    // mira la pantalla tiene que poder distinguirlos sin abrir los logs.
    estado: {
      operativo: "Operativo",
      degradado: "Degradado",
      inalcanzable: "Sin respuesta",
      consultando: "Consultando…",
    },

    detalle: {
      operativo: "El backend responde y Mongo está conectado.",
      degradado:
        "El backend responde pero Mongo no. El backend devuelve 503 a propósito, para que el balanceador lo saque de rotación.",
      inalcanzable:
        "No se pudo llegar al backend. Revisá que esté levantado en la URL configurada.",
    },

    campos: {
      ok: "ok",
      mongo: "Mongo",
      entorno: "Entorno",
      url: "URL consultada",
      httpStatus: "HTTP",
      actualizado: "Última consulta",
    },

    valores: {
      si: "sí",
      no: "no",
    },

    acciones: {
      reconsultar: "Volver a consultar",
      consultando: "Consultando…",
    },

    // Se refresca solo, pero eso no se ve. Decirlo evita que alguien mire una
    // pantalla vieja creyendo que está mirando el estado de ahora.
    autorefresco: "Se actualiza solo cada 5 segundos.",
  },

  entornos: {
    local: "local",
    staging: "staging",
    produccion: "producción",
  },
} as const;
