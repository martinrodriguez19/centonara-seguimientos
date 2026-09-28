"use client";

import { useState } from "react";

import { coincide, ListaDeErrores, type Filtro } from "@/components/errores/lista";
import { Pagina } from "@/components/navegacion/pagina";
import { Aviso } from "@/components/ui/estado";
import { useEstado, useProblemas } from "@/lib/consultas";
import { textos } from "@/lib/textos";
import { cn } from "@/lib/utils";

/**
 * Errores y avisos: todo lo que hay que mirar, en un solo lugar (Panel v2).
 *
 * Antes esto se pintaba arriba del inicio —cada alerta como un cartel grande—,
 * más un aviso por problema dentro de cada tarjeta de máquina, más la banda
 * roja. El inicio terminaba siendo una pared de advertencias y el cliente no
 * sabía cuál importaba. Acá están todas, agrupadas por urgencia, filtrables por
 * máquina, y cada una se puede sacar de la vista con "Ya lo vi".
 *
 * Lo que no cambió: las alertas las sigue calculando el backend al preguntar
 * (`GET /alertas`, cada quince segundos), y desaparecen solas cuando se
 * resuelve la causa.
 */
export default function Errores() {
  const estado = useEstado();
  const problemas = useProblemas();
  const [filtro, setFiltro] = useState<Filtro>(null);

  const maquinas = estado.data?.maquinas ?? [];
  const cuantos = (f: Filtro) => problemas.nuevos.filter((p) => coincide(p, f)).length;
  const opciones: { filtro: Filtro; texto: string }[] = [
    { filtro: null, texto: textos.errores.todas },
    { filtro: "sistema", texto: textos.errores.sistema },
    ...maquinas.map((m) => ({ filtro: m.maquina, texto: m.nombre })),
  ];

  return (
    <Pagina titulo={textos.errores.titulo} bajada={textos.errores.bajada}>
      {estado.data?.pausa_global && (
        <Aviso nivel="critico" titulo={textos.errores.frenado} accion={textos.errores.frenadoAccion}>
          {textos.errores.frenadoDetalle}
        </Aviso>
      )}

      <div role="group" aria-label={textos.errores.filtroMaquina} className="flex flex-wrap gap-1.5">
        {opciones.map((opcion) => {
          const activo = filtro === opcion.filtro;
          const n = cuantos(opcion.filtro);
          return (
            <button
              key={opcion.filtro ?? "todas"}
              type="button"
              aria-pressed={activo}
              onClick={() => setFiltro(opcion.filtro)}
              className={cn(
                "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
                activo ? "border-foreground bg-foreground text-primary-foreground" : "bg-card hover:bg-muted",
              )}
            >
              {opcion.texto}
              {n > 0 && (
                <span className={cn("font-mono text-xs tabular-nums", activo ? "opacity-80" : "text-muted-foreground")}>
                  {n}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <ListaDeErrores filtro={filtro} />
    </Pagina>
  );
}
