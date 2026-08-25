/**
 * El cliente del panel, del lado del navegador.
 *
 * Habla con `/api/...` del propio Next, que reenvía al backend
 * (`app/api/[...ruta]/route.ts`). Nunca con el backend directo.
 *
 * Los tipos copian `docs/02-ARQUITECTURA.md` §4.2, que es la fuente de verdad:
 * si esto y el documento no coinciden, el que está mal es esto.
 */

export type Maquina = {
  maquina: string;
  nombre: string;
  activo: boolean;
  pausada: boolean;
  online: boolean;
  ultimo_latido: string | null;
  puede_enviar: boolean;
  /** Qué chequeo falló, por nombre. Es lo único accionable de un diagnóstico. */
  chequeos_fallando: string[];
  diagnostico: Record<string, string>;
  version_agente: string | null;
  tope_diario: number;
};

export type Corrida = {
  id: string;
  tipo: string;
  modo: string;
  estado: string;
  maquinas: string[];
  creada_en: string;
  jobs: { total: number; pendientes: number } & Record<string, number>;
  terminada: boolean;
  costo_usd: number;
};

export type Estado = {
  maquinas: Maquina[];
  corrida_en_curso: Corrida | null;
  /** La más reciente, haya terminado o no. Es el enlace a "revisar borradores". */
  ultima_corrida: Corrida | null;
  pausa_global: boolean;
  enviados_hoy: number;
  /**
   * Si el sistema puede escribirle a cualquiera (regla R4).
   *
   * ⚠️ Es esto y no `ENTORNO` lo que decide si la pantalla se ve en modo
   * prueba. Mientras la lista de destinos no esté abierta, el sistema no puede
   * alcanzar a un cliente real por más que el servidor sea el de producción.
   */
  destinos_abiertos: boolean;
  destinos_permitidos: number;
};

export type Configuracion = {
  pausa_global: boolean;
  destinos_permitidos: string[];
  n_chats_por_defecto: number;
  /**
   * La ventana de antigüedad: desde y hasta cuántos días de silencio vale la
   * pena un seguimiento. El caso de uso son los clientes fríos, no el que
   * escribió hoy.
   */
  antiguedad_min_dias: number;
  antiguedad_max_dias: number;
  tope_diario_maquina: number;
  tope_por_corrida: number;
  largo_maximo: number;
  dias_anti_duplicado: number;
  palabras_conflicto: string[];
  /**
   * Lo que hace que un chat parezca de trabajo. Si el resumen no contiene
   * ninguna, el triage marca `CHAT_NO_COMERCIAL` y el borrador se retiene.
   *
   * Es el otro extremo de la misma perilla que `palabras_conflicto`, y el que
   * mueve `tasa_retencion` —el número que la pantalla de métricas dice calibrar
   * cuando se va del 10 al 20%—.
   */
  palabras_comerciales: string[];
  /** Sólo lectura: no está en `CambioConfiguracion`, no se edita desde acá. */
  ventana: { inicio: string; fin: string; dias: number[] };
  /** Sólo lectura, en segundos: [mínimo, máximo] entre dos envíos. */
  pausa_entre_envios_s: [number, number];
  actualizado_en?: string;
};

export type Evento = {
  _id: string;
  cuando: string;
  que: string;
  quien: string;
  mensaje_id: string | null;
  corrida_id: string | null;
  detalle: Record<string, unknown>;
};

/** Un borrador, como lo necesita la pantalla de revisión. */
export type Mensaje = {
  id: string;
  maquina: string;
  contacto_nombre: string;
  contacto_id: string;
  resumen: string;
  texto: string;
  estado: "BORRADOR" | "RETENIDO" | "EN_ESPERA" | "ENVIANDO" | "ENVIADO" | "DESCARTADO";
  motivo: string | null;
  /** Por qué se apartó, o qué guardrail lo rechazó. Nunca vacío si no está limpio. */
  senales: string[];
  editado_por: string | null;
};

export type Revision = {
  mensajes: Mensaje[];
  conteo: Record<string, number>;
};

export type Alerta = {
  /** `urgente` pide una acción ahora; `aviso` se puede mirar después. */
  nivel: "urgente" | "aviso";
  codigo: string;
  titulo: string;
  detalle: string;
  /** Qué hacer. Nunca vacío: una alerta sin acción es una queja. */
  accion: string;
};

/** Cómo salió una corrida. Lo que devuelve `GET /corridas/{id}/metricas`. */
export type MetricasDeCorrida = {
  mensajes: number;
  /** Cuántos quedaron en cada estado. Las claves son los seis de la máquina. */
  por_estado: Record<string, number>;
  enviados: number;
  descartados: number;
  costo_usd: number;
  /**
   * Sobre lo que una persona pudo mirar. Un rechazado por guardrail nunca
   * estuvo sobre la mesa, así que no dice nada de la calidad del borrador.
   */
  tasa_edicion: number;
  editados: number;
};

