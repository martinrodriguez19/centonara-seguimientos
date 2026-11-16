/**
 * La página de conexiones (D71): su cliente y la lógica de la vista de pasos.
 *
 * **Aparte de `lib/panel.ts` a propósito.** La página es pública y la abre un
 * vendedor desde el celular: no tiene sesión, no puede mandar al login y no
 * tiene por qué cargar los tipos del panel. Que el contrato público viva en su
 * propio archivo es lo mismo que hace el backend con `api/publico.py`: un campo
 * nuevo del panel no llega acá por accidente.
 *
 * La lógica de "en qué paso estamos" es una función pura (`pasoDeReconexion`)
 * para poder probarla sin montar la página ni esperar cinco minutos de verdad.
 */

export type Semaforo = "ok" | "caida" | "desconocido";
export type EstadoDeComputadora = "viva" | "dormida" | "apagada";
export type TipoDeReconexion = "whatsapp" | "claude" | "verificar";

export type ReconexionPublica = {
  tipo: TipoDeReconexion;
  pedida_en: string;
  /** La máquina ya abrió la ventana (o ya verificó). */
  hecha: boolean;
  /** La máquina no la tomó a tiempo: apagada o dormida. */
  vencida: boolean;
};

export type ConexionPublica = {
  maquina: string;
  nombre: string;
  estado: EstadoDeComputadora;
  whatsapp: Semaforo;
  claude: Semaforo;
  reconexion: ReconexionPublica | null;
};

export type Conexiones = {
  maquinas: ConexionPublica[];
  /** A quién pedirle el código de Claude. Puede venir vacío. */
  pedir_codigo_a: string;
};

/**
 * Un error de la página, con el texto que se le puede mostrar al vendedor.
 *
 * `texto` es `null` cuando el servidor no dijo nada mostrable: la página pone
 * entonces su aviso genérico, nunca un código ni un "502".
 */
export class ErrorDeConexiones extends Error {
  constructor(
    readonly status: number,
    readonly texto: string | null,
  ) {
    super(texto ?? `status ${status}`);
    this.name = "ErrorDeConexiones";
  }
}

async function pedir<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`/api/publico${ruta}`, { ...opciones, cache: "no-store" });
  } catch {
    // Sin señal en el celular: es lo más común y no es culpa de nadie.
    throw new ErrorDeConexiones(0, null);
  }
  const cuerpo: unknown = await respuesta.json().catch(() => null);
  if (!respuesta.ok) {
    const detalle = (cuerpo as { detail?: unknown } | null)?.detail;
    // Sólo el 429 trae un texto pensado para el vendedor ("Ya se pidió recién…").
    // Los demás `detail` son para quien programa y no se muestran.
    const texto = respuesta.status === 429 && typeof detalle === "string" ? detalle : null;
    throw new ErrorDeConexiones(respuesta.status, texto);
  }
  return cuerpo as T;
}

export const traerConexiones = () => pedir<Conexiones>("/conexiones");

export const pedirReconexion = (maquina: string, tipo: TipoDeReconexion) =>
  pedir<{ ok: boolean; reconexion: ReconexionPublica }>(
    `/conexiones/${encodeURIComponent(maquina)}/${tipo}`,
    { method: "POST" },
  );

// ---------------------------------------------------------------------------
// La vista de pasos
// ---------------------------------------------------------------------------

/** Lo que tarda de más un escaneo antes de decir "no se completó". */
export const MINUTOS_PARA_COMPLETAR = 5;

/** Lo que la página recuerda de la reconexión que pidió este celular. */
export type Pedido = {
  maquina: string;
  tipo: "whatsapp" | "claude";
  /** Cuándo se apretó el botón, en el reloj del celular: sólo para los cinco minutos. */
  pedidoEn: number;
  /**
   * El `pedida_en` que devolvió el servidor para el último pedido de este
   * celular (el de reconectar o el de verificar), en la hora del servidor.
   *
   * Hace falta porque `reconexion` es la última acción de la máquina, y entre
   * el POST y el refresco siguiente el servidor todavía muestra la anterior:
   * sin esto, reintentar después de un "vencida" mostraría "vencida" otra vez
   * durante cinco segundos. Se compara con la hora del servidor y no con la
   * del celular, que puede estar corrida. `null` = cualquiera sirve (un 429:
   * el pedido que vale es el que ya estaba).
   */
  desde: string | null;
  /** Si después se apretó "Ya escaneé" / "Ya terminé". */
  verificacionPedida: boolean;
};

export type Paso =
  /** Las instrucciones, esperando que la persona haga lo suyo. */
  | "esperando"
  /** Se apretó "Ya terminé" y la máquina está mirando. */
  | "revisando"
  /** La máquina verificó y todavía no aparece conectado. */
  | "todavia_no"
  | "listo"
  /** La máquina no tomó el pedido a tiempo: apagada, dormida o sin internet. */
  | "vencida"
  /** Pasaron cinco minutos sin que WhatsApp se conecte. */
  | "no_se_completo";

/**
 * En qué paso está una reconexión, según lo último que dijo el servidor.
 *
 * El orden importa:
 *
 * 1. **Conectado gana siempre.** Si el semáforo está en verde, el vendedor no
 *    tiene que hacer nada más. El botón sólo aparece con el semáforo en rojo,
 *    así que un verde después del pedido es el resultado del pedido.
 * 2. **Vencida** antes que el reloj: si la máquina ni siquiera tomó el pedido,
 *    "probá de nuevo" no sirve; hay que ir a prenderla.
 * 3. **La verificación** ("Ya terminé"): mientras no esté hecha, "Revisando…";
 *    hecha y sin verde, "todavía no".
 * 4. **Cinco minutos** sin verde, sólo para WhatsApp: "no se completó". Claude
 *    no tiene reloj, porque depende de que otra persona pase un código y eso
 *    puede tardar lo que tarde.
 */
export function pasoDeReconexion(
  pedido: Pedido,
  maquina: ConexionPublica | undefined,
  ahora: number,
): Paso {
  if (maquina && maquina[pedido.tipo] === "ok") return "listo";

  const reconexion = maquina?.reconexion ?? null;
  const vigente =
    reconexion !== null &&
    (reconexion.tipo === pedido.tipo || reconexion.tipo === "verificar") &&
    (pedido.desde === null || Date.parse(reconexion.pedida_en) >= Date.parse(pedido.desde));

  if (vigente && reconexion.vencida) return "vencida";

  if (pedido.verificacionPedida) {
    if (vigente && reconexion.tipo === "verificar" && reconexion.hecha) return "todavia_no";
    // Pedida y todavía no hecha, o el servidor todavía no la muestra.
    return "revisando";
  }

  if (pedido.tipo === "whatsapp" && ahora - pedido.pedidoEn >= MINUTOS_PARA_COMPLETAR * 60_000) {
    return "no_se_completo";
  }
  return "esperando";
}
