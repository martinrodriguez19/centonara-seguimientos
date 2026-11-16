import { textos } from "@/lib/textos";

/**
 * El manifiesto de la página de conexiones, para "agregar a pantalla de inicio".
 *
 * Una ruta y no `app/manifest.ts` porque ése vale para toda la aplicación: el
 * panel del dueño terminaría instalable con `start_url` en la página pública.
 * Vive bajo `/conectar` para quedar dentro de lo que el middleware deja pasar
 * sin cookie.
 */
export function GET() {
  return Response.json(
    {
      name: `${textos.conectar.titulo} · ${textos.conectar.marca}`,
      short_name: textos.conectar.titulo,
      start_url: "/conectar",
      scope: "/conectar",
      display: "standalone",
      background_color: "#f5f7fa",
      theme_color: "#f5f7fa",
      icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
    },
    { headers: { "content-type": "application/manifest+json" } },
  );
}