export type Metricas = {
  dias: number;
  corridas: number;
  mensajes: number;
  enviados: number;
  costo_usd: number;
  /** Lo que cuesta cada mensaje que llegó. Con esto se decide si es viable. */
  costo_por_enviado: number;
  /** El número que importa. Si el dueño reescribe el 80%, esto no sirve. */
  tasa_edicion: number;
  /** El objetivo es 10 a 20%. Fuera de ahí hay que calibrar el triage. */
  tasa_retencion: number;
  fallidos: Record<string, number>;
};

/** Un token recién generado. Se muestra una vez y no se puede recuperar. */
export type TokenNuevo = { maquina: string; token: string; aviso: string };

/**
 * Un error del backend, con su código.
 *
 * Lleva `status` porque hay dos que la pantalla trata distinto: `401` manda al
 * login, y `423` significa "el kill switch está puesto", que no es una falla
 * sino el sistema haciendo lo que le pidieron.
 */
export class ErrorDeApi extends Error {
  constructor(
    readonly status: number,
    readonly codigo: string,
    mensaje: string,
  ) {
    super(mensaje);
    this.name = "ErrorDeApi";
  }

  get esSesionVencida(): boolean {
    return this.status === 401;
  }

  get esPausa(): boolean {
    return this.status === 423;
  }

  /**
   * El backend no contestó.
   *
   * Lo emite el proxy de Next (`app/api/[...ruta]/route.ts`) con su propio
   * código cuando el `fetch` al backend falla o expira. Se distingue del resto
   * porque **no hay nada que arreglar del lado de quien mira**: no es un dato
   * mal cargado ni una sesión vencida, es un servidor que se está despertando.
   * Decirle "revisá los datos" a alguien cuyo problema es que Render tardó en
   * levantar la instancia es hacerle perder el tiempo.
   */
  get esBackendCaido(): boolean {
    return this.codigo === "BACKEND_NO_DISPONIBLE" || this.status === 502;
  }
}

/**
 * El `detail` de un error, en texto legible.
 *
 * FastAPI usa el mismo campo para dos formas distintas, y el panel las recibe
 * las dos. En un error nuestro es una cadena —`"no hay nada que cambiar"`—
 * pero en un **error de validación (422) es un array de objetos**, uno por
 * campo que no pasó:
 *
 *     { "detail": [ { "loc": ["body", "maquina"], "msg": "String should ..." } ] }
 *
 * Estaba tipado como `string` a secas, así que ese array terminaba en
 * `ErrorDeApi.message` y cualquier pantalla que lo mostrara renderizaba
 * `[object Object]`. Es el mismo problema que los tipos escritos contra el
 * contrato en vez de contra la respuesta, pero en el camino de error.
 */
function leerDetalle(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return null;

  const partes = detail
    .map((item) => {
      if (typeof item !== "object" || item === null) return null;
      const { loc, msg } = item as { loc?: unknown[]; msg?: string };
      if (!msg) return null;
      // `loc` es ["body", "campo"]; lo útil es el último tramo.
      const campo = Array.isArray(loc) ? loc[loc.length - 1] : undefined;
      return campo ? `${String(campo)}: ${msg}` : msg;
    })
    .filter((parte): parte is string => parte !== null);

  return partes.length ? partes.join(" · ") : null;
}

async function pedir<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  const respuesta = await fetch(`/api${ruta}`, {
    ...opciones,
    headers: { "content-type": "application/json", ...opciones.headers },
    cache: "no-store",
  });

  if (respuesta.status === 204) return undefined as T;

  const cuerpo: unknown = await respuesta.json().catch(() => null);

  if (!respuesta.ok) {
    const detalle = cuerpo as { detail?: unknown; error?: string } | null;
    throw new ErrorDeApi(
      respuesta.status,
      detalle?.error ?? String(respuesta.status),
      leerDetalle(detalle?.detail) ??
        detalle?.error ??
        `El servidor contest\u00f3 ${respuesta.status}`,
    );
  }
  return cuerpo as T;
}

const conCuerpo = (metodo: string, datos?: unknown): RequestInit => ({
  method: metodo,
  body: datos === undefined ? undefined : JSON.stringify(datos),
});

// --- Sesión ----------------------------------------------------------------

export const ingresar = (clave: string) =>
  pedir<{ ok: boolean }>("/sesion", conCuerpo("POST", { clave }));

export const salir = () => pedir<{ ok: boolean }>("/sesion", { method: "DELETE" });

// --- Estado ----------------------------------------------------------------

