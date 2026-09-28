"use client";

import Link from "next/link";
import { Popover } from "radix-ui";

import { cn } from "@/lib/utils";
import { textos } from "@/lib/textos";

/**
 * En qué modo está el sistema, en un chip de la barra (D54).
 *
 * **Reemplaza a la banda de todo el ancho.** La banda cumplía el criterio de
 * "saber en dos segundos si esto le puede escribir a un cliente real", pero el
 * cliente la leía como un error permanente —roja todo el día con el envío
 * automático prendido—, y un cartel que asusta sin pedir nada enseña a no leer
 * los carteles. El chip dice lo mismo, en el mismo lugar de todas las
 * pantallas, sin gritar. El detalle está a un toque.
 *
 * Lo que decide el modo sigue siendo la lista de destinos (regla R4) y el
 * switch del envío automático (D52), nunca la variable de entorno.
 */
export type Modo = "prueba" | "real" | "automatico";

export function modoDe(destinosAbiertos: boolean, envioAutomatico: boolean): Modo {
  if (envioAutomatico) return "automatico";
  if (destinosAbiertos) return "real";
  return "prueba";
}

const PUNTO: Record<Modo, string> = {
  prueba: "bg-ok",
  real: "bg-atencion",
  automatico: "bg-critico",
};

const CHIP: Record<Modo, string> = {
  prueba: "border-border bg-card text-foreground",
  real: "border-atencion-borde bg-atencion-suave text-atencion",
  automatico: "border-critico-borde bg-critico-suave text-critico",
};

export function ChipModo({
  destinosAbiertos,
  envioAutomatico,
  destinosPermitidos,
}: {
  destinosAbiertos: boolean;
  envioAutomatico: boolean;
  destinosPermitidos: number;
}) {
  const modo = modoDe(destinosAbiertos, envioAutomatico);
  const t = textos.chipModo;

  const titulo = { prueba: t.prueba, real: t.real, automatico: t.automatico }[modo];
  const detalle = {
    prueba: t.pruebaDetalle(destinosPermitidos),
    real: t.realDetalle,
    automatico: `${t.automaticoDetalle}${destinosAbiertos ? "" : ` ${t.automaticoAcotado}`}`,
  }[modo];
  // Adónde se cambia: el envío automático vive en Envío; la lista, en Seguridad.
  const cambiar = modo === "automatico" ? "/config/envio" : "/config/seguridad";

  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label={`${t.etiqueta}: ${titulo}`}
        className={cn(
          "inline-flex h-8 items-center gap-2 rounded-full border px-3 text-xs font-medium whitespace-nowrap outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring",
          CHIP[modo],
        )}
      >
        <span className={cn("size-2 rounded-full", PUNTO[modo])} aria-hidden />
        <span className="hidden sm:inline">{titulo}</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-50 w-72 rounded-xl border bg-popover p-4 text-sm text-popover-foreground shadow-lg outline-none"
        >
          <p className="flex items-center gap-2 font-medium">
            <span className={cn("size-2 rounded-full", PUNTO[modo])} aria-hidden />
            {titulo}
          </p>
          <p className="mt-1 text-muted-foreground">{detalle}</p>
          <Popover.Close asChild>
            <Link
              href={cambiar}
              className="mt-3 inline-block text-sm font-medium text-accion-tinta underline-offset-2 hover:underline"
            >
              {t.cambiar} →
            </Link>
          </Popover.Close>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
