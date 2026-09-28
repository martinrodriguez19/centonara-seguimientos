"use client";

import { TarjetaMaquina } from "@/components/maquina";
import { useConfiguracion, useCorridasConTandas } from "@/lib/consultas";
import { deHoy, dejadosHoy } from "@/lib/derivados";
import type { Maquina } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Las tarjetas de las máquinas, con lo que cada una hizo hoy.
 *
 * El "hoy" sale de las tandas de las corridas de hoy (`GET /corridas`), y el
 * tope, de la configuración: los dos ya se consultaban en otras pantallas y
 * salen de la misma caché. Mientras cargan, la tarjeta muestra "—".
 */
export function GrillaDeMaquinas({
  maquinas,
  onToken,
}: {
  maquinas: Maquina[];
  onToken: (token: string, nombre: string) => void;
}) {
  const hoy = useCorridasConTandas(deHoy);
  const config = useConfiguracion();

  if (maquinas.length === 0) {
    return (
      <p className="rounded-xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">
        {textos.panel.sinMaquinas}
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {maquinas.map((maquina) => (
        <TarjetaMaquina
          key={maquina.maquina}
          maquina={maquina}
          dejadosHoy={hoy.cargando ? undefined : dejadosHoy(hoy.corridas, maquina.maquina)}
          topeDelDia={config.data?.tope_diario_borradores}
          onToken={onToken}
        />
      ))}
    </div>
  );
}
