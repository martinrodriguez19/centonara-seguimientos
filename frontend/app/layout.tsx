import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Proveedores } from "@/components/proveedores";
import { textos } from "@/lib/textos";

import "./globals.css";

const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

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
    <html lang="es">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <Proveedores>{children}</Proveedores>
      </body>
    </html>
  );
}
