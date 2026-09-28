"use client";

import Link from "next/link";
import { Tabs } from "radix-ui";
import { use, useState } from "react";

import { TokenReciente } from "@/components/alta-maquina";
import { ErrorDeCarga } from "@/components/error-de-carga";
import { ListaDeErrores } from "@/components/errores/lista";
import { MenuDeAcciones, useAccionesDeMaquina } from "@/components/maquinas/acciones";
import { Actividad, Chequeos, HistorialDeMaquina, Mensajes, Resumen } from "@/components/maquinas/detalle";
import { Pagina } from "@/components/navegacion/pagina";
import { Button } from "@/components/ui/button";
import { EsqueletoDelPanel } from "@/components/ui/esqueleto";
import { Punto } from "@/components/ui/estado";
import { useConfiguracion, useCorridasConTandas, useEstado, useProblemas } from "@/lib/consultas";
import { deHoy, dejadosHoy, situacion } from "@/lib/derivados";
import type { Maquina } from "@/lib/panel";
import { textos } from "@/lib/textos";
import { cn } from "@/lib/utils";

const t = textos.maquinas;
const MIGAS = [{ href: "/maquinas", texto: textos.navegacion.maquinas }];

/**
 * El detalle de una máquina (Panel v2).
 *
 * Lo que antes había que ir a buscar a la Mac o a los logs —qué chequeo falla,
 * qué versión corre, qué dejó cada corrida, por qué salteó— en una sola
 * página. Se refresca con el estado, cada cinco segundos.
 */
export default function DetalleDeMaquina({ params }: { params: Promise<{ maquina: string }> }) {
  const { maquina: crudo } = use(params);
  const id = decodeURIComponent(crudo);
  const estado = useEstado();

  if (estado.isPending) {
    return (
      <Pagina titulo={id} migas={MIGAS}>
        <EsqueletoDelPanel />
      </Pagina>
    );
  }
  if (estado.isError) {
    return (
      <Pagina titulo={id} migas={MIGAS}>
        <ErrorDeCarga error={estado.error} onReintentar={() => void estado.refetch()} />
      </Pagina>
    );
  }

  const maquina = estado.data.maquinas.find((m) => m.maquina === id);
  if (!maquina) {
    return (
      <Pagina titulo={id} migas={MIGAS}>
        <div className="rounded-xl border border-dashed bg-card p-8 text-center">
          <p className="font-medium">{t.noEncontrada}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t.noEncontradaDetalle}</p>
          <Button asChild variant="outline" size="sm" className="mt-4">
            <Link href="/maquinas">{t.volverALista}</Link>
          </Button>
        </div>
      </Pagina>
    );
  }

  return <Detalle maquina={maquina} />;
}

function Detalle({ maquina }: { maquina: Maquina }) {
  const [tokenNuevo, setTokenNuevo] = useState<string | null>(null);
  const acciones = useAccionesDeMaquina(maquina, (token) => setTokenNuevo(token));
  const hoy = useCorridasConTandas(deHoy);
  const config = useConfiguracion();
  const problemas = useProblemas();
  const estado = situacion(maquina);
  const errores = problemas.nuevos.filter((p) => p.maquina === maquina.maquina).length;

  return (
    <Pagina
      migas={MIGAS}
      titulo={
        <span className="flex items-center gap-3">
          <Punto nivel={estado.nivel} latiendo={estado.nivel === "ok"} />
          {maquina.nombre}
        </span>
      }
      bajada={
        <>
          <span className="font-mono">{maquina.maquina}</span> · {estado.texto}
        </>
      }
      acciones={
        <>
          {maquina.activo && (
            <Button variant="outline" size="sm" disabled={acciones.pausar.isPending} onClick={acciones.pausarPorHoy}>
              {acciones.pausadaPorHoy ? textos.maquina.reanudarHoy : textos.maquina.pausarPorHoy}
            </Button>
          )}
          <Button
            variant={maquina.activo ? "outline" : "default"}
            size="sm"
            disabled={acciones.activar.isPending}
            onClick={() => acciones.activar.mutate(!maquina.activo)}
          >
            {maquina.activo ? textos.maquina.desactivar : textos.maquina.activar}
          </Button>
          <MenuDeAcciones maquina={maquina} acciones={acciones} />
        </>
      }
    >
      {tokenNuevo && <TokenReciente token={tokenNuevo} maquina={maquina.maquina} onCerrar={() => setTokenNuevo(null)} />}

      <Tabs.Root defaultValue="resumen" className="space-y-5">
        <Tabs.List aria-label={maquina.nombre} className="-mx-4 flex gap-1 overflow-x-auto border-b px-4 sm:mx-0 sm:px-0">
          {(Object.keys(t.pestanas) as (keyof typeof t.pestanas)[]).map((clave) => (
            <Tabs.Trigger
              key={clave}
              value={clave}
              className={cn(
                "relative -mb-px inline-flex items-center gap-1.5 border-b-2 border-transparent px-3 py-2.5 text-sm font-medium whitespace-nowrap text-muted-foreground outline-none",
                "hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
                "data-[state=active]:border-accion data-[state=active]:text-foreground",
              )}
            >
              {t.pestanas[clave]}
              {clave === "errores" && errores > 0 && (
                <span className="rounded-full bg-muted-foreground/15 px-1.5 font-mono text-[10px] tabular-nums">{errores}</span>
              )}
              {clave === "chequeos" && maquina.chequeos_fallando.length > 0 && (
                <span className="rounded-full bg-atencion-suave px-1.5 font-mono text-[10px] text-atencion tabular-nums">
                  {maquina.chequeos_fallando.length}
                </span>
              )}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <Tabs.Content value="resumen" className="outline-none">
          <Resumen
            maquina={maquina}
            acciones={acciones}
            dejadosHoy={hoy.cargando ? undefined : dejadosHoy(hoy.corridas, maquina.maquina)}
            topeDelDia={config.data?.tope_diario_borradores}
          />
        </Tabs.Content>
        <Tabs.Content value="chequeos" className="outline-none">
          <Chequeos maquina={maquina} />
        </Tabs.Content>
        <Tabs.Content value="actividad" className="outline-none">
          <Actividad maquina={maquina} />
        </Tabs.Content>
        <Tabs.Content value="mensajes" className="outline-none">
          <Mensajes maquina={maquina} />
        </Tabs.Content>
        <Tabs.Content value="errores" className="outline-none">
          <ListaDeErrores filtro={maquina.maquina} />
        </Tabs.Content>
        <Tabs.Content value="historial" className="outline-none">
          <HistorialDeMaquina maquina={maquina} />
        </Tabs.Content>
      </Tabs.Root>

      {acciones.dialogos}
    </Pagina>
  );
}
