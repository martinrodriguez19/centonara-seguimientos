import { cn } from "@/lib/utils";

/**
 * El hueco que ocupa algo mientras carga.
 *
 * **Por qué.** Cuatro pantallas mostraban `<p>Cargando…</p>` en la esquina
 * superior izquierda y después reemplazaban eso por el contenido entero. El
 * resultado es que la pantalla salta: lo que estabas por tocar se corre. Con la
 * forma reservada de antemano, no salta.
 *
 * `aria-hidden` porque un esqueleto no tiene nada que leerle a nadie: el estado
 * de carga se anuncia una sola vez, desde `Cargando`.
 */
export function Esqueleto({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-md bg-muted", className)}
    />
  );
}

/**
 * El estado de carga de una pantalla entera.
 *
 * `role="status"` con `aria-live="polite"`: quien usa un lector de pantalla se
 * entera de que está cargando sin que se le interrumpa lo que estaba oyendo.
 */
export function Cargando({
  etiqueta = "Cargando…",
  children,
}: {
  etiqueta?: string;
  children: React.ReactNode;
}) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{etiqueta}</span>
      {children}
    </div>
  );
}

/** El esqueleto de la pantalla principal: la banda, el botón y las tarjetas. */
export function EsqueletoDelPanel() {
  return (
    <Cargando>
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-6">
        <Esqueleto className="h-11 w-64" />
        <div className="grid gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Esqueleto key={i} className="h-20" />
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1].map((i) => (
            <Esqueleto key={i} className="h-52" />
          ))}
        </div>
      </div>
    </Cargando>
  );
}

/** El esqueleto de una lista de tarjetas: revisión, corridas, historial. */
export function EsqueletoDeLista({ filas = 4 }: { filas?: number }) {
  return (
    <Cargando>
      <div className="space-y-3">
        <Esqueleto className="h-7 w-48" />
        {Array.from({ length: filas }, (_, i) => (
          <Esqueleto key={i} className="h-24" />
        ))}
      </div>
    </Cargando>
  );
}
