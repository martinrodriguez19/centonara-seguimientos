"use client";

import { Switch } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Un sí/no que se aplica al tocarlo (Panel v2, D56).
 *
 * Antes cada sí/no de la configuración era un par de botones ("Prender" /
 * "Apagar", "Preguntar" / "No escribirle") con la variante cambiando según el
 * valor, y había que leer los dos para saber cuál estaba puesto. Un switch se
 * lee sin leer.
 *
 * `peligroso` lo pinta de rojo cuando está prendido: sólo para lo que hace que
 * algo salga sin que una persona lo mire.
 */
export function Interruptor({
  prendido,
  onCambiar,
  etiqueta,
  deshabilitado = false,
  peligroso = false,
}: {
  prendido: boolean;
  onCambiar: (prendido: boolean) => void;
  /** Para el lector de pantalla: el switch no tiene texto propio. */
  etiqueta: string;
  deshabilitado?: boolean;
  peligroso?: boolean;
}) {
  return (
    <Switch.Root
      checked={prendido}
      onCheckedChange={onCambiar}
      disabled={deshabilitado}
      aria-label={etiqueta}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border border-transparent transition-colors outline-none",
        "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        prendido ? (peligroso ? "bg-critico" : "bg-accion") : "bg-input",
      )}
    >
      <Switch.Thumb className="pointer-events-none block size-5 translate-x-0.5 rounded-full bg-card shadow-sm transition-transform data-[state=checked]:translate-x-[1.35rem]" />
    </Switch.Root>
  );
}
