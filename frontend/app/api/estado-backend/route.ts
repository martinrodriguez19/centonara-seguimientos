import { NextResponse } from "next/server";

import { consultarSalud, type EstadoBackend } from "@/lib/api";

/**
 * Ruta interna del frontend. **No es un endpoint del producto** y no está en
 * `04-CONTRATOS-API.md` porque no le pertenece al backend: existe sólo para que
 * el navegador pueda preguntar por el estado sin hablar con el backend
 * directamente (no hay CORS) y sin conocer su URL.
 *
 * Devuelve **200 siempre**, con el estado real en el cuerpo. Es la decisión
 * contraria a la del `/health` del backend, y a propósito: aquel es una sonda
 * de liveness que un balanceador lee por código de estado; ésta es un dato que
 * una pantalla muestra. Si contestara 503 cuando el backend está caído, el
 * fetch del cliente sería un error y la pantalla no podría mostrar *por qué*.
 *
 * Si algún día Render necesita una sonda del frontend, es otra ruta, no ésta.
 */
export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse<EstadoBackend>> {
  return NextResponse.json(await consultarSalud());
}
