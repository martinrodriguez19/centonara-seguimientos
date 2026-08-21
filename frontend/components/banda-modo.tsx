"use client";

import { AlertTriangle, ShieldCheck } from "lucide-react";

import { textos } from "@/lib/textos";

/**
 * La banda que dice en qué modo está el sistema.
 *
 * **Criterio: alguien mira la pantalla dos segundos y sabe si esto le puede
 * escribir a un cliente real.** Confundir prueba con real es de los errores más
 * caros que puede cometer un operador, y es de los que se cometen apurado — así
 * que ocupa todo el ancho arriba de todo, no una etiqueta chica en una esquina.
 *
 * Lo que la decide NO es la variable de entorno: es si la lista de destinos
 * permitidos está abierta (regla R4). Un servidor de producción con la lista
 * cerrada sigue sin poder alcanzar a nadie, y la pantalla tiene que decir eso y
 * no otra cosa.
 */
export function BandaModo({ destinosAbiertos }: { destinosAbiertos: boolean }) {
  if (destinosAbiertos) {
    return (
      <div
        role="status"
        className="flex items-center justify-center gap-2 bg-destructive px-4 py-2 text-center text-sm font-semibold text-white"
      >
        <AlertTriangle className="size-4 shrink-0" aria-hidden />
        <span>{textos.modo.real}</span>
        <span className="hidden font-normal opacity-90 sm:inline">
          — {textos.modo.realDetalle}
        </span>
      </div>
    );
  }

  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 bg-amber-400 px-4 py-2 text-center text-sm font-semibold text-amber-950"
    >
      <ShieldCheck className="size-4 shrink-0" aria-hidden />
      <span>{textos.modo.prueba}</span>
      <span className="hidden font-normal opacity-80 sm:inline">
        — {textos.modo.pruebaDetalle}
      </span>
    </div>
  );
}
