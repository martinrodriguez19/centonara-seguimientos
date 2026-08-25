"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Esqueleto } from "@/components/ui/esqueleto";
import { Aviso } from "@/components/ui/estado";
import { traerMetricas } from "@/lib/panel";
import { textos } from "@/lib/textos";

const PERIODOS = [7, 30, 90] as const;

/**
 * Los números que decide mirar el dueño.
 *
 * El que importa es la **tasa de edición**. "23 mensajes enviados" no distingue
 * un sistema que funciona de uno que la gente corrige a mano todos los días, y
 * esa diferencia es la única que decide si esto vale la pena sostener. Se pinta
 * en rojo cuando pasa de la mitad: a esa altura el sistema está dando trabajo
 * disfrazado de ayuda.
 *
 * **Lo que se agregó.** La respuesta del backend trae nueve campos y la
 * pantalla dibujaba cuatro. El que faltaba y más se extraña es `fallidos`: por
 * qué fallaron los envíos, agrupado por código. Es lo que distingue "WhatsApp
 * cambió por dentro" —que frena todo y hay que arreglar— de "los contactos no
 * estaban en la lista", que es el sistema haciendo su trabajo. Sin eso, las dos
 * cosas se ven igual: un número de envíos más bajo de lo esperado.
 */
export function Metricas() {
  const [dias, setDias] = useState<number>(30);
  const metricas = useQuery({
    queryKey: ["metricas", dias],
    queryFn: () => traerMetricas(dias),
  });

  if (metricas.isPending) {
    return (
      <section className="grid gap-3 sm:grid-cols-4" aria-hidden>
        {[0, 1, 2, 3].map((i) => (
          <Esqueleto key={i} className="h-20" />
        ))}
      </section>
    );
  }

  // Un error de métricas no puede tapar el panel: son informativas, y el botón
  // y las máquinas siguen sirviendo sin ellas.
  if (!metricas.data) return null;
  const m = metricas.data;

  const fallidos = Object.entries(m.fallidos ?? {}).sort((a, b) => b[1] - a[1]);
  const totalFallidos = fallidos.reduce((suma, [, cuantos]) => suma + cuantos, 0);

  return (
    <section className="space-y-3" aria-label={textos.metricas.titulo}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{textos.metricas.titulo}</h2>
        <div className="flex gap-1" role="group" aria-label={textos.metricas.periodo}>
          {PERIODOS.map((opcion) => (
            <Button
              key={opcion}
              variant={opcion === dias ? "default" : "ghost"}
              size="sm"
              aria-pressed={opcion === dias}
              onClick={() => setDias(opcion)}
            >
              {textos.metricas.dias(opcion)}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        <Numero
          titulo={textos.metricas.enviados}
          valor={String(m.enviados)}
          ayuda={textos.metricas.enviadosAyuda(m.corridas, m.mensajes)}
        />
        <Numero
          titulo={textos.metricas.costoPorMensaje}
          valor={m.enviados ? `US$ ${m.costo_por_enviado.toFixed(3)}` : "—"}
          ayuda={textos.metricas.costoTotal(m.costo_usd)}
        />
        <Numero
          titulo={textos.metricas.reescritos}
          valor={porcentaje(m.tasa_edicion)}
          ayuda={textos.metricas.reescritosAyuda}
          alarma={m.tasa_edicion > 0.5}
        />
        <Numero
          titulo={textos.metricas.apartados}
          valor={porcentaje(m.tasa_retencion)}
          ayuda={textos.metricas.apartadosAyuda}
          alarma={m.tasa_retencion > 0.35}
        />
      </div>

      {/* Sólo aparece si hubo fallas. Un cuadro permanente que dice "0 fallas"
          enseña a no mirar el cuadro. */}
      {totalFallidos > 0 && (
        <Aviso nivel="atencion" titulo={textos.metricas.fallidos(totalFallidos)}>
          <ul className="space-y-1">
            {fallidos.map(([codigo, cuantos]) => (
              <li key={codigo} className="flex items-baseline gap-2">
                <span className="shrink-0 font-medium tabular-nums">{cuantos}×</span>
                <span>{textos.motivos[codigo] ?? codigo}</span>
              </li>
            ))}
          </ul>
        </Aviso>
      )}
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
    <div className="rounded-lg border bg-card p-3">
      <p className="text-xs text-muted-foreground">{titulo}</p>
      <p
        className={
          alarma
            ? "text-2xl font-semibold tabular-nums text-critico"
            : "text-2xl font-semibold tabular-nums"
        }
      >
        {valor}
      </p>
      {ayuda && <p className="text-xs text-muted-foreground">{ayuda}</p>}
    </div>
  );
}
