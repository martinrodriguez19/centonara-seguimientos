"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";

import { Borrador } from "@/components/borrador";
import { ErrorDeCarga } from "@/components/error-de-carga";
import { Button } from "@/components/ui/button";
import { EsqueletoDeLista } from "@/components/ui/esqueleto";
import {
  enviarCorrida,
  ErrorDeApi,
  liberarMensaje,
  traerEstado,
  traerMensajes,
  validarCorrida,
  type Mensaje,
} from "@/lib/panel";
import { Enviar, type Modo } from "@/components/enviar";
import { textos } from "@/lib/textos";

/**
 * La pantalla donde el dueño revisa una corrida.
 *
 * El orden de arriba abajo es el orden de lo que hay que hacer:
 *
 *   1. Los retenidos, que necesitan una decisión
 *   2. Los listos, que se pueden mirar por arriba
 *   3. Los descartados, que están ahí sólo para que nadie se pregunte a dónde
 *      fueron a parar
 *
 * Y abajo los dos botones de enviar, que dicen **cuántos** van a salir y **en
 * qué modo**. "Enviar" a secas no deja claro si son tres o treinta, ni si
 * llegan a alguien.
 */
export default function Revision({ params }: { params: Promise<{ corrida: string }> }) {
  const { corrida } = use(params);
  const clienteQuery = useQueryClient();
  const [enviado, setEnviado] = useState<{ cuantos: number; modo: Modo } | null>(null);

  const revision = useQuery({
    queryKey: ["mensajes", corrida],
    queryFn: () => traerMensajes(corrida),
  });

  // Para saber si la lista de destinos está abierta. Enviar de verdad con la
  // lista vacía no alcanza a nadie (regla R4), así que el botón lo dice en vez
  // de dejar que alguien apriete y no pase nada.
  const estado = useQuery({ queryKey: ["estado"], queryFn: traerEstado });

  const validar = useMutation({
    mutationFn: () => validarCorrida(corrida),
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["mensajes", corrida] }),
  });

  const enviar = useMutation({
    mutationFn: (modo: Modo) => enviarCorrida(corrida, modo),
    onSuccess: (resultado) => {
      setEnviado({ cuantos: resultado.mensajes, modo: resultado.modo as Modo });
      void clienteQuery.invalidateQueries({ queryKey: ["mensajes", corrida] });
      void clienteQuery.invalidateQueries({ queryKey: ["estado"] });
    },
  });

  if (revision.isPending) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8">
        <EsqueletoDeLista filas={3} />
      </main>
    );
  }
  if (revision.isError) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8">
        <ErrorDeCarga error={revision.error} onReintentar={() => void revision.refetch()} />
      </main>
    );
  }

  const mensajes = revision.data.mensajes;
  const retenidos = mensajes.filter((m) => m.estado === "RETENIDO");
  const listos = mensajes.filter((m) => m.estado === "EN_ESPERA");
  const descartados = mensajes.filter((m) => m.estado === "DESCARTADO");
  const sinValidar = mensajes.filter((m) => m.estado === "BORRADOR");

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">{textos.revision.titulo}</h1>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/panel">{textos.revision.volver}</Link>
        </Button>
      </div>

      {mensajes.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {textos.revision.sinMensajes}
        </p>
      )}

      {/* Los borradores llegan sin pasar por las reglas: alguien tiene que
          dispararlo. Lo normal es que el panel lo haga solo cuando la
          generación termina, pero el botón queda por si quedó a medias. */}
      {sinValidar.length > 0 && (
        <div className="flex items-center gap-3 rounded-lg border bg-muted/40 p-4">
          <p className="flex-1 text-sm">
            {sinValidar.length === 1
              ? "Hay 1 borrador sin revisar por el sistema."
              : `Hay ${sinValidar.length} borradores sin revisar por el sistema.`}
          </p>
          <Button size="sm" disabled={validar.isPending} onClick={() => validar.mutate()}>
            {validar.isPending ? textos.revision.validando : "Revisar ahora"}
          </Button>
        </div>
      )}

      {retenidos.length > 0 && (
        <Grupo
          titulo={textos.revision.retenidos}
          ayuda={textos.revision.retenidosAyuda}
          mensajes={retenidos}
          corrida={corrida}
          accion={<LiberarTodos mensajes={retenidos} corrida={corrida} />}
        />
      )}

      {listos.length > 0 && (
        <Grupo titulo={textos.revision.listos} mensajes={listos} corrida={corrida} />
      )}

      {descartados.length > 0 && (
        <Grupo
          titulo={textos.revision.descartados}
          ayuda={textos.revision.descartadosAyuda}
          mensajes={descartados}
          corrida={corrida}
        />
      )}

      {/* El segundo acto explícito. Nada de esto sale por inacción. */}
      <div className="sticky bottom-0 space-y-2 border-t bg-background/95 py-4 backdrop-blur">
        {enviado !== null ? (
          <p className="text-sm">
            {/* ⚠️ El resultado dice el MODO. "Se encolaron 3 mensajes" a secas
                deja al operador sin saber si acaba de escribirle a un cliente
                real: es la ambigüedad más cara que puede tener esta pantalla. */}
            {enviado.modo === "real"
              ? textos.revision.enviadoReal(enviado.cuantos)
              : textos.revision.enviadoPrueba(enviado.cuantos)}{" "}
            {enviado.modo === "real" && textos.revision.enviarAyuda}
          </p>
        ) : listos.length === 0 ? (
          <p className="text-sm text-muted-foreground">{textos.revision.nadaQueEnviar}</p>
        ) : (
          <>
            <Enviar
              cuantos={listos.length}
              // Ausente mientras carga el estado: hasta saberlo, se asume
              // cerrada. Fallar cerrado también acá (regla R2).
              destinosPermitidos={estado.data?.destinos_permitidos ?? 0}
              enviando={enviar.isPending}
              onEnviar={(modo) => enviar.mutate(modo)}
            />
            {enviar.error instanceof ErrorDeApi && (
              <p className="text-sm text-destructive">{enviar.error.message}</p>
            )}
          </>
        )}
      </div>
    </main>
  );
}

