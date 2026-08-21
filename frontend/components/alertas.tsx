"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Info } from "lucide-react";

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
      {alertas.data.alertas.map((alerta) => {
        const urgente = alerta.nivel === "urgente";
        const Icono = urgente ? AlertTriangle : Info;
        return (
          <div
            key={alerta.codigo + alerta.titulo}
            role={urgente ? "alert" : "status"}
            className={
              urgente
                ? "flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4"
                : "flex items-start gap-3 rounded-lg border bg-muted/40 p-4"
            }
          >
            <Icono
              className={
                urgente
                  ? "mt-0.5 size-5 shrink-0 text-destructive"
                  : "mt-0.5 size-5 shrink-0 text-muted-foreground"
              }
              aria-hidden
            />
            <div className="space-y-1">
              <p className={urgente ? "font-semibold text-destructive" : "font-semibold"}>
                {alerta.titulo}
              </p>
              <p className="text-sm">{alerta.detalle}</p>
              {/* Qué hacer. Sin esto, la alerta sólo genera ansiedad. */}
              <p className="text-sm text-muted-foreground">{alerta.accion}</p>
            </div>
          </div>
        );
      })}
    </section>
  );
}
