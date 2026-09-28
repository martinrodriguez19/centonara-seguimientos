"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { MenuDeAcciones, useAccionesDeMaquina } from "@/components/maquinas/acciones";
import { Pildora, Punto } from "@/components/ui/estado";
import { chipsDeMaquina, haceCuanto, situacion } from "@/lib/derivados";
import type { Maquina } from "@/lib/panel";
import { textos } from "@/lib/textos";
import { cn } from "@/lib/utils";

/**
 * La tarjeta de una máquina (Panel v2).
 *
 * **Antes** eran 480 líneas con todo a la vista a la vez: latido, versión,
 * modo, los dos cursores, un aviso grande de chequeos, otro de consentimiento,
 * el tope editable y cinco botones. Con tres máquinas el inicio era una pared.
 *
 * **Ahora** responde tres preguntas de un vistazo —¿está viva?, ¿cuánto hizo
 * hoy?, ¿hay algo que resolver?— y el resto está a un click:
 *
 * - Los problemas son **chips chicos**, no avisos. El detalle y qué hacer
 *   viven en la página de la máquina y en "Errores y avisos".
 * - Las acciones van a un menú `⋯`.
 * - Los cursores de barrido y ventana, el tope y los chequeos, al detalle.
 *
 * Toda la tarjeta lleva al detalle: el enlace se estira sobre ella y el menú
 * queda por encima, para no anidar un botón adentro de un enlace.
 */
export function TarjetaMaquina({
  maquina,
  dejadosHoy,
  topeDelDia,
  onToken,
}: {
  maquina: Maquina;
  /** Los borradores que dejó hoy, sumando corridas. `undefined` mientras carga. */
  dejadosHoy?: number;
  /** El tope de borradores por máquina por día (`tope_diario_borradores`). */
  topeDelDia?: number;
  onToken: (token: string, nombre: string) => void;
}) {
  const acciones = useAccionesDeMaquina(maquina, onToken);
  const estado = situacion(maquina);
  const chips = chipsDeMaquina(maquina);
  const sha = maquina.version_agente?.split(" ")[0];
  const proporcion =
    dejadosHoy !== undefined && topeDelDia ? Math.min(1, dejadosHoy / topeDelDia) : null;

  return (
    <article
      className={cn(
        "group relative flex flex-col rounded-xl border bg-card sombra-suave transition-colors",
        "focus-within:border-accion/50 hover:border-accion/50",
        !maquina.activo && "opacity-75",
      )}
    >
      <div className="flex items-start justify-between gap-3 px-4 pt-4">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <Punto nivel={estado.nivel} latiendo={estado.nivel === "ok"} />
            <h3 className="truncate text-[15px] font-semibold">
              <Link
                href={`/maquinas/${encodeURIComponent(maquina.maquina)}`}
                className="outline-none after:absolute after:inset-0 after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
              >
                {maquina.nombre}
              </Link>
            </h3>
            <span className="text-xs text-muted-foreground">{estado.texto}</span>
          </div>
          <p className="truncate font-mono text-xs text-muted-foreground">
            {maquina.maquina}
            {sha && (
              <>
                {" · "}
                {sha.slice(0, 7)}
                {maquina.actualizada === true && <span className="text-ok"> ✓</span>}
              </>
            )}
          </p>
        </div>
        <div className="relative z-10 flex items-center gap-1">
          <span className="font-mono text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">
            {haceCuanto(maquina.ultimo_latido)}
          </span>
          <MenuDeAcciones maquina={maquina} acciones={acciones} />
        </div>
      </div>

      <div className="space-y-2 px-4 py-4">
        <div className="flex items-baseline justify-between gap-2 text-xs">
          <span className="text-muted-foreground">
            {textos.maquinas.hoy} · {textos.maquinas.borradores}
          </span>
          <span className="font-mono tabular-nums">
            <span className="text-base font-semibold text-foreground">{dejadosHoy ?? "—"}</span>
            {topeDelDia ? <span className="text-muted-foreground"> / {topeDelDia}</span> : null}
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
          <div
            className={cn("h-full rounded-full transition-[width]", proporcion === 1 ? "bg-atencion" : "bg-accion")}
            style={{ width: `${(proporcion ?? 0) * 100}%` }}
          />
        </div>
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 border-t px-4 py-2.5">
        <div className="flex min-w-0 flex-wrap gap-1.5">
          {chips.length === 0 ? (
            <span className="text-xs text-muted-foreground">{textos.maquina.modo}: {maquina.modo_agente ?? "—"}</span>
          ) : (
            chips.map((chip) => (
              <Pildora key={chip.texto} nivel={chip.nivel} className="px-1.5 text-[11px]">
                {chip.texto}
              </Pildora>
            ))
          )}
        </div>
        <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-accion-tinta">
          {textos.maquinas.verDetalle}
          <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </span>
      </div>

      {acciones.dialogos}
    </article>
  );
}