function Grupo({
  titulo,
  ayuda,
  mensajes,
  corrida,
  accion,
}: {
  titulo: string;
  ayuda?: string;
  mensajes: Mensaje[];
  corrida: string;
  accion?: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">
            {titulo}{" "}
            <span className="tabular-nums text-muted-foreground">({mensajes.length})</span>
          </h2>
          {ayuda && <p className="text-sm text-muted-foreground">{ayuda}</p>}
        </div>
        {accion}
      </div>
      <div className="space-y-3">
        {mensajes.map((mensaje) => (
          <Borrador key={mensaje.id} mensaje={mensaje} corridaId={corrida} />
        ))}
      </div>
    </section>
  );
}

/**
 * Liberar todos los retenidos de una vez, escribiendo cuántos son.
 *
 * **Fricción proporcional.** Frenar uno es un click; soltar veinte que el
 * sistema apartó a propósito no puede serlo — es exactamente la acción que
 * alguien apurado haría sin mirar, y es la que el triage existe para evitar.
 *
 * Escribir el número obliga a leerlo, que es todo lo que hace falta.
 */
function LiberarTodos({ mensajes, corrida }: { mensajes: Mensaje[]; corrida: string }) {
  const clienteQuery = useQueryClient();
  const [confirmacion, setConfirmacion] = useState("");
  const [abierto, setAbierto] = useState(false);

  const liberar = useMutation({
    mutationFn: async () => {
      // De a uno y en orden: cada uno pasa por su propia validación en el
      // backend, y si uno falla los demás no se pierden.
      for (const mensaje of mensajes) {
        await liberarMensaje(mensaje.id);
      }
    },
    onSettled: () => {
      setAbierto(false);
      setConfirmacion("");
      void clienteQuery.invalidateQueries({ queryKey: ["mensajes", corrida] });
    },
  });

  if (mensajes.length < 2) return null;

  if (!abierto) {
    return (
      <Button variant="ghost" size="sm" onClick={() => setAbierto(true)}>
        {textos.revision.liberarTodos(mensajes.length)}
      </Button>
    );
  }

  return (
    <div className="space-y-2 rounded-md border border-atencion-borde bg-atencion-suave p-3">
      <p className="max-w-xs text-sm">
        {textos.revision.liberarTodosConfirmar(mensajes.length)}
      </p>
      <div className="flex gap-2">
        <input
          inputMode="numeric"
          aria-label={`Escribí ${mensajes.length} para confirmar`}
          className="w-20 rounded-md border border-input bg-background px-3 py-1.5 text-sm tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={confirmacion}
          onChange={(evento) => setConfirmacion(evento.target.value)}
        />
        <Button
          size="sm"
          disabled={confirmacion !== String(mensajes.length) || liberar.isPending}
          onClick={() => liberar.mutate()}
        >
          {textos.revision.liberar}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setAbierto(false)}>
          {textos.revision.cancelar}
        </Button>
      </div>
    </div>
  );
}
