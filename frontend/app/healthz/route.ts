import { NextResponse } from "next/server";

/**
 * Sonda de liveness del **frontend**. Es la que va en el healthcheck de Render.
 *
 * Contesta 200 sin tocar nada externo: no consulta al backend, no lee la base,
 * no depende de configuración. Lo único que afirma es "este proceso está vivo y
 * puede servir una petición", que es exactamente lo que un balanceador necesita
 * saber para decidir si deja la instancia en rotación.
 *
 * Por qué no alcanza ninguna de las otras dos rutas:
 *
 * - `/` consulta al backend para pintar el diagnóstico. Si el backend se cae,
 *   `/` sigue estando bien pero Render vería un frontend enfermo y lo sacaría de
 *   rotación sin motivo — dos servicios cayendo por el precio de uno.
 * - `/api/estado-backend` contesta 200 siempre, a propósito, porque es un dato
 *   que una pantalla muestra. Como sonda diría "sano" pase lo que pase.
 *
 * Fuera de `/api` y sin autenticación, igual que el `/health` del backend: no es
 * del producto, es del proceso. No lleva textos porque no la lee una persona,
 * así que no va nada de esto a `lib/textos.ts`.
 */

// Sin esto Next la prerenderiza en el build y la sonda pasaría a ser un archivo
// estático: contestaría 200 aunque el proceso esté hecho un desastre.
export const dynamic = "force-dynamic";

export function GET(): NextResponse {
  return NextResponse.json(
    { ok: true, servicio: "frontend" },
    {
      // El dominio va detrás de Cloudflare con el proxy activo (07 §7 de infra).
      // Un 200 cacheado es una sonda que sigue diciendo que sí después de que el
      // servicio murió: es peor que no tener sonda, porque da confianza falsa.
      headers: { "cache-control": "no-store, no-cache, must-revalidate" },
    },
  );
}
