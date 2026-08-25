"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Loader2, Play, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Confirmacion } from "@/components/ui/dialogo";
import {
  cancelarCorrida,
  dispararCorrida,
  ErrorDeApi,
  traerConfiguracion,
  type Corrida,
} from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * El botón. Lo único que arranca el sistema.
 *
 * No hay cron y no hay temporizador: si nadie lo aprieta, no pasa nada. Eso es
 * una característica — el dueño sabe siempre por qué salieron mensajes hoy.
 *
 * **Son dos botones y no uno**, porque son dos cosas distintas y una cuesta
 * dinero:
 *
 * - **Generar seguimientos** abre WhatsApp en cada máquina, lee los chats
 *   fríos y redacta. Tarda minutos y se paga por chat leído, así que confirma.
 * - **Correr diagnóstico** sólo pregunta a cada máquina si está lista. Es
 *   gratis, no toca ningún chat y no confirma nada: ponerle fricción a algo
 *   inofensivo sólo logra que nadie lo use.
 *
 * Antes había un solo botón y llamaba siempre a `dispararCorrida("diagnostico")`,
 * con lo cual el producto —generar borradores— no se podía pedir desde el panel.
 *
 * Y **enviar sigue siendo un tercer acto explícito**, en la pantalla de
 * revisión. Esto genera borradores y se detiene. Nada sale por inacción.
 */
export function BotonCorrida({
  maquinas,
  pausado,
  enCurso,
  ultima,
}: {
  /** Cuántas máquinas activas y sin pausar van a recibir trabajo. */
  maquinas: number;
  pausado: boolean;
  enCurso: Corrida | null;
  ultima: Corrida | null;
}) {
  const clienteQuery = useQueryClient();
  const [confirmando, setConfirmando] = useState(false);
  const [cancelando, setCancelando] = useState(false);

  // Para decir en la confirmación cuántos chats va a leer cada máquina. Misma
  // clave que usa la pantalla de configuración, así que sale de la caché.
  const config = useQuery({ queryKey: ["configuracion"], queryFn: traerConfiguracion });

  const disparar = useMutation({
    mutationFn: (tipo: "diagnostico" | "generacion") => dispararCorrida(tipo),
    onSuccess: () => setConfirmando(false),
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["estado"] }),
  });

  const cancelar = useMutation({
    mutationFn: (id: string) => cancelarCorrida(id),
    onSuccess: () => setCancelando(false),
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["estado"] }),
  });

  if (enCurso) {
    const hechos = enCurso.jobs.total - enCurso.jobs.pendientes;
    return (
      <div className="flex items-center gap-3 rounded-lg border bg-muted/40 px-4 py-3">
        <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">
            {textos.boton.enCurso}
            {/* Qué corrida es. "En curso" a secas no distingue un diagnóstico
                de treinta segundos de una generación de diez minutos. */}
            <span className="ml-2 font-normal text-muted-foreground">
              {enCurso.tipo === "generacion" ? "· generando seguimientos" : "· diagnóstico"}
            </span>
          </p>
          <p className="text-sm tabular-nums text-muted-foreground">
            {textos.boton.progreso(hechos, enCurso.jobs.total)}
          </p>
        </div>
        {/* La salida de emergencia: sin esto, una corrida con un job trabado
            deja el panel "en movimiento" para siempre y el botón preso. */}
        <Button
          variant="ghost"
          size="sm"
          disabled={cancelar.isPending}
          onClick={() => setCancelando(true)}
        >
          <X className="size-4" aria-hidden />
          {textos.boton.cancelar}
        </Button>

        <Confirmacion
          abierto={cancelando}
          onCerrar={() => setCancelando(false)}
          onConfirmar={() => cancelar.mutate(enCurso.id)}
          titulo={textos.boton.confirmarCancelarTitulo}
          confirmar={textos.boton.cancelar}
          peligrosa
          ocupado={cancelar.isPending}
        >
          <p>{textos.boton.confirmarCancelar}</p>
        </Confirmacion>
      </div>
    );
  }

  const impedido = maquinas === 0 || pausado;
  const chats = config.data?.n_chats_por_defecto ?? 20;

  // Una generación que terminó deja borradores esperando una decisión. Que la
  // pantalla no lo diga es la forma más fácil de que nadie los mire nunca.
  const hayQueRevisar = ultima?.terminada && ultima.tipo === "generacion";

  return (
    <div className="space-y-3">
      {hayQueRevisar && (
        <Button variant="outline" asChild>
          <Link href={`/revision/${ultima.id}`}>
            <ClipboardList className="size-4" aria-hidden />
            {textos.boton.revisarBorradores}
          </Link>
        </Button>
      )}

      {confirmando ? (
        <ConfirmarGeneracion
          maquinas={maquinas}
          chats={chats}
          enviando={disparar.isPending}
          onConfirmar={() => disparar.mutate("generacion")}
          onCancelar={() => {
            setConfirmando(false);
            disparar.reset();
          }}
        />
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="lg" disabled={impedido || disparar.isPending} onClick={() => setConfirmando(true)}>
            <Play className="size-4" aria-hidden />
            {disparar.isPending ? textos.boton.disparando : textos.boton.disparar}
          </Button>

          {/* Secundario a propósito: el que importa es el de arriba. Éste es
              la herramienta de cuando algo no anda. */}
          <Button
            variant="outline"
            disabled={impedido || disparar.isPending}
            onClick={() => disparar.mutate("diagnostico")}
          >
            {textos.boton.diagnostico}
          </Button>
        </div>
      )}

      {!confirmando && (
        <p className="text-sm text-muted-foreground">{textos.boton.diagnosticoAyuda}</p>
      )}

      {/* "No pasó nada" sin explicación es peor que un mensaje: si el botón
          está deshabilitado, la pantalla dice por qué. */}
      {maquinas === 0 && <p className="text-sm text-muted-foreground">{textos.boton.sinMaquinas}</p>}

      {disparar.error instanceof ErrorDeApi && (
        <p className="text-sm text-destructive">{disparar.error.message}</p>
      )}
    </div>
  );
}

/**
 * La confirmación de una generación.
 *
 * Dice **cuánto trabajo se está pidiendo** —cuántas máquinas y cuántos chats
 * cada una— porque eso es lo que decide si alguien quiere apretar. Un
 * "¿confirmás?" a secas no deja decidir nada y se acepta sin leer.
 *
 * No pide escribir un número: eso está reservado para las acciones que le
 * llegan a una persona de afuera —liberar retenidos en lote, enviar de
 * verdad—. Generar de más cuesta plata, que se recupera; mandar de más, no.
 */
function ConfirmarGeneracion({
  maquinas,
  chats,
  enviando,
  onConfirmar,
  onCancelar,
}: {
  maquinas: number;
  chats: number;
  enviando: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
}) {
  return (
    <div className="space-y-3 rounded-lg border bg-muted/40 p-4">
      <div>
        <p className="font-medium">{textos.boton.generarConfirmarTitulo}</p>
        <p className="text-sm text-muted-foreground">
          {textos.boton.generarConfirmarDetalle(maquinas, chats)}
        </p>
      </div>
      <p className="text-sm text-muted-foreground">{textos.boton.generarConfirmarNota}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="lg" disabled={enviando} onClick={onConfirmar}>
          <Play className="size-4" aria-hidden />
          {enviando ? textos.boton.disparando : textos.boton.generarConfirmar}
        </Button>
        <Button variant="ghost" disabled={enviando} onClick={onCancelar}>
          {textos.revision.cancelar}
        </Button>
      </div>
    </div>
  );
}
