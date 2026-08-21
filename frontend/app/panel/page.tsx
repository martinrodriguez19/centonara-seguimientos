"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Alertas } from "@/components/alertas";
import { AltaMaquina, TokenReciente } from "@/components/alta-maquina";
import { BandaModo } from "@/components/banda-modo";
import { BotonCorrida } from "@/components/boton-corrida";
import { AvisoFrenado, KillSwitch } from "@/components/kill-switch";
import { TarjetaMaquina } from "@/components/maquina";
import { Metricas } from "@/components/metricas";
import { Button } from "@/components/ui/button";
import { ErrorDeApi, salir, traerEstado } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * La pantalla principal.
 *
 * Quien la usa entra al mediodía, mira, aprieta y se va. Así que el orden de
 * arriba abajo es el orden en que le importan las cosas:
 *
 *   1. En qué modo está el sistema (banda)
 *   2. Si está frenado
 *   3. El botón
 *   4. Las máquinas
 *
 * El kill switch vive en la barra superior, que es `sticky`: se ve sin hacer
 * scroll por más máquinas que haya.
 */
export default function Panel() {
  const router = useRouter();
  const clienteQuery = useQueryClient();
  const [tokenNuevo, setTokenNuevo] = useState<{ token: string; maquina: string } | null>(null);

  const estado = useQuery({
    queryKey: ["estado"],
    queryFn: traerEstado,
    // Cada cinco segundos: las máquinas laten cada treinta, y una corrida
    // avanza sola. Una pantalla que hay que recargar a mano para ver si algo
    // pasó es una pantalla que nadie mira.
    refetchInterval: 5000,
  });

  const cerrarSesion = useMutation({
    mutationFn: salir,
    onSuccess: () => {
      router.push("/login");
      router.refresh();
    },
  });

  // La cookie dura una jornada. Si venció mientras la pestaña estaba abierta,
  // el reintento automático de la consulta devolvería 401 para siempre; mejor
  // mandar al login que dejar una pantalla congelada sin explicación.
  useEffect(() => {
    if (estado.error instanceof ErrorDeApi && estado.error.esSesionVencida) {
      router.push("/login");
    }
  }, [estado.error, router]);

  if (estado.isPending) {
    return <p className="p-8 text-sm text-muted-foreground">Cargando…</p>;
  }

  if (estado.isError) {
    return (
      <main className="p-8">
        <p className="text-sm text-destructive">
          No se pudo leer el estado del sistema: {estado.error.message}
        </p>
      </main>
    );
  }

  const datos = estado.data;
  const maquinasUtiles = datos.maquinas.filter((m) => m.activo && !m.pausada);

  return (
    <div className="min-h-svh">
      <BandaModo destinosAbiertos={datos.destinos_abiertos} />

      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-3">
          <div className="flex items-baseline gap-4">
            <h1 className="text-lg font-semibold">{textos.panel.titulo}</h1>
            <p className="text-sm tabular-nums text-muted-foreground">
              {textos.panel.enviadosHoy}: <strong>{datos.enviados_hoy}</strong>
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" asChild>
              <Link href="/config">{textos.panel.configuracion}</Link>
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/historial">{textos.panel.historial}</Link>
            </Button>
            {/* El freno, siempre visible. Un freno al que hay que ir a buscar
                no es un freno. */}
            <KillSwitch pausado={datos.pausa_global} />
            <Button
              variant="ghost"
              size="sm"
              disabled={cerrarSesion.isPending}
              onClick={() => cerrarSesion.mutate()}
            >
              {textos.panel.salir}
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-6 py-6">
        {datos.pausa_global && <AvisoFrenado />}

        {/* Arriba de todo: si algo esta mal, es lo primero que hay que leer. */}
        <Alertas />

        <BotonCorrida
          hayMaquinas={maquinasUtiles.length > 0}
          pausado={datos.pausa_global}
          enCurso={datos.corrida_en_curso}
          ultima={datos.ultima_corrida}
        />

        {tokenNuevo && (
          <TokenReciente
            token={tokenNuevo.token}
            maquina={tokenNuevo.maquina}
            onCerrar={() => setTokenNuevo(null)}
          />
        )}

        <Metricas />

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">
              {textos.panel.maquinas}{" "}
              <span className="tabular-nums text-muted-foreground">({datos.maquinas.length})</span>
            </h2>
            <AltaMaquina
              onToken={(token, maquina) => {
                setTokenNuevo({ token, maquina });
                void clienteQuery.invalidateQueries({ queryKey: ["estado"] });
              }}
            />
          </div>

          {datos.maquinas.length === 0 ? (
            <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
              {textos.panel.sinMaquinas}
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {datos.maquinas.map((maquina) => (
                <TarjetaMaquina
                  key={maquina.maquina}
                  maquina={maquina}
                  onToken={(token, nombre) => setTokenNuevo({ token, maquina: nombre })}
                />
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
