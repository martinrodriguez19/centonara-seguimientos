/**
 * Cliente del backend.
 *
 * Todo lo de este archivo corre **en el servidor de Next**, nunca en el
 * navegador: el backend no tiene CORS y `BACKEND_URL` no lleva prefijo
 * `NEXT_PUBLIC_`, así que no viaja al cliente. El navegador habla con la ruta
 * interna de `app/api/estado-backend/`, que reenvía hasta acá.
 *
 * A partir del Sprint 1 este archivo crece con los endpoints de
 * `04-CONTRATOS-API.md`. Hoy sólo tiene `/health`.
 */

/** Los tres entornos de 06 §4. Igual que el `Entorno` del backend (config.py). */
export type Entorno = "local" | "staging" | "produccion";

/**
 * Respuesta de `GET /health` del backend (T0.3).
 *
 * ⚠ `/health` todavía no está en `04-CONTRATOS-API.md`, que es la fuente de
 * verdad declarada. Este tipo copia lo que el backend implementa hoy; cuando se
 * documente el contrato, se revisa contra el documento.
 */
export type Salud = {
  ok: boolean;
  mongo: boolean;
  entorno: Entorno;
};

/**
 * Lo que el frontend le muestra a quien mira la pantalla.
 *
 * Es un tipo **nuestro**, no un contrato del backend: agrega la distinción
 * entre "el backend contestó" y "no llegamos al backend", que del lado del
 * backend no existe porque un proceso caído no contesta nada.
 */
export type EstadoBackend =
  | { alcanzable: true; httpStatus: number; salud: Salud; url: string }
  | { alcanzable: false; motivo: string; url: string };

/**
 * URL del backend. En local vale el default; en staging y producción la inyecta
 * Render (T0.7). Mismo criterio que `config.py` del backend, que también trae
 * defaults de local.
 */
export function urlBackend(): string {
  return process.env.BACKEND_URL ?? "http://localhost:8000";
}

/**
 * Cuánto esperamos antes de dar el backend por no disponible.
 *
 * 3 s: un poco más que los 2 s que el backend le da a Mongo
 * (`mongo_timeout_ms`), para que un Mongo lento se vea como "degradado" —que es
 * la verdad— y no como "sin respuesta".
 */
const TIMEOUT_MS = 3000;

function esSalud(valor: unknown): valor is Salud {
  if (typeof valor !== "object" || valor === null) return false;
  const v = valor as Record<string, unknown>;
  return (
    typeof v.ok === "boolean" &&
    typeof v.mongo === "boolean" &&
    (v.entorno === "local" || v.entorno === "staging" || v.entorno === "produccion")
  );
}

/**
 * Consulta `GET /health` y devuelve el estado, sin lanzar.
 *
 * No lanza a propósito: que el backend esté caído no es un error de esta
 * función, es justamente el dato que vino a buscar. Quien la llama siempre
 * recibe un `EstadoBackend` que puede mostrar.
 */
export async function consultarSalud(): Promise<EstadoBackend> {
  const url = `${urlBackend()}/health`;
  try {
    const respuesta = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
      headers: { accept: "application/json" },
    });

    const cuerpo: unknown = await respuesta.json();
    if (!esSalud(cuerpo)) {
      return {
        alcanzable: false,
        url,
        motivo: `El backend contestó ${respuesta.status} con un cuerpo que no es /health`,
      };
    }

    // 200 y 503 son los dos casos previstos por el backend, y los dos traen
    // cuerpo válido. Pasamos el status para poder mostrarlo tal cual.
    return { alcanzable: true, httpStatus: respuesta.status, salud: cuerpo, url };
  } catch (error) {
    return { alcanzable: false, url, motivo: describirError(error) };
  }
}

/**
 * Un motivo que sirva para arreglar el problema.
 *
 * `fetch` de Node envuelve el error real: siempre dice "fetch failed" y guarda
 * el motivo verdadero en `cause`. Sin desenvolverlo, la pantalla no distingue
 * "el backend no está levantado" de "la URL está mal escrita", que es
 * justamente lo que quien lee esta página vino a averiguar.
 */
function describirError(error: unknown): string {
  if (!(error instanceof Error)) return String(error);

  // AbortSignal.timeout lanza un TimeoutError; su mensaje suelto no dice nada.
  if (error.name === "TimeoutError") return `Sin respuesta en ${TIMEOUT_MS} ms`;

  const causa = detalleDeLaCausa(error.cause);
  return causa ? `${error.message}: ${causa}` : error.message;
}

/**
 * El detalle útil de la causa.
 *
 * Preferimos el `code` (`ECONNREFUSED`, `ENOTFOUND`, `ECONNRESET`) al mensaje:
 * cuando Node no puede conectar arma un `AggregateError` con un intento por
 * cada IP resuelta, y ese error tiene el `code` pero el `message` vacío.
 */
function detalleDeLaCausa(causa: unknown): string | null {
  if (!(causa instanceof Error)) return null;
  // `code` no está en el tipo Error, pero Node se lo pone a los errores de red.
  const code = (causa as Error & { code?: unknown }).code;
  if (typeof code === "string" && code) return code;
  return causa.message || null;
}
