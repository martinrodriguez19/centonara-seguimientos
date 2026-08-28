"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban, Check, Pencil } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Aviso, Pildora } from "@/components/ui/estado";
import {
  editarMensaje,
  ErrorDeApi,
  liberarMensaje,
  vetarMensaje,
  type Mensaje,
} from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Un borrador en la pantalla de revisión.
 *
 * Lo que decide cómo se ve: **por qué se apartó**. Un retenido sin motivo
 * obliga a releer el chat entero para adivinar qué le llamó la atención al
 * sistema, y nadie hace eso veinte veces — termina liberando todo sin mirar,
 * que es peor que no tener triage.
 */
export function Borrador({ mensaje, corridaId }: { mensaje: Mensaje; corridaId: string }) {
  const clienteQuery = useQueryClient();
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState(mensaje.texto);

  const refrescar = () =>
    clienteQuery.invalidateQueries({ queryKey: ["mensajes", corridaId] });

  const guardar = useMutation({
    mutationFn: () => editarMensaje(mensaje.id, texto),
    onSuccess: () => {
      setEditando(false);
      void refrescar();
    },
  });

  const vetar = useMutation({ mutationFn: () => vetarMensaje(mensaje.id), onSettled: refrescar });
  const liberar = useMutation({
    mutationFn: () => liberarMensaje(mensaje.id),
    onSettled: refrescar,
  });

  const descartado = mensaje.estado === "DESCARTADO";
  // Un mensaje que ya está (o está quedando) en el chat no se toca desde acá
  // (D36): editarlo o vetarlo no cambiaría lo escrito en WhatsApp — quedarían
  // desincronizados, que es peor que no poder tocarlo.
  const enElChat = mensaje.estado === "BORRADOR_DEJADO" || mensaje.estado === "ENVIANDO";
  // El backend devuelve 422 con los problemas si el texto editado viola algo.
  // Un humano también puede empeorar un mensaje.
  const problema = guardar.error instanceof ErrorDeApi ? guardar.error.message : null;

  return (
    <Card className={descartado ? "opacity-60" : undefined}>
      <CardContent className="space-y-3 pt-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-medium">{mensaje.contacto_nombre || "Sin nombre"}</p>
            <p className="truncate font-mono text-xs text-muted-foreground">
              {mensaje.contacto_id} · {mensaje.maquina}
            </p>
          </div>
          {mensaje.editado_por && (
            <Pildora nivel="neutro" conIcono={false}>
              Editado
            </Pildora>
          )}
          {descartado && <Pildora nivel="critico">{textos.revision.vetado}</Pildora>}
          {mensaje.estado === "BORRADOR_DEJADO" && (
            <Pildora nivel="ok">{textos.revision.enElChat}</Pildora>
          )}
          {mensaje.estado === "ENVIANDO" && (
            <Pildora nivel="neutro" conIcono={false}>
              {textos.revision.escribiendose}
            </Pildora>
          )}
        </div>

        {/* ⚠️ Por qué se apartó — o, para un borrador ya dejado, qué le llamó
            la atención al sistema (D36: información, no un freno). Es lo único
            que convierte "revisá esto" en una decisión de cinco segundos. */}
        {mensaje.senales.length > 0 && (
          <Aviso
            nivel={descartado ? "critico" : "atencion"}
            titulo={
              descartado
                ? "Por qué no va a salir"
                : enElChat
                  ? "Para tener en cuenta antes de mandarlo"
                  : "Por qué lo apartamos"
            }
            className="p-3"
          >
            <ul className="space-y-0.5">
              {mensaje.senales.map((senal) => (
                <li key={senal}>{textos.senales[senal] ?? senal}</li>
              ))}
            </ul>
          </Aviso>
        )}

        {/* `motivo` llegaba del backend en cada mensaje y no se mostraba en
            ningún lado. Es lo que distingue "lo frenaste vos" de "una regla lo
            frenó", que para quien revisa son cosas distintas. */}
        {mensaje.motivo && (
          <p className="text-sm">
            <span className="font-medium">Motivo:</span>{" "}
            <span className="text-muted-foreground">
              {textos.motivos[mensaje.motivo] ?? mensaje.motivo}
            </span>
          </p>
        )}

        {mensaje.resumen && (
          <p className="text-sm text-muted-foreground">
            <span className="font-medium">De qué se hablaba:</span> {mensaje.resumen}
          </p>
        )}

        {editando ? (
          <div className="space-y-2">
            <textarea
              rows={4}
              autoFocus
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={texto}
              onChange={(evento) => setTexto(evento.target.value)}
            />
            {problema && <p className="text-sm text-destructive">{problema}</p>}
            <div className="flex gap-2">
              <Button size="sm" disabled={guardar.isPending} onClick={() => guardar.mutate()}>
                {textos.revision.guardar}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setTexto(mensaje.texto);
                  setEditando(false);
                  guardar.reset();
                }}
              >
                {textos.revision.cancelar}
              </Button>
            </div>
          </div>
        ) : (
          <p className="whitespace-pre-wrap rounded-md bg-muted/50 p-3 text-sm">{mensaje.texto}</p>
        )}

        {!descartado && !enElChat && !editando && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="ghost" onClick={() => setEditando(true)}>
              <Pencil className="size-4" aria-hidden />
              {textos.revision.editar}
            </Button>

            {mensaje.estado === "RETENIDO" && (
              <Button size="sm" disabled={liberar.isPending} onClick={() => liberar.mutate()}>
                <Check className="size-4" aria-hidden />
                {textos.revision.liberar}
              </Button>
            )}

            {/* Vetar de a uno es un click: frenar de más no le hace daño a
                nadie, y ponerle fricción sólo lograría que alguien no lo use. */}
            <Button
              size="sm"
              variant="ghost"
              disabled={vetar.isPending}
              onClick={() => vetar.mutate()}
            >
              <Ban className="size-4" aria-hidden />
              {textos.revision.vetar}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
