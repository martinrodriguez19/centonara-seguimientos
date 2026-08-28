"use client";

import { Send } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { textos } from "@/lib/textos";

/**
 * El botón de Envío real, con su fricción intacta.
 *
 * El de "Dejar borradores" ya no existe (D36): los borradores se dejan solos
 * en los chats al terminar cada redacción — nadie tiene que apretar nada para
 * eso. Lo único que sigue necesitando una persona es el envío REAL, y ése no
 * afloja: pide escribir la cantidad de mensajes que van a salir. Escribir el
 * número obliga a leerlo; un `confirm()` se acepta sin mirar, y esta es
 * exactamente la acción que alguien apurado haría sin mirar.
 *
 * Y con la lista de destinos vacía no se ofrece siquiera: R4 dice que vacía
 * significa a nadie, así que un envío real no alcanzaría a nadie. La pantalla
 * lo explica en vez de dejar que alguien apriete y no pase nada.
 */
export function Enviar({
  cuantos,
  destinosPermitidos,
  enviando,
  onEnviar,
}: {
  cuantos: number;
  destinosPermitidos: number;
  enviando: boolean;
  onEnviar: () => void;
}) {
  const [confirmacion, setConfirmacion] = useState("");
  const [abierto, setAbierto] = useState(false);

  const puedeEnviarDeVerdad = destinosPermitidos > 0;

  if (abierto) {
    return (
      <div className="space-y-2 rounded-md border border-critico-borde bg-critico-suave p-3">
        <p className="max-w-md text-sm font-medium">
          {textos.revision.enviarRealConfirmar(cuantos)}
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            inputMode="numeric"
            autoFocus
            aria-label={`Escribí ${cuantos} para confirmar`}
            className="w-20 rounded-md border border-input bg-background px-3 py-1.5 text-sm tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={confirmacion}
            onChange={(evento) => setConfirmacion(evento.target.value)}
          />
          <Button
            variant="destructive"
            disabled={confirmacion !== String(cuantos) || enviando}
            onClick={() => onEnviar()}
          >
            <Send className="size-4" aria-hidden />
            {enviando ? textos.revision.enviando : textos.revision.enviarRealBoton(cuantos)}
          </Button>
          <Button
            variant="ghost"
            disabled={enviando}
            onClick={() => {
              setAbierto(false);
              setConfirmacion("");
            }}
          >
            {textos.revision.cancelar}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <Button
        size="lg"
        variant="destructive"
        disabled={enviando || !puedeEnviarDeVerdad}
        onClick={() => setAbierto(true)}
      >
        <Send className="size-4" aria-hidden />
        {textos.revision.modoReal}
      </Button>
      <p className="max-w-sm text-sm text-muted-foreground">
        {puedeEnviarDeVerdad
          ? textos.revision.modoRealDetalle
          : textos.revision.modoRealSinDestinos}
      </p>
    </div>
  );
}
