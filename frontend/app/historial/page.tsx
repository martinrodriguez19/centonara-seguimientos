"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { traerHistorial, type Evento } from "@/lib/panel";

/**
 * El historial.
 *
 * Es la pantalla que se abre cuando un cliente se queja. Diseñada para ese
 * momento: alguien nervioso buscando qué pasó, que necesita el orden cronológico
 * y quién hizo cada cosa, sin tener que interpretar nada.
 */
export default function Historial() {
  const historial = useQuery({ queryKey: ["historial"], queryFn: () => traerHistorial(200) });

  if (historial.isPending) return <p className="p-8 text-sm text-muted-foreground">Cargando…</p>;
  if (historial.isError) {
    return <p className="p-8 text-sm text-destructive">{historial.error.message}</p>;
  }

  return (
    <main className="mx-auto max-w-4xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Historial</h1>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/panel">Volver al panel</Link>
        </Button>
      </div>

      {historial.data.eventos.length === 0 ? (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          Todavía no pasó nada.
        </p>
      ) : (
        <ol className="divide-y rounded-lg border">
          {historial.data.eventos.map((evento) => (
            <Fila key={evento._id} evento={evento} />
          ))}
        </ol>
      )}
    </main>
  );
}

/** Los nombres técnicos no se le muestran a nadie. */
const QUE: Record<string, string> = {
  corrida_disparada: "Se disparó una corrida",
  mensaje_enviado: "Se envió un mensaje",
  mensaje_vetado: "Se frenó un mensaje",
  mensaje_editado: "Se editó un mensaje",
  mensaje_liberado: "Se liberó un mensaje retenido",
  mensaje_descartado: "Se descartó un mensaje",
  envio_abortado: "Se abortó un envío",
  kill_switch: "Se usó el freno de emergencia",
  configuracion_cambiada: "Cambió la configuración",
  destinos_cambiados: "Cambiaron los destinos permitidos",
  maquina_alta: "Se dio de alta una máquina",
  maquina_baja: "Se dio de baja una máquina",
  consentimiento_registrado: "Se registró el consentimiento de un vendedor",
};

function Fila({ evento }: { evento: Evento }) {
  const cuando = new Date(evento.cuando);
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3 text-sm">
      <time
        dateTime={evento.cuando}
        className="w-40 shrink-0 tabular-nums text-muted-foreground"
      >
        {cuando.toLocaleString("es-AR", { dateStyle: "short", timeStyle: "medium" })}
      </time>
      <span className="font-medium">{QUE[evento.que] ?? evento.que}</span>
      <span className="text-muted-foreground">— {evento.quien}</span>
      {Object.keys(evento.detalle).length > 0 && (
        <code className="w-full overflow-x-auto font-mono text-xs text-muted-foreground">
          {JSON.stringify(evento.detalle)}
        </code>
      )}
    </li>
  );
}