export const traerEstado = () => pedir<Estado>("/estado");

// --- Máquinas --------------------------------------------------------------

export const altaMaquina = (datos: {
  maquina: string;
  nombre: string;
  telefono_linea?: string | null;
  tope_diario?: number;
}) => pedir<TokenNuevo>("/vendedores", conCuerpo("POST", datos));

export const rotarToken = (maquina: string) =>
  pedir<TokenNuevo>(`/vendedores/${maquina}/token`, conCuerpo("POST"));

export const editarMaquina = (
  maquina: string,
  cambios: {
    activo?: boolean;
    tope_diario?: number;
    pausado_hasta?: string | null;
    acepto_condiciones?: boolean;
  },
) => pedir<{ ok: boolean }>(`/vendedores/${maquina}`, conCuerpo("PATCH", cambios));

export const bajaMaquina = (maquina: string) =>
  pedir<{ ok: boolean }>(`/vendedores/${maquina}`, { method: "DELETE" });

// --- El botón --------------------------------------------------------------

export const dispararCorrida = (tipo: "diagnostico" | "generacion" = "diagnostico") =>
  pedir<{ id: string; maquinas: string[]; jobs: number }>("/corridas", conCuerpo("POST", { tipo }));

export const traerCorrida = (id: string) => pedir<Corrida>(`/corridas/${id}`);

/**
 * Las últimas corridas.
 *
 * Distinto del historial, que es el registro de auditoría y sirve para
 * reconstruir qué pasó con **un mensaje**. Esto es para mirar el trabajo de los
 * últimos días.
 */
export const traerCorridas = (limite = 50) =>
  pedir<{ corridas: Corrida[] }>(`/corridas?limite=${limite}`);

/**
 * Cómo salió una corrida.
 *
 * ⚠️ Esta ruta existía en el backend desde hacía tiempo y **no estaba en este
 * archivo**: era la única de las del panel que el front no llamaba nunca. Es
 * justo lo que necesita la pantalla de detalle — cómo se repartieron los
 * mensajes, cuántos salieron, cuánto costó y qué proporción reescribió un
 * humano.
 */
export const traerMetricasDeCorrida = (id: string) =>
  pedir<MetricasDeCorrida>(`/corridas/${id}/metricas`);

export const cancelarCorrida = (id: string) =>
  pedir<{ ok: boolean; jobs_cortados: number }>(`/corridas/${id}/cancelar`, conCuerpo("POST"));

// --- Revisión de borradores ------------------------------------------------

export const validarCorrida = (id: string) =>
  pedir<{
    en_espera: number;
    retenidos: number;
    rechazados: number;
    proporcion_retenida: number;
  }>(`/corridas/${id}/validar`, conCuerpo("POST"));

export const traerMensajes = (id: string) => pedir<Revision>(`/corridas/${id}/mensajes`);

export const editarMensaje = (id: string, texto: string) =>
  pedir<{ ok: boolean }>(`/mensajes/${id}`, conCuerpo("PATCH", { texto }));

export const vetarMensaje = (id: string) =>
  pedir<{ ok: boolean }>(`/mensajes/${id}/veto`, conCuerpo("POST"));

export const liberarMensaje = (id: string) =>
  pedir<{ ok: boolean }>(`/mensajes/${id}/liberar`, conCuerpo("POST"));

/**
 * El segundo botón. Nada sale por inacción: esto es lo que pasa cuando una
 * persona miró y decidió.
 *
 * `modo` es "prueba" por defecto en el backend también: para que algo salga de
 * verdad hay que decirlo en los dos lados.
 */
export const enviarCorrida = (id: string, modo: "prueba" | "real" = "prueba") =>
  pedir<{ mensajes: number; jobs: number; modo: string }>(
    `/corridas/${id}/enviar`,
    conCuerpo("POST", { modo }),
  );

// --- Alertas y métricas ----------------------------------------------------

export const traerAlertas = () => pedir<{ alertas: Alerta[]; urgentes: number }>("/alertas");

export const traerMetricas = (dias = 30) => pedir<Metricas>(`/metricas?dias=${dias}`);

// --- Kill switch -----------------------------------------------------------

export const pausarSistema = (pausado: boolean) =>
  pedir<{ pausado: boolean }>("/sistema/pausa", conCuerpo("POST", { pausado }));

// --- Configuración e historial ---------------------------------------------

export const traerConfiguracion = () => pedir<Configuracion>("/configuracion");

export const guardarConfiguracion = (cambios: Partial<Configuracion>) =>
  pedir<Configuracion>("/configuracion", conCuerpo("PATCH", cambios));

export const traerHistorial = (limite = 100) =>
  pedir<{ eventos: Evento[] }>(`/historial?limite=${limite}`);
