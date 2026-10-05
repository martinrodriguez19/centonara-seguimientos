import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Pildora, type Nivel } from "@/components/ui/estado";
import { horaCorta } from "@/lib/derivados";
import type { RevisionDelDia, ResultadoDelDia } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Lo que encontró la repesca de hoy (D61): cómo terminó el día cada máquina.
 *
 * Es la respuesta a "¿se hizo todo el laburo?" sin contar borradores a mano.
 * Sólo aparece cuando la repesca ya corrió hoy.
 */
const NIVEL: Record<ResultadoDelDia, Nivel> = {
  completa: "ok",
  sin_chats: "ok",
  repescada: "atencion",
  sin_cuota: "atencion",
  pausada: "neutro",
  ausente: "critico",
};

export function RevisionDelDiaTarjeta({
  revision,
  proxima,
}: {
  revision: RevisionDelDia;
  proxima: string | null;
}) {
  const nota = revision.sin_disparo ? textos.repesca.hoySinDisparo[revision.sin_disparo] : null;
  return (
    <section className="space-y-3 rounded-xl border bg-card p-4" aria-label={textos.repesca.hoyTitulo}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-medium">{textos.repesca.hoyTitulo}</h2>
        <span className="text-sm text-muted-foreground">
          {textos.repesca.titulo} · {horaCorta(revision.cuando)}
        </span>
      </div>
      <ul className="divide-y text-sm">
        {revision.maquinas.map((m) => (
          <li key={m.maquina} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="font-medium">{m.nombre}</span>
            <span className="flex items-center gap-3">
              <span className="font-mono tabular-nums text-muted-foreground">
                {m.dejados} / {m.tope}
              </span>
              <Pildora nivel={NIVEL[m.resultado] ?? "neutro"}>
                {textos.repesca.hoyResultado[m.resultado] ?? m.resultado}
              </Pildora>
            </span>
          </li>
        ))}
      </ul>
      {nota && <p className="text-sm text-muted-foreground">{nota}</p>}
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        {revision.corrida_id ? (
          <Link
            href={`/corrida/${revision.corrida_id}`}
            className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
          >
            {textos.repesca.hoyCorrida}
            <ArrowRight className="size-4" aria-hidden />
          </Link>
        ) : (
          <span />
        )}
        {proxima && (
          <span className="text-muted-foreground">
            {textos.repesca.proxima(
              new Date(proxima).toLocaleString("es-AR", { weekday: "long", hour: "2-digit", minute: "2-digit" }),
            )}
          </span>
        )}
      </div>
    </section>
  );
}
