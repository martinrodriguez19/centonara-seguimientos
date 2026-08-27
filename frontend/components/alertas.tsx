"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useAvisos } from "@/components/ui/avisos-flotantes";
import { Aviso } from "@/components/ui/estado";
import { reanudarCorrida, traerAlertas, type Alerta } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Las alertas, arriba de todo.
 *
 * Se refrescan solas cada quince segundos. Una alerta que hay que ir a buscar a
 * otra pantalla es una alerta que nadie ve — y las dos que más importan ("puede
 * haber salido y no sabemos", "WhatsApp cambió") son exactamente las que no
 * pueden esperar a que a alguien se le ocurra mirar.
 *
 * Si no hay ninguna, esto no ocupa lugar. Un panel con un cartel verde
 * permanente enseña a no leer los carteles.
 *
 * La del canario trae su botón al lado (D31): "ya lo miré, continuar" reanuda
 * la corrida y suelta el freno. Antes esa alerta no tenía salida — quedó
 * encendida días enteros la primera vez que sonó.
 */
export function Alertas() {
  const alertas = useQuery({
    queryKey: ["alertas"],
    queryFn: traerAlertas,
    refetchInterval: 15_000,
  });

  if (!alertas.data?.alertas.length) return null;

  return (
    <section className="space-y-2" aria-label="Alertas">
      {alertas.data.alertas.map((alerta) => (
        <Aviso
          key={alerta.codigo + alerta.titulo + (alerta.corrida_id ?? "")}
          nivel={alerta.nivel === "urgente" ? "critico" : "atencion"}
          titulo={alerta.titulo}
          // Qué hacer. Sin esto, la alerta sólo genera ansiedad.
          accion={<AccionDeAlerta alerta={alerta} />}
        >
          {alerta.detalle}
        </Aviso>
      ))}
    </section>
  );
}

function AccionDeAlerta({ alerta }: { alerta: Alerta }) {
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();
  const reanudar = useMutation({
    mutationFn: () => reanudarCorrida(alerta.corrida_id ?? ""),
    onSuccess: () => avisar(textos.alertas.avisoReanudada),
    onError: () => avisar(textos.alertas.avisoFalloReanudar, "critico"),
    onSettled: () => {
      void clienteQuery.invalidateQueries({ queryKey: ["alertas"] });
      void clienteQuery.invalidateQueries({ queryKey: ["estado"] });
    },
  });

  if (alerta.codigo !== "canario_fallido" || !alerta.corrida_id) {
    return <>{alerta.accion}</>;
  }

  return (
    <div className="space-y-2">
      <p>{alerta.accion}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href={`/corrida/${alerta.corrida_id}`}>{textos.alertas.verCorrida}</Link>
        </Button>
        <Button size="sm" disabled={reanudar.isPending} onClick={() => reanudar.mutate()}>
          {reanudar.isPending ? textos.alertas.reanudando : textos.alertas.reanudar}
        </Button>
      </div>
    </div>
  );
}
