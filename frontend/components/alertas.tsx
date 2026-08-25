"use client";

import { useQuery } from "@tanstack/react-query";

import { Aviso } from "@/components/ui/estado";
import { traerAlertas } from "@/lib/panel";

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
          key={alerta.codigo + alerta.titulo}
          nivel={alerta.nivel === "urgente" ? "critico" : "atencion"}
          titulo={alerta.titulo}
          // Qué hacer. Sin esto, la alerta sólo genera ansiedad.
          accion={alerta.accion}
        >
          {alerta.detalle}
        </Aviso>
      ))}
    </section>
  );
}
