"use client";

import { AlertTriangle, ArrowRight, CalendarClock, Cpu, FileText, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { TokenReciente } from "@/components/alta-maquina";
import { BotonCorrida } from "@/components/boton-corrida";
import { ErrorDeCarga } from "@/components/error-de-carga";
import { GrillaDeMaquinas } from "@/components/maquinas/grilla";
import { Pagina, Seccion } from "@/components/navegacion/pagina";
import { Indicador } from "@/components/ui/indicador";
import { EsqueletoDelPanel } from "@/components/ui/esqueleto";
import { useCorridasConTandas, useEstado, useProblemas } from "@/lib/consultas";
import { deHoy, dejadosHoyTotal, ZONA } from "@/lib/derivados";
import { textos } from "@/lib/textos";

/**
 * El inicio (Panel v2).
 *
 * Quien lo usa entra al mediodía, mira, aprieta y se va. Así que tiene cuatro
 * cosas y nada más:
 *
 *   1. Los números de hoy.
 *   2. El botón.
 *   3. Las máquinas.
 *   4. Una sola línea si hay algo **urgente** — nunca la lista.
 *
 * **Lo que se fue, y adónde.** Las alertas, a "Errores y avisos" (antes se
 * pintaban todas acá arriba, cada una como un cartel grande). La banda de modo,
 * al chip de la barra. Las métricas, a "Estadísticas". El alta de máquina, a
 * "Máquinas". El freno sigue en la barra, a la vista en todas las pantallas.
 */
export default function Inicio() {
  const [tokenNuevo, setTokenNuevo] = useState<{ token: string; maquina: string } | null>(null);
  const estado = useEstado();
  const hoy = useCorridasConTandas(deHoy);
  const problemas = useProblemas();

  if (estado.isPending) {
    return (
      <Pagina titulo={textos.inicio.titulo}>
        <EsqueletoDelPanel />
      </Pagina>
    );
  }

  if (estado.isError) {
    return (
      <Pagina titulo={textos.inicio.titulo}>
        <ErrorDeCarga error={estado.error} onReintentar={() => void estado.refetch()} />
      </Pagina>
    );
  }

  const datos = estado.data;
  const maquinasUtiles = datos.maquinas.filter((m) => m.activo && !m.pausada);
  const conectadas = datos.maquinas.filter((m) => m.activo && m.online).length;
  const activas = datos.maquinas.filter((m) => m.activo).length;

  return (
    <Pagina titulo={textos.inicio.titulo} bajada={hoyLargo()}>
      {datos.pausa_global && (
        <LineaDeEstado nivel="critico" texto={textos.killSwitch.frenado} detalle={textos.killSwitch.frenadoDetalle} />
      )}
      {problemas.urgentes > 0 && (
        <LineaDeEstado
          nivel="critico"
          texto={textos.inicio.urgentes(problemas.urgentes)}
          href="/errores"
          enlace={textos.inicio.verErrores}
        />
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Indicador
          etiqueta={textos.inicio.dejadosHoy}
          valor={hoy.cargando ? "—" : dejadosHoyTotal(hoy.corridas)}
          icono={FileText}
        />
        <Indicador etiqueta={textos.inicio.enviadosHoy} valor={datos.enviados_hoy} icono={Send} />
        <Indicador
          etiqueta={textos.inicio.proxima}
          valor={datos.proxima_corrida ? cuandoEs(datos.proxima_corrida) : textos.inicio.apagada}
          icono={CalendarClock}
          chico
        />
        <Indicador
          etiqueta={textos.inicio.enLinea}
          valor={
            <>
              {conectadas}
              <span className="text-base text-muted-foreground"> / {activas}</span>
            </>
          }
          tinta={activas > 0 && conectadas < activas ? "text-atencion" : undefined}
          icono={Cpu}
        />
      </div>

      <BotonCorrida
        maquinas={maquinasUtiles.length}
        pausado={datos.pausa_global}
        enCurso={datos.corrida_en_curso}
        ultima={datos.ultima_corrida}
        envioAutomatico={datos.envio_automatico}
      />

      {tokenNuevo && (
        <TokenReciente token={tokenNuevo.token} maquina={tokenNuevo.maquina} onCerrar={() => setTokenNuevo(null)} />
      )}

      <Seccion
        titulo={
          <>
            {textos.panel.maquinas}{" "}
            <span className="font-mono text-sm font-normal text-muted-foreground tabular-nums">
              {textos.maquinas.conectadas(conectadas, activas)}
            </span>
          </>
        }
        acciones={
          <Link
            href="/maquinas"
            className="inline-flex items-center gap-1 text-sm font-medium text-accion-tinta hover:underline"
          >
            {textos.inicio.verTodas}
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        }
      >
        <GrillaDeMaquinas
          maquinas={datos.maquinas}
          onToken={(token, maquina) => setTokenNuevo({ token, maquina })}
        />
      </Seccion>
    </Pagina>
  );
}

/**
 * Una línea, no un cartel: lo que hay que saber y adónde ir.
 */
function LineaDeEstado({
  nivel,
  texto,
  detalle,
  href,
  enlace,
}: {
  nivel: "critico";
  texto: string;
  detalle?: string;
  href?: string;
  enlace?: string;
}) {
  return (
    <div
      role={nivel === "critico" ? "alert" : "status"}
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-critico-borde bg-critico-suave px-4 py-2.5 text-sm"
    >
      <AlertTriangle className="size-4 shrink-0 text-critico" aria-hidden />
      <span className="font-medium text-critico">{texto}</span>
      {detalle && <span className="text-muted-foreground">{detalle}</span>}
      {href && enlace && (
        <Link href={href} className="ml-auto inline-flex items-center gap-1 font-medium text-critico hover:underline">
          {enlace}
          <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      )}
    </div>
  );
}

/** "lunes 28 de septiembre", en hora argentina. */
function hoyLargo(): string {
  return new Date().toLocaleDateString("es-AR", {
    timeZone: ZONA,
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

/**
 * "hoy 17:00", "mañana 17:00" o "lunes 17:00", en hora argentina (D51).
 *
 * El backend manda el instante en UTC; acá se muestra como lo piensa quien
 * mira el panel, que está en Buenos Aires aunque el navegador diga otra cosa.
 */
function cuandoEs(iso: string): string {
  const cuando = new Date(iso);
  const diaDe = (fecha: Date) =>
    fecha.toLocaleDateString("es-AR", { timeZone: ZONA, year: "numeric", month: "2-digit", day: "2-digit" });
  const hoy = new Date();
  const manana = new Date(hoy.getTime() + 24 * 60 * 60 * 1000);
  const hora = cuando.toLocaleTimeString("es-AR", { timeZone: ZONA, hour: "2-digit", minute: "2-digit" });
  if (diaDe(cuando) === diaDe(hoy)) return `hoy ${hora}`;
  if (diaDe(cuando) === diaDe(manana)) return `mañana ${hora}`;
  const dia = cuando.toLocaleDateString("es-AR", { timeZone: ZONA, weekday: "long" });
  return `${dia} ${hora}`;
}
