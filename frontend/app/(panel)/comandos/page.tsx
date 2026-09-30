"use client";

import { Tabs } from "radix-ui";
import { useEffect, useState } from "react";

import { Comando } from "@/components/comando";
import { Pagina } from "@/components/navegacion/pagina";
import { sistemas, type Paso, type Problema, type Sistema } from "@/lib/guia";
import { textos } from "@/lib/textos";
import { cn } from "@/lib/utils";

/**
 * La guía de instalación y reparación, adentro del panel.
 *
 * Existe porque el momento en que hace falta es siempre el mismo: alguien está
 * parado frente a la computadora de un vendedor, algo no anda, y la guía está
 * en un PDF que quedó en otra máquina. El panel ya está abierto —es desde
 * donde se mira si la máquina está online—, así que la guía tiene que estar
 * ahí, y tiene que servir para **cualquiera de las computadoras del parque**:
 * Mac, Mac vieja, Windows.
 *
 * Una pestaña por sistema, los mismos nueve pasos en todas, y al final de cada
 * una la tabla "si algo no anda". El contenido está en `lib/guia.ts`.
 *
 * La pestaña elegida va en el hash de la URL (`#windows`), así que un enlace
 * a la guía de Windows se puede mandar por WhatsApp.
 */
export default function Guia() {
  // Arranca en "mac" también en el cliente, y recién montada mira el hash: la
  // página se prerenderiza, y si el primer render del cliente eligiera otra
  // pestaña que el servidor, React avisaría un desajuste de hidratación.
  const [sistema, setSistema] = useState<Sistema["id"]>("mac");
  useEffect(() => {
    const delHash = desdeElHash();
    if (delHash !== "mac") setSistema(delHash);
  }, []);

  return (
    <Pagina titulo={textos.comandos.titulo} bajada={textos.comandos.intro}>
      <p className="rounded-xl border border-atencion-borde bg-atencion-suave px-4 py-2.5 text-sm text-atencion">
        {textos.comandos.aviso}
      </p>

      <Tabs.Root
        value={sistema}
        onValueChange={(valor) => {
          setSistema(valor as Sistema["id"]);
          window.history.replaceState(null, "", `#${valor}`);
        }}
        className="space-y-6"
      >
        <Tabs.List aria-label={textos.comandos.sistema} className="-mx-4 flex gap-1 overflow-x-auto border-b px-4 sm:mx-0 sm:px-0">
          {sistemas.map((s) => (
            <Tabs.Trigger
              key={s.id}
              value={s.id}
              className={cn(
                "-mb-px inline-flex items-center border-b-2 border-transparent px-3 py-2.5 text-sm font-medium whitespace-nowrap text-muted-foreground outline-none",
                "hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
                "data-[state=active]:border-accion data-[state=active]:text-foreground",
              )}
            >
              {s.titulo}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        {sistemas.map((s) => (
          <Tabs.Content key={s.id} value={s.id} className="outline-none">
            <Cuerpo sistema={s} />
          </Tabs.Content>
        ))}
      </Tabs.Root>

      <p className="text-sm text-muted-foreground">{textos.comandos.pie}</p>
    </Pagina>
  );
}

function desdeElHash(): Sistema["id"] {
  if (typeof window === "undefined") return "mac";
  const hash = window.location.hash.replace("#", "");
  return sistemas.some((s) => s.id === hash) ? (hash as Sistema["id"]) : "mac";
}

function Cuerpo({ sistema }: { sistema: Sistema }) {
  const enlace = "flex gap-2 rounded-lg px-2 py-1.5 text-muted-foreground hover:bg-card hover:text-foreground";
  return (
    <div className="grid gap-6 lg:grid-cols-[15rem_1fr]">
      {/* El índice. Con nueve pasos y treinta comandos, entrar por arriba y
          scrollear hasta encontrar el que se busca es exactamente lo que no
          sirve cuando algo está roto. */}
      <aside className="lg:sticky lg:top-20 lg:self-start">
        <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{textos.comandos.pasos}</p>
        <ol className="space-y-0.5 text-sm">
          {sistema.pasos.map((paso, i) => (
            <li key={paso.id}>
              <a href={`#${sistema.id}-${paso.id}`} className={enlace}>
                <span className="w-4 shrink-0 font-mono text-xs text-muted-foreground/70 tabular-nums">{i + 1}</span>
                <span>{paso.titulo}</span>
              </a>
            </li>
          ))}
          {sistema.problemas && (
            <li>
              <a href={`#${sistema.id}-problemas`} className={enlace}>
                <span className="w-4 shrink-0 font-mono text-xs text-muted-foreground/70">?</span>
                <span>{textos.comandos.problemas}</span>
              </a>
            </li>
          )}
        </ol>
      </aside>

      <div className="min-w-0 space-y-6">
        <div className="rounded-xl border bg-card px-5 py-4 sombra-suave">
          <p className="text-sm">{sistema.descripcion}</p>
          {sistema.donde && <p className="mt-2 text-sm text-muted-foreground">{sistema.donde}</p>}
        </div>

        {sistema.pasos.map((paso, i) => (
          <PasoDeLaGuia key={paso.id} sistema={sistema.id} numero={i + 1} paso={paso} />
        ))}

        {sistema.problemas && <Problemas sistema={sistema.id} problemas={sistema.problemas} />}
      </div>
    </div>
  );
}

function PasoDeLaGuia({ sistema, numero, paso }: { sistema: string; numero: number; paso: Paso }) {
  return (
    <section id={`${sistema}-${paso.id}`} className="scroll-mt-20 rounded-xl border bg-card sombra-suave">
      <header className="flex items-baseline gap-3 border-b px-5 py-4">
        <span className="font-mono text-sm text-accion-tinta tabular-nums">{numero}</span>
        <h2 className="text-[15px] font-semibold">{paso.titulo}</h2>
      </header>
      <div className="space-y-4 px-5 py-4">
        {/* El aviso va ANTES de todo, no después: en el apartado de macOS viejo
            lo que dice es que hay algo para probar primero, y leerlo al final es
            haber perdido la tarde. */}
        {paso.aviso && (
          <p className="rounded-lg border border-atencion-borde bg-atencion-suave px-3 py-2 text-sm text-atencion">{paso.aviso}</p>
        )}
        {paso.intro && <p className="text-sm">{paso.intro}</p>}
        {paso.items && (
          <ul className="space-y-2 text-sm">
            {paso.items.map((item) => (
              <li key={item} className="flex gap-2.5">
                <span className="mt-[0.55em] size-1.5 shrink-0 rounded-full bg-accion" aria-hidden />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        )}
        {paso.comandos && (
          <div className="space-y-5 pt-1">
            {paso.comandos.map((comando) => (
              <Comando key={comando.id} datos={comando} />
            ))}
          </div>
        )}
        {paso.pie && <p className="border-t pt-4 text-sm text-muted-foreground">{paso.pie}</p>}
      </div>
    </section>
  );
}

function Problemas({ sistema, problemas }: { sistema: string; problemas: Problema[] }) {
  const etiqueta = "text-xs font-medium text-muted-foreground uppercase sm:sr-only";
  return (
    <section id={`${sistema}-problemas`} className="scroll-mt-20 rounded-xl border bg-card sombra-suave">
      <header className="flex items-baseline gap-3 border-b px-5 py-4">
        <span className="font-mono text-sm text-accion-tinta">?</span>
        <h2 className="text-[15px] font-semibold">{textos.comandos.problemas}</h2>
      </header>
      <div className="hidden grid-cols-3 gap-4 border-b px-5 py-2 text-xs font-medium text-muted-foreground uppercase sm:grid">
        <span>{textos.comandos.sintoma}</span>
        <span>{textos.comandos.queEs}</span>
        <span>{textos.comandos.queHacer}</span>
      </div>
      <dl className="divide-y">
        {problemas.map((p) => (
          <div key={p.sintoma} className="grid gap-1 px-5 py-4 text-sm sm:grid-cols-3 sm:gap-4">
            <div>
              <dt className={etiqueta}>{textos.comandos.sintoma}</dt>
              <dd className="font-medium">{p.sintoma}</dd>
            </div>
            <div>
              <dt className={etiqueta}>{textos.comandos.queEs}</dt>
              <dd className="text-muted-foreground">{p.queEs}</dd>
            </div>
            <div>
              <dt className={etiqueta}>{textos.comandos.queHacer}</dt>
              <dd>{p.queHacer}</dd>
            </div>
          </div>
        ))}
      </dl>
    </section>
  );
}
