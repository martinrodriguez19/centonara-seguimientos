"use client";

import { useQuery } from "@tanstack/react-query";

import { traerMetricas } from "@/lib/panel";

/**
 * Los cuatro números del mes.
 *
 * El que importa es la **tasa de edición**. "23 mensajes enviados" no distingue
 * un sistema que funciona de uno que la gente corrige a mano todos los días, y
 * esa diferencia es la única que decide si esto vale la pena sostener.
 *
 * Se pinta en rojo cuando pasa de la mitad: a esa altura el sistema está dando
 * trabajo disfrazado de ayuda.
 */
export function Metricas() {
  const metricas = useQuery({ queryKey: ["metricas"], queryFn: () => traerMetricas(30) });

  if (!metricas.data) return null;
  const m = metricas.data;

  return (
    <section className="grid gap-3 sm:grid-cols-4" aria-label="Métricas del mes">
      <Numero titulo="Enviados (30 días)" valor={String(m.enviados)} />
      <Numero
        titulo="Costo por mensaje"
        valor={m.enviados ? `US$ ${m.costo_por_enviado.toFixed(3)}` : "—"}
        ayuda={`US$ ${m.costo_usd.toFixed(2)} en total`}
      />
      <Numero
        titulo="Reescritos por vos"
        valor={porcentaje(m.tasa_edicion)}
        ayuda="Si es alto, los borradores no están sirviendo"
        alarma={m.tasa_edicion > 0.5}
      />
      <Numero
        titulo="Apartados para revisar"
        valor={porcentaje(m.tasa_retencion)}
        ayuda="Lo esperable es entre 10% y 20%"
        alarma={m.tasa_retencion > 0.35}
      />
    </section>
  );
}

const porcentaje = (valor: number) => `${Math.round(valor * 100)}%`;

function Numero({
  titulo,
  valor,
  ayuda,
  alarma,
}: {
  titulo: string;
  valor: string;
  ayuda?: string;
  alarma?: boolean;
}) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{titulo}</p>
      <p
        className={
          alarma
            ? "text-2xl font-semibold tabular-nums text-destructive"
            : "text-2xl font-semibold tabular-nums"
        }
      >
        {valor}
      </p>
      {ayuda && <p className="text-xs text-muted-foreground">{ayuda}</p>}
    </div>
  );
}
