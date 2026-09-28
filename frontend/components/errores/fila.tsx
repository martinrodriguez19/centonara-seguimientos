"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Ban, ChevronDown, Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useAvisos } from "@/components/ui/avisos-flotantes";
import { Button } from "@/components/ui/button";
import type { Problema } from "@/lib/derivados";
import { reanudarCorrida } from "@/lib/panel";
import { textos } from "@/lib/textos";
import { cn } from "@/lib/utils";

/**
 * Una cosa para revisar, en una fila.
 *
 * Antes cada alerta era un `Aviso` del tamaño de un párrafo, y con cuatro el
 * inicio era una pared roja. Acá la fila dice qué pasa y de qué máquina; el
 * "qué hacer" se despliega, porque se lee una vez y después estorba.
 */
export function FilaDeProblema({
  problema,
  nombreDeMaquina,
  visto,
  onVisto,
}: {
  problema: Problema;
  nombreDeMaquina?: string;
  visto: boolean;
  onVisto: (visto: boolean) => void;
}) {
  const [abierta, setAbierta] = useState(false);
  const urgente = problema.nivel === "urgente";
  const Icono = urgente ? Ban : AlertTriangle;

  return (
    <li className={cn("bg-card", visto && "opacity-70")}>
      <div className="flex items-start gap-3 px-4 py-3">
        <span
          className={cn(
            "mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg border",
            urgente ? "border-critico-borde bg-critico-suave text-critico" : "border-atencion-borde bg-atencion-suave text-atencion",
          )}
        >
          <Icono className="size-3.5" aria-hidden />
        </span>

        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{problema.titulo}</p>
            {problema.maquina && (
              <Link
                href={`/maquinas/${encodeURIComponent(problema.maquina)}`}
                className="rounded-md border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground hover:text-foreground"
              >
                {nombreDeMaquina ?? problema.maquina}
              </Link>
            )}
          </div>
          <p className="text-sm text-muted-foreground">{problema.detalle}</p>

          <button
            type="button"
            aria-expanded={abierta}
            onClick={() => setAbierta((a) => !a)}
            className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-accion-tinta hover:underline"
          >
            {textos.errores.queHacer}
            <ChevronDown className={cn("size-3 transition-transform", abierta && "rotate-180")} aria-hidden />
          </button>
          {abierta && (
            <div className="space-y-2 pt-1 text-sm">
              <p>{problema.accion}</p>
              <AccionesDelProblema problema={problema} />
            </div>
          )}
        </div>

        <Button
          variant="ghost"
          size="sm"
          className="shrink-0 text-muted-foreground"
          onClick={() => onVisto(!visto)}
        >
          {visto ? <Eye className="size-3.5" aria-hidden /> : <EyeOff className="size-3.5" aria-hidden />}
          <span className="hidden sm:inline">{visto ? textos.errores.volverAMostrar : textos.errores.yaLoVi}</span>
        </Button>
      </div>
    </li>
  );
}

/**
 * Los botones que resuelven algunas alertas desde acá mismo.
 *
 * La del canario trae el suyo (D31): "ya lo miré, continuar" reanuda la corrida
 * y suelta el freno. Antes esa alerta no tenía salida — quedó encendida días
 * enteros la primera vez que sonó.
 */
function AccionesDelProblema({ problema }: { problema: Problema }) {
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();
  const reanudar = useMutation({
    mutationFn: () => reanudarCorrida(problema.corrida_id ?? ""),
    onSuccess: () => avisar(textos.alertas.avisoReanudada),
    onError: () => avisar(textos.alertas.avisoFalloReanudar, "critico"),
    onSettled: () => {
      void clienteQuery.invalidateQueries({ queryKey: ["alertas"] });
      void clienteQuery.invalidateQueries({ queryKey: ["estado"] });
    },
  });

  const botones: React.ReactNode[] = [];
  if (problema.corrida_id) {
    botones.push(
      <Button key="ver" asChild size="sm" variant="outline">
        <Link href={`/corrida/${problema.corrida_id}`}>{textos.alertas.verCorrida}</Link>
      </Button>,
    );
  }
  if (problema.codigo === "canario_fallido" && problema.corrida_id) {
    botones.push(
      <Button key="reanudar" size="sm" disabled={reanudar.isPending} onClick={() => reanudar.mutate()}>
        {reanudar.isPending ? textos.alertas.reanudando : textos.alertas.reanudar}
      </Button>,
    );
  }
  if (problema.maquina) {
    botones.push(
      <Button key="maquina" asChild size="sm" variant="outline">
        <Link href={`/maquinas/${encodeURIComponent(problema.maquina)}`}>{textos.errores.verMaquina}</Link>
      </Button>,
    );
  }
  if (botones.length === 0) return null;
  return <div className="flex flex-wrap gap-2">{botones}</div>;
}

/** Una lista de filas con su encabezado, o nada si está vacía. */
export function GrupoDeProblemas({
  titulo,
  ayuda,
  problemas,
  nombres,
  vistos,
  onVisto,
}: {
  titulo: string;
  ayuda: string;
  problemas: Problema[];
  nombres: Record<string, string>;
  vistos: boolean;
  onVisto: (firma: string, visto: boolean) => void;
}) {
  if (problemas.length === 0) return null;
  return (
    <section className="space-y-2" aria-label={titulo}>
      <div className="flex items-baseline gap-2">
        <h2 className="text-sm font-semibold">{titulo}</h2>
        <span className="font-mono text-xs text-muted-foreground tabular-nums">{problemas.length}</span>
        <span className="text-xs text-muted-foreground">· {ayuda}</span>
      </div>
      <ul className="divide-y overflow-hidden rounded-xl border sombra-suave">
        {problemas.map((p) => (
          <FilaDeProblema
            key={p.firma}
            problema={p}
            nombreDeMaquina={p.maquina ? nombres[p.maquina] : undefined}
            visto={vistos}
            onVisto={(visto) => onVisto(p.firma, visto)}
          />
        ))}
      </ul>
    </section>
  );
}
