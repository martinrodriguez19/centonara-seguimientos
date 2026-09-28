"use client";

import { cn } from "@/lib/utils";

/**
 * Los dos gráficos del panel, hechos a mano en HTML (Panel v2).
 *
 * Sin librería a propósito: son dos formas —columnas en el tiempo y barras
 * ordenadas— y una dependencia de gráficos pesa más que todo el panel junto.
 *
 * Las reglas que siguen, y por qué:
 *
 * - **Una sola serie, un solo color** (`--accion`). Sin leyenda: el título ya
 *   dice qué se grafica. El texto va en tinta, nunca en el color de la serie.
 * - **Barras finas** (hasta 24 px) con la punta redondeada y la base recta, y
 *   una grilla de 1 px que casi no se ve: lo único que tiene que resaltar es el
 *   dato.
 * - **Cada barra dice su valor** al pasar el mouse o al llegar con el teclado,
 *   y hay una vista de tabla: el color nunca es la única forma de leerlo.
 */

/** Un techo redondo para el eje: 0 / 5 / 10 / 20 / 50 / 100… */
export function techoRedondo(maximo: number): number {
  if (maximo <= 0) return 1;
  const potencia = 10 ** Math.floor(Math.log10(maximo));
  for (const paso of [1, 2, 2.5, 5, 10]) {
    if (maximo <= paso * potencia) return paso * potencia;
  }
  return 10 * potencia;
}

type Punto = { clave: string; etiqueta: string; valor: number; detalle?: string };

/**
 * Columnas en el tiempo: una por día o por corrida.
 *
 * Las etiquetas del eje de abajo son salteadas (una de cada `cadaCuantas`) para
 * que no choquen; el valor de cada columna está en su tooltip y en la tabla.
 */
export function Columnas({
  puntos,
  formato = (v) => v.toLocaleString("es-AR"),
  alto = 160,
  titulo,
}: {
  puntos: Punto[];
  formato?: (valor: number) => string;
  alto?: number;
  /** Para el lector de pantalla y el encabezado de la tabla. */
  titulo: string;
}) {
  const techo = techoRedondo(Math.max(0, ...puntos.map((p) => p.valor)));
  const marcas = [0, 0.5, 1].map((f) => techo * f);
  const cadaCuantas = Math.max(1, Math.ceil(puntos.length / 8));

  return (
    <figure className="space-y-2">
      <div className="flex gap-2">
        {/* El eje de la izquierda: tres marcas redondas, en tinta tenue. */}
        <div className="relative w-10 shrink-0 font-mono text-[10px] text-muted-foreground tabular-nums" style={{ height: alto }}>
          {marcas.map((m) => (
            <span key={m} className="absolute right-0 -translate-y-1/2" style={{ top: `${(1 - m / techo) * 100}%` }}>
              {formato(m)}
            </span>
          ))}
        </div>
        <div className="relative min-w-0 flex-1" style={{ height: alto }} role="img" aria-label={titulo}>
          {marcas.map((m) => (
            <div key={m} className="absolute inset-x-0 h-px bg-border" style={{ top: `${(1 - m / techo) * 100}%` }} aria-hidden />
          ))}
          <div className="absolute inset-0 flex items-end gap-0.5">
            {puntos.map((p) => (
              <div
                key={p.clave}
                tabIndex={0}
                aria-label={`${p.etiqueta}: ${formato(p.valor)}${p.detalle ? `. ${p.detalle}` : ""}`}
                className="group relative flex h-full min-w-0 flex-1 cursor-default items-end justify-center rounded-sm outline-none hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div
                  className="w-full max-w-6 rounded-t bg-accion transition-opacity group-hover:opacity-80"
                  style={{ height: p.valor > 0 ? `max(2px, ${(p.valor / techo) * 100}%)` : 0 }}
                />
                <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 rounded-lg border bg-popover px-2.5 py-1.5 text-xs whitespace-nowrap shadow-md group-hover:block group-focus-visible:block">
                  <p className="text-muted-foreground">{p.etiqueta}</p>
                  <p className="font-mono font-semibold tabular-nums">{formato(p.valor)}</p>
                  {p.detalle && <p className="text-muted-foreground">{p.detalle}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="flex gap-0.5 pl-12 font-mono text-[10px] text-muted-foreground" aria-hidden>
        {puntos.map((p, i) => (
          <span key={p.clave} className="min-w-0 flex-1 truncate text-center">
            {i % cadaCuantas === 0 ? p.etiqueta : ""}
          </span>
        ))}
      </div>
      <VistaDeTabla titulo={titulo} filas={puntos.map((p) => [p.etiqueta, formato(p.valor)])} />
    </figure>
  );
}

/**
 * Barras horizontales ordenadas: "de qué hubo más".
 *
 * El nombre y el número son texto de verdad (se leen, se copian, los lee el
 * lector de pantalla); la barra sólo da la proporción a simple vista.
 */
export function Barras({
  filas,
  formato = (v) => v.toLocaleString("es-AR"),
  vacio,
}: {
  filas: { clave: string; etiqueta: string; valor: number }[];
  formato?: (valor: number) => string;
  vacio: string;
}) {
  if (filas.length === 0) return <p className="py-6 text-center text-sm text-muted-foreground">{vacio}</p>;
  const maximo = Math.max(...filas.map((f) => f.valor));
  return (
    <ul className="space-y-2.5">
      {filas.map((fila) => (
        <li key={fila.clave} className="grid grid-cols-[minmax(0,11rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate" title={fila.etiqueta}>
            {fila.etiqueta}
          </span>
          <span className="h-2.5 rounded-full bg-muted" aria-hidden>
            <span
              className="block h-full rounded-full bg-accion"
              style={{ width: `${maximo > 0 ? Math.max(2, (fila.valor / maximo) * 100) : 0}%` }}
            />
          </span>
          <span className="w-12 text-right font-mono tabular-nums">{formato(fila.valor)}</span>
        </li>
      ))}
    </ul>
  );
}

/** La tabla con los mismos números del gráfico, plegada. */
function VistaDeTabla({ titulo, filas }: { titulo: string; filas: [string, string][] }) {
  if (filas.length === 0) return null;
  return (
    <details className="pl-12 text-xs">
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Ver como tabla</summary>
      <table className="mt-2 w-full max-w-sm">
        <caption className="sr-only">{titulo}</caption>
        <tbody className="divide-y">
          {filas.map(([a, b], i) => (
            <tr key={i}>
              <td className="py-1 text-muted-foreground">{a}</td>
              <td className={cn("py-1 text-right font-mono tabular-nums")}>{b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
