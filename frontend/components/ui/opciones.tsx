"use client";

import { ToggleGroup } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Elegir una entre pocas opciones, con la elegida a la vista (Panel v2, D56).
 *
 * Reemplaza a los grupos de `Button` sueltos cuya variante cambiaba según el
 * valor: se veían como tres acciones y no como una elección. Esto es un
 * control segmentado —una sola pieza— y siempre hay exactamente una marcada:
 * tocar la que ya está no la desmarca.
 */
export function Opciones<T extends string>({
  valor,
  opciones,
  onCambiar,
  etiqueta,
  deshabilitado = false,
}: {
  valor: T;
  opciones: { valor: T; texto: string }[];
  onCambiar: (valor: T) => void;
  etiqueta: string;
  deshabilitado?: boolean;
}) {
  return (
    <ToggleGroup.Root
      type="single"
      value={valor}
      onValueChange={(nuevo) => {
        // Radix manda "" al tocar la que ya estaba: eso no es una elección.
        if (nuevo && nuevo !== valor) onCambiar(nuevo as T);
      }}
      aria-label={etiqueta}
      disabled={deshabilitado}
      className="inline-flex flex-wrap gap-1 rounded-lg border bg-muted p-1"
    >
      {opciones.map((opcion) => (
        <ToggleGroup.Item
          key={opcion.valor}
          value={opcion.valor}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors outline-none",
            "hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
            "data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-sm",
          )}
        >
          {opcion.texto}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
