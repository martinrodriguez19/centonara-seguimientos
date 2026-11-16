import type { Metadata, Viewport } from "next";

import { textos } from "@/lib/textos";

/**
 * El marco de la página pública de conexiones (D71).
 *
 * Es un *route group* aparte de `(panel)` para que no herede la barra: la
 * barra consulta `/api/estado`, que sin sesión contesta 401 y manda al login.
 * Acá no hay login, no hay menú y no hay nada del panel salvo las piezas de
 * `ui/`.
 *
 * Los metadatos son los de "agregar a pantalla de inicio" (plan §2.5): un
 * nombre corto que entre debajo del ícono, el ícono de siempre y el manifiesto
 * para Android. Sin service worker ni push: eso es la Fase 5, opcional.
 */
export const metadata: Metadata = {
  title: `${textos.conectar.titulo} · ${textos.conectar.marca}`,
  description: textos.conectar.bajada,
  manifest: "/conectar/manifest.webmanifest",
  appleWebApp: { capable: true, title: textos.conectar.titulo, statusBarStyle: "default" },
  // Que un buscador no la indexe: es pública, pero no es para el público.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Sólo tema claro (D55): el color de la barra del navegador es el fondo.
  themeColor: "#f5f7fa",
  colorScheme: "light",
};

export default function LayoutDeConexiones({ children }: { children: React.ReactNode }) {
  return <div className="min-h-svh">{children}</div>;
}
