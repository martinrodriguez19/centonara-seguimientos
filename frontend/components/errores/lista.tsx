"use client";

import { CheckCircle2 } from "lucide-react";
import { useEffect, useMemo } from "react";

import { ErrorDeCarga } from "@/components/error-de-carga";
import { GrupoDeProblemas } from "@/components/errores/fila";
import { EsqueletoDeLista } from "@/components/ui/esqueleto";
import { useEstado, useProblemas } from "@/lib/consultas";
import type { Problema } from "@/lib/derivados";
import { textos } from "@/lib/textos";

/** `null` = todas; `"sistema"` = las que no son de ninguna máquina; si no, el id de una. */
export type Filtro = null | "sistema" | string;

export function coincide(problema: Problema, filtro: Filtro): boolean {
  if (filtro === null) return true;
  if (filtro === "sistema") return problema.maquina === null;
  return problema.maquina === filtro;
}

/**
 * Los errores y avisos, agrupados: urgentes, para mirar, y los ya vistos al
 * final y plegados.
 *
 * La usan la página de errores (con filtro) y el detalle de una máquina (fijo
 * en esa máquina).
 */
export function ListaDeErrores({ filtro = null }: { filtro?: Filtro }) {
  const estado = useEstado();
  const problemas = useProblemas();
  const { podar, todos, cargando } = problemas;

  // Olvidar lo marcado como visto que ya no existe: si no, la lista del
  // navegador crece para siempre. Sólo con los datos completos, para no
  // olvidar todo durante la primera carga.
  useEffect(() => {
    if (!cargando) podar(todos.map((p) => p.firma));
  }, [cargando, todos, podar]);

  const nombres = useMemo(
    () => Object.fromEntries((estado.data?.maquinas ?? []).map((m) => [m.maquina, m.nombre])),
    [estado.data],
  );

  if (cargando) return <EsqueletoDeLista filas={3} />;
  if (problemas.error) return <ErrorDeCarga error={problemas.error} />;

  const nuevos = problemas.nuevos.filter((p) => coincide(p, filtro));
  const vistos = problemas.yaVistos.filter((p) => coincide(p, filtro));
  const alVisto = (firma: string, visto: boolean) =>
    visto ? problemas.marcar(firma) : problemas.desmarcar(firma);

  if (nuevos.length === 0 && vistos.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed bg-card px-6 py-12 text-center">
        <CheckCircle2 className="size-8 text-ok" aria-hidden />
        <p className="font-medium">{filtro === null ? textos.errores.nada : textos.errores.nadaFiltrado}</p>
        <p className="max-w-sm text-sm text-muted-foreground">{textos.errores.nadaDetalle}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <GrupoDeProblemas
        titulo={textos.errores.urgentes}
        ayuda={textos.errores.urgentesAyuda}
        problemas={nuevos.filter((p) => p.nivel === "urgente")}
        nombres={nombres}
        vistos={false}
        onVisto={alVisto}
      />
      <GrupoDeProblemas
        titulo={textos.errores.avisos}
        ayuda={textos.errores.avisosAyuda}
        problemas={nuevos.filter((p) => p.nivel === "aviso")}
        nombres={nombres}
        vistos={false}
        onVisto={alVisto}
      />
      {nuevos.length === 0 && (
        <p className="text-sm text-muted-foreground">{textos.errores.nada}</p>
      )}
      {vistos.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground">
            {textos.errores.vistos} ({vistos.length})
          </summary>
          <div className="pt-3">
            <GrupoDeProblemas
              titulo={textos.errores.vistos}
              ayuda={textos.errores.vistosAyuda}
              problemas={vistos}
              nombres={nombres}
              vistos
              onVisto={alVisto}
            />
          </div>
        </details>
      )}
    </div>
  );
}
