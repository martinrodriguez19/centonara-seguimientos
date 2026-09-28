import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Un número con su etiqueta: "Borradores hoy · 42".
 *
 * La cifra va en mono y grande porque es lo que se lee; la etiqueta, chica y
 * arriba, porque se lee una vez y después se reconoce por el lugar.
 */
export function Indicador({
  etiqueta,
  valor,
  ayuda,
  icono: Icono,
  tinta,
  chico = false,
  className,
}: {
  etiqueta: string;
  valor: React.ReactNode;
  ayuda?: React.ReactNode;
  icono?: LucideIcon;
  /** Para teñir la cifra con un color de estado (`text-critico`). */
  tinta?: string;
  /** Para un valor que es texto ("mañana 17:00") y no una cifra. */
  chico?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border bg-card p-4 sombra-suave", className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-muted-foreground">{etiqueta}</p>
        {Icono && <Icono className="size-4 text-muted-foreground/70" aria-hidden />}
      </div>
      <p className={cn("mt-2 font-mono font-semibold tracking-tight tabular-nums", chico ? "text-xl" : "text-2xl", tinta)}>{valor}</p>
      {ayuda && <p className="mt-1 text-xs text-muted-foreground">{ayuda}</p>}
    </div>
  );
}
