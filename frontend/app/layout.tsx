import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { Proveedores } from "@/components/proveedores";
import { textos } from "@/lib/textos";

import "./globals.css";

/**
 * Dos familias con trabajos separados.
 *
 * - **Inter** hace todo: títulos, cuerpo, tablas, botones. Tiene cifras
 *   tabulares de verdad, que es lo que hace que los números se alineen entre
 *   filas. Los títulos eran Poppins; se unificó en el rediseño (D55) porque
 *   el aire técnico pide una sola voz, apretada, en vez de dos.
 * - **JetBrains Mono** para lo que es literalmente un identificador o una
 *   cifra que se lee sola: un token, el nombre de una máquina, un latido.
 *   Nunca texto corrido.
 *
 * La marca (Playfair) vive sólo en la pantalla de ingreso, que la importa ella.
 */
const cuerpo = Inter({
  variable: "--fuente-cuerpo",
  subsets: ["latin"],
  display: "swap",
});

const mono = JetBrains_Mono({
  variable: "--fuente-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: textos.app.titulo,
  description: textos.app.descripcion,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // lang="es": lo lee el lector de pantalla para elegir pronunciación, y el
    // navegador para ofrecer traducción. Toda la interfaz es en español (08 §3).
    //
    // ⚠️ Las variables de las fuentes van en el `<html>` y NO en el `<body>`:
    // `globals.css` aplica `font-sans` sobre `html`, y una variable definida en
    // el body no existe todavía ahí.
    //
    // Sin selector de tema ni script en el `<head>`: el panel es sólo claro
    // (D55), así que no hay nada que decidir antes del primer pintado.
    <html lang="es" className={`${cuerpo.variable} ${mono.variable}`}>
      <body className="antialiased">
        <Proveedores>{children}</Proveedores>
      </body>
    </html>
  );
}
