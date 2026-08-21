"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Loader2, Play } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { dispararCorrida, ErrorDeApi, type Corrida } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * El botón. Lo único que arranca el sistema.
 *
 * No hay cron y no hay temporizador: si nadie lo aprieta, no pasa nada. Eso es
 * una característica — el dueño sabe siempre por qué salieron mensajes hoy.
 *
 * Y **enviar es un segundo acto explícito**: esto genera borradores y se
 * detiene. Nada sale por inacción.
 */
export function BotonCorrida({
  hayMaquinas,
  pausado,
  enCurso,
  ultima,
}: {
  hayMaquinas: boolean;
  pausado: boolean;
  enCurso: Corrida | null;
  ultima: Corrida | null;
}) {
  const clienteQuery = useQueryClient();

  const disparar = useMutation({
    mutationFn: () => dispararCorrida("diagnostico"),
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["estado"] }),
  });

  if (enCurso) {
    const hechos = enCurso.jobs.total - enCurso.jobs.pendientes;
    return (
      <div className="flex items-center gap-3 rounded-lg border bg-muted/40 px-4 py-3">
        <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden />
        <div>
          <p className="text-sm font-medium">{textos.boton.enCurso}</p>
          <p className="text-sm tabular-nums text-muted-foreground">
            {textos.boton.progreso(hechos, enCurso.jobs.total)}
          </p>
        </div>
      </div>
    );
  }

  const impedido = !hayMaquinas || pausado;

  // Una generación que terminó deja borradores esperando una decisión. Que la
  // pantalla no lo diga es la forma más fácil de que nadie los mire nunca.
  const hayQueRevisar = ultima?.terminada && ultima.tipo === "generacion";

  return (
    <div className="space-y-2">
      {hayQueRevisar && (
        <Button variant="outline" asChild>
          <Link href={`/revision/${ultima.id}`}>
            <ClipboardList className="size-4" aria-hidden />
            Revisar borradores
          </Link>
        </Button>
      )}
      <Button
        size="lg"
        disabled={impedido || disparar.isPending}
        onClick={() => disparar.mutate()}
      >
        <Play className="size-4" aria-hidden />
        {disparar.isPending ? textos.boton.disparando : textos.boton.diagnostico}
      </Button>

      {/* "No pasó nada" sin explicación es peor que un mensaje: si el botón
          está deshabilitado, la pantalla dice por qué. */}
      {!hayMaquinas && <p className="text-sm text-muted-foreground">{textos.boton.sinMaquinas}</p>}

      {disparar.error instanceof ErrorDeApi && (
        <p className="text-sm text-destructive">{disparar.error.message}</p>
      )}
    </div>
  );
}
