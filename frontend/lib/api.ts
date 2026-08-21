/**
 * Lo único que este archivo tiene que saber: dónde está el backend.
 *
 * Corre **en el servidor de Next**, nunca en el navegador. `BACKEND_URL` no
 * lleva prefijo `NEXT_PUBLIC_`, así que no viaja al cliente: el navegador habla
 * con `/api/...` del propio Next, que reenvía al backend
 * (`app/api/[...ruta]/route.ts`). Consecuencia buena de eso: el backend no
 * necesita CORS, porque todo le llega del mismo origen.
 *
 * Los tipos del panel viven en `lib/panel.ts`, que es lo que usa el navegador.
 */

/** En local vale el default; en producción la inyecta Render. */
export function urlBackend(): string {
  return process.env.BACKEND_URL ?? "http://localhost:8000";
}
