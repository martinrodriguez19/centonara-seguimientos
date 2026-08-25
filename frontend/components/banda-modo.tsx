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
 *
 * ---------------------------------------------------------------------------
 *
 * **Por qué la banda de prueba pasó de ámbar a verde.** Antes el estado normal
 * —el 99% del tiempo— pintaba una franja ámbar permanente arriba de todo. Un
 * color de advertencia que está siempre deja de leerse como advertencia, y de
 * paso le robaba fuerza a la única franja que sí tiene que alarmar. Además, en
 * una paleta cálida como la de Centonara, el ámbar permanente compite con los
 * avisos de verdad.
 *
 * El modo prueba no es una advertencia: es **la garantía funcionando**. El
 * sistema no le puede escribir a nadie, y eso es lo que el cliente compró. Va
 * en verde. El rojo queda reservado para cuando la lista está abierta, que es
 * la única situación en la que hay algo que temer — y ahora contrasta con lo de
 * al lado en vez de ser un tono más de la misma familia.
 */
export function BandaModo({ destinosAbiertos }: { destinosAbiertos: boolean }) {
  if (destinosAbiertos) {
    return (
      <div
        role="alert"
        // `text-background` y no `text-white`: en oscuro el rojo del token es
        // un salmón claro, y el blanco encima no se lee. El fondo de la página
        // invierte solo y contrasta en los dos temas.
        className="flex items-center justify-center gap-2 bg-critico px-4 py-2 text-center text-sm font-semibold text-background"
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
      className="flex items-center justify-center gap-2 border-b border-ok-borde bg-ok-suave px-4 py-2 text-center text-sm font-semibold text-ok"
    >
      <ShieldCheck className="size-4 shrink-0" aria-hidden />
      <span>{textos.modo.prueba}</span>
      <span className="hidden font-normal opacity-90 sm:inline">
        — {textos.modo.pruebaDetalle}
      </span>
    </div>
  );
}
