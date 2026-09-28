import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * El marco de cada pantalla: un encabezado con título, bajada y acciones, y el
 * contenido debajo.
 *
 * Antes cada página armaba el suyo, con su propio `<h1>` y su propio botón de
 * "Volver al panel". Con la barra común (D54) ese botón sobra —la barra está
 * siempre— y lo que queda es que todas las pantallas empiecen igual.
 */
export function Pagina({
  titulo,
  bajada,
  acciones,
  migas,
  ancho = "normal",
  children,
}: {
  titulo: React.ReactNode;
  bajada?: React.ReactNode;
  acciones?: React.ReactNode;
  /** El camino hasta acá, sin la página actual: `[{ href: "/maquinas", texto: "Máquinas" }]`. */
  migas?: { href: string; texto: string }[];
  ancho?: "normal" | "angosto";
  children: React.ReactNode;
}) {
  const contenedor = cn("mx-auto w-full px-4 sm:px-6", ancho === "angosto" ? "max-w-3xl" : "max-w-6xl");
  return (
    <>
      <section className="fondo-grilla border-b bg-card">
        <div className={cn(contenedor, "flex flex-wrap items-end justify-between gap-4 py-6")}>
          <div className="min-w-0 space-y-1">
            {migas && migas.length > 0 && (
              <nav aria-label="Estás en" className="text-xs text-muted-foreground">
                {migas.map((miga) => (
                  <span key={miga.href}>
                    <Link href={miga.href} className="hover:text-foreground hover:underline">
                      {miga.texto}
                    </Link>
                    <span aria-hidden className="mx-1.5">
                      /
                    </span>
                  </span>
                ))}
              </nav>
            )}
            <h1 className="text-2xl font-semibold">{titulo}</h1>
            {bajada && <p className="max-w-2xl text-sm text-muted-foreground">{bajada}</p>}
          </div>
          {acciones && <div className="flex flex-wrap items-center gap-2">{acciones}</div>}
        </div>
      </section>
      <main className={cn(contenedor, "space-y-6 py-6")}>{children}</main>
    </>
  );
}

/** Un bloque con título dentro de una página. */
export function Seccion({
  titulo,
  ayuda,
  acciones,
  children,
  className,
}: {
  titulo: React.ReactNode;
  ayuda?: React.ReactNode;
  acciones?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">{titulo}</h2>
          {ayuda && <p className="text-sm text-muted-foreground">{ayuda}</p>}
        </div>
        {acciones}
      </div>
      {children}
    </section>
  );
}
