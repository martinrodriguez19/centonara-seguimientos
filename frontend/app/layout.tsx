import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Poppins } from "next/font/google";

import { Proveedores } from "@/components/proveedores";
import { textos } from "@/lib/textos";

import "./globals.css";

/**
 * Dos familias con trabajos separados, y una tercera sólo para identificadores.
 *
 * Antes había una sola (Geist) para absolutamente todo, incluido
 * `--font-heading`, y de ahí venía la falta de jerarquía: un título y una celda
 * de tabla eran la misma letra en dos tamaños.
 *
 * - **Poppins** es el sans geométrico del sitio de Centonara. Da la voz de la
 *   marca, y por eso viste los títulos. ⚠️ No baja de 16 px: en texto chico y
 *   denso es ancho y confuso, y es justo donde una interfaz "se complica".
 * - **Inter** hace todo lo demás — cuerpo, tablas, datos, botones. Tiene cifras
 *   tabulares de verdad, que es lo que hace que los números se alineen entre
 *   filas.
 * - **JetBrains Mono** sólo para lo que es literalmente un identificador: un
 *   token, un teléfono, el nombre de una máquina. Nunca texto corrido.
 */
const titulo = Poppins({
  variable: "--fuente-titulo",
  subsets: ["latin"],
  weight: ["500", "600"],
  display: "swap",
});

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

/**
 * Elige el tema **antes de que pinte la primera vez**.
 *
 * Va como script en línea y no como efecto de React a propósito: un efecto
 * corre después del primer pintado, y el resultado es el destello blanco que
 * tiene toda aplicación que resuelve el tema tarde. Acá el `<html>` ya sale con
 * la clase puesta.
 *
 * Y explica por qué el `.dark` de `globals.css` no hacía nada hasta hoy: estaba
 * definido, había `dark:` repartidos por los componentes, y **nada lo aplicaba
 * nunca**. Esto es lo que faltaba.
 *
 * Tres estados, no dos: `claro`, `oscuro` y —el que viene de fábrica— seguir la
 * preferencia del sistema operativo.
 */
const ELEGIR_TEMA = `
(function () {
  try {
    var guardado = localStorage.getItem("tema");
    var oscuro =
      guardado === "oscuro" ||
      (guardado !== "claro" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", oscuro);
  } catch (e) {
    /* Sin localStorage —modo privado, permisos— se queda en claro. Que el tema
       falle no puede impedir que el panel cargue. */
  }
})();
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // lang="es": lo lee el lector de pantalla para elegir pronunciación, y el
    // navegador para ofrecer traducción. Toda la interfaz es en español (08 §3).
    //
    // suppressHydrationWarning: el script de arriba le toca la clase al `<html>`
    // antes de que React hidrate, así que el servidor y el cliente difieren en
    // ese atributo a propósito. Es el único lugar del panel donde se permite.
    //
    // ⚠️ Las variables de las fuentes van en el `<html>` y NO en el `<body>`.
    // Estaban en el body, y `globals.css` aplica `font-sans` sobre `html`: una
    // variable definida en el body no existe todavía en el html, así que esa
    // declaración quedaba inválida y la tipografía elegida no llegaba a
    // aplicarse del todo. Es la clase de error que no rompe nada y sólo se ve
    // como "la interfaz no termina de verse bien".
    <html
      lang="es"
      suppressHydrationWarning
      className={`${titulo.variable} ${cuerpo.variable} ${mono.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: ELEGIR_TEMA }} />
      </head>
      <body className="antialiased">
        <Proveedores>{children}</Proveedores>
      </body>
    </html>
  );
}
