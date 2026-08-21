"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import { pausarSistema } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * El kill switch.
 *
 * Tres decisiones, y las tres tienen el mismo motivo: el dueño lo va a usar con
 * las manos temblando algún día.
 *
 * 1. **Se ve sin hacer scroll, en todas las pantallas.** Va en la barra
 *    superior, que es `sticky`. Un freno al que hay que ir a buscar no es un
 *    freno.
 * 2. **Una sola confirmación, no tres.** Una guarda que molesta se termina
 *    esquivando, y la que importa es la primera.
 * 3. **Reanudar no confirma nada.** Frenar de más no le hace daño a nadie;
 *    hacer difícil el freno, sí.
 */
export function KillSwitch({ pausado }: { pausado: boolean }) {
  const clienteQuery = useQueryClient();

  const cambiar = useMutation({
    mutationFn: pausarSistema,
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["estado"] }),
  });

  if (pausado) {
    return (
      <Button
        variant="outline"
        size="sm"
        disabled={cambiar.isPending}
        onClick={() => cambiar.mutate(false)}
      >
        <Play className="size-4" aria-hidden />
        {textos.killSwitch.reanudar}
      </Button>
    );
  }

  return (
    <Button
      variant="destructive"
      size="sm"
      disabled={cambiar.isPending}
      onClick={() => {
        if (confirm(textos.killSwitch.confirmar)) cambiar.mutate(true);
      }}
    >
      <Ban className="size-4" aria-hidden />
      {textos.killSwitch.frenar}
    </Button>
  );
}

/**
 * El cartel de "está frenado", separado del botón.
 *
 * Con el sistema pausado, el botón dice "Reanudar" — que por sí solo no
 * comunica que hay algo detenido ahora mismo. Esto lo dice.
 */
export function AvisoFrenado() {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4"
    >
      <Ban className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
      <div>
        <p className="font-semibold text-destructive">{textos.killSwitch.frenado}</p>
        <p className="text-sm text-muted-foreground">{textos.killSwitch.frenadoDetalle}</p>
      </div>
    </div>
  );
}
