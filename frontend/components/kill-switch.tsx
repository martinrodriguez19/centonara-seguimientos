"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban, Play } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useAvisos } from "@/components/ui/avisos-flotantes";
import { Confirmacion } from "@/components/ui/dialogo";
import { Aviso } from "@/components/ui/estado";
import { pausarSistema } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * El kill switch.
 *
 * Tres decisiones, y las tres tienen el mismo motivo: el dueño lo va a usar con
 * las manos temblando algún día.
 *
 * 1. **Se ve sin hacer scroll, en todas las pantallas.** Va en la barra
 *    superior, que es `sticky`. Un freno al que hay que ir a buscar no es un
 *    freno.
 * 2. **Una sola confirmación, no tres.** Una guarda que molesta se termina
 *    esquivando, y la que importa es la primera.
 * 3. **Reanudar no confirma nada.** Frenar de más no le hace daño a nadie;
 *    hacer difícil el freno, sí.
 *
 * La confirmación era un `confirm()` del navegador. En una Mac eso aparece como
 * una hoja gris del sistema con botones que dicen "Aceptar" y "Cancelar" —
 * justo en el control donde hace falta leer qué va a pasar. Ahora es el diálogo
 * del panel, sin fricción de escribir: frenar es reversible.
 */
export function KillSwitch({ pausado }: { pausado: boolean }) {
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();
  const [confirmando, setConfirmando] = useState(false);

  const cambiar = useMutation({
    mutationFn: pausarSistema,
    onSuccess: (resultado) => {
      setConfirmando(false);
      avisar(
        resultado.pausado ? textos.killSwitch.avisoFrenado : textos.killSwitch.avisoReanudado,
        resultado.pausado ? "critico" : "ok",
      );
    },
    onError: () => avisar(textos.killSwitch.avisoFallo, "critico"),
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["estado"] }),
  });

  if (pausado) {
    return (
      <Button
        variant="outline"
        size="sm"
        disabled={cambiar.isPending}
        onClick={() => cambiar.mutate(false)}
      >
        <Play className="size-4" aria-hidden />
        {textos.killSwitch.reanudar}
      </Button>
    );
  }

  return (
    <>
      <Button
        variant="destructive"
        size="sm"
        disabled={cambiar.isPending}
        onClick={() => setConfirmando(true)}
      >
        <Ban className="size-4" aria-hidden />
        {textos.killSwitch.frenar}
      </Button>

      <Confirmacion
        abierto={confirmando}
        onCerrar={() => setConfirmando(false)}
        onConfirmar={() => cambiar.mutate(true)}
        titulo={textos.killSwitch.confirmarTitulo}
        confirmar={textos.killSwitch.frenar}
        peligrosa
        ocupado={cambiar.isPending}
      >
        <p>{textos.killSwitch.confirmar}</p>
        <p className="text-muted-foreground">{textos.killSwitch.confirmarNota}</p>
      </Confirmacion>
    </>
  );
}

/**
 * El cartel de "está frenado", separado del botón.
 *
 * Con el sistema pausado, el botón dice "Reanudar" — que por sí solo no
 * comunica que hay algo detenido ahora mismo. Esto lo dice.
 */
export function AvisoFrenado() {
  return (
    <Aviso nivel="critico" titulo={textos.killSwitch.frenado}>
      {textos.killSwitch.frenadoDetalle}
    </Aviso>
  );
}
