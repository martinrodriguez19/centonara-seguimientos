"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  KeyRound,
  MoreHorizontal,
  Pause,
  Play,
  Power,
  PowerOff,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { DropdownMenu } from "radix-ui";
import { useState } from "react";

import { useAvisos } from "@/components/ui/avisos-flotantes";
import { Button } from "@/components/ui/button";
import { Confirmacion } from "@/components/ui/dialogo";
import { bajaMaquina, editarMaquina, rotarToken, type Maquina } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Todo lo que se le puede hacer a una máquina, en un solo lugar.
 *
 * Antes vivía adentro de la tarjeta, con sus cinco botones siempre a la vista.
 * Ahora lo usan dos pantallas —el menú `⋯` de la tarjeta y la página de detalle
 * (Panel v2)— y las dos llaman exactamente a las mismas mutaciones de siempre:
 * `PATCH /vendedores/{maquina}`, `POST …/token`, `DELETE …`. Nada nuevo del
 * lado del servidor.
 */

/** Pausar por hoy es hasta las 23:59 de hoy, hora de la computadora que mira. */
function finDelDia(): string {
  const hasta = new Date();
  hasta.setHours(23, 59, 59, 999);
  return hasta.toISOString();
}

/**
 * Quitar la pausa es mandar un `pausado_hasta` **en el pasado**, no `null`.
 *
 * El backend ignora los campos en `null` del PATCH y contesta 400 "no hay nada
 * que cambiar": así "Quitar la pausa" nunca funcionó (30/09/2026). Como una
 * máquina está pausada mientras `pausado_hasta` sea futuro, una fecha de hace
 * un minuto la despausa con el mismo endpoint de siempre. Un minuto y no "ahora"
 * por si el reloj de esta computadora va adelantado respecto del servidor.
 *
 * Lo que esto NO suelta es el freno del canario (D35): ése lo levanta reanudar
 * o cancelar la corrida, y el aviso lo dice.
 */
function haceUnMinuto(): string {
  return new Date(Date.now() - 60_000).toISOString();
}

export function useAccionesDeMaquina(
  maquina: Maquina,
  onToken?: (token: string, nombre: string) => void,
) {
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();
  const [dandoDeBaja, setDandoDeBaja] = useState(false);
  const [consintiendo, setConsintiendo] = useState(false);
  const [reiniciando, setReiniciando] = useState<"barrido" | "ventana" | null>(null);

  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ["estado"] });
  const fallo = () => avisar(textos.maquina.avisoFallo, "critico");

  const activar = useMutation({
    mutationFn: (activo: boolean) => editarMaquina(maquina.maquina, { activo }),
    onSuccess: (_, activo) =>
      avisar(activo ? textos.maquina.avisoActivada : textos.maquina.avisoDesactivada),
    onError: fallo,
    onSettled: refrescar,
  });

  // "Pausar por hoy" es de otra persona que activar: activar lo decide el
  // dueño, pausar lo decide el vendedor sobre su propia máquina.
  const pausar = useMutation({
    mutationFn: ({ hasta }: { hasta: string; pausar: boolean }) =>
      editarMaquina(maquina.maquina, { pausado_hasta: hasta }),
    onSuccess: (_, { pausar }) =>
      avisar(pausar ? textos.maquina.avisoPausada : textos.maquina.avisoDespausada),
    onError: fallo,
    onSettled: refrescar,
  });

  const tope = useMutation({
    mutationFn: (tope_diario: number) => editarMaquina(maquina.maquina, { tope_diario }),
    onSuccess: () => avisar(textos.maquina.avisoTope),
    onError: fallo,
    onSettled: refrescar,
  });

  const rotar = useMutation({
    mutationFn: () => rotarToken(maquina.maquina),
    onSuccess: (nuevo) => onToken?.(nuevo.token, nuevo.maquina),
    onError: fallo,
    onSettled: refrescar,
  });

  // Borra el cursor del barrido (D27) o de la ventana (D43). El anti-duplicado
  // sigue protegiendo a los ya contactados, así que reiniciar no re-escribe a
  // nadie. Antes esto era un `confirm()` del navegador.
  const reiniciar = useMutation({
    mutationFn: (cual: "barrido" | "ventana") =>
      editarMaquina(
        maquina.maquina,
        cual === "barrido" ? { reiniciar_barrido: true } : { reiniciar_ventana: true },
      ),
    onSuccess: () => {
      setReiniciando(null);
      avisar(textos.maquinas.avisoReiniciado);
    },
    onError: fallo,
    onSettled: refrescar,
  });

  const baja = useMutation({
    mutationFn: () => bajaMaquina(maquina.maquina),
    onSuccess: () => {
      setDandoDeBaja(false);
      avisar(textos.maquina.avisoBaja(maquina.nombre));
    },
    onError: fallo,
    onSettled: refrescar,
  });

  const consentir = useMutation({
    mutationFn: () => editarMaquina(maquina.maquina, { acepto_condiciones: true }),
    onSuccess: () => {
      setConsintiendo(false);
      avisar(textos.maquina.avisoConsentimiento);
    },
    onError: fallo,
    onSettled: refrescar,
  });

  const pausadaPorHoy = maquina.activo && maquina.pausada;

  const dialogos = (
    <>
      {/* Dar de baja borra la máquina y revoca su token: no se deshace con otro
          click, así que confirma. */}
      <Confirmacion
        abierto={dandoDeBaja}
        onCerrar={() => setDandoDeBaja(false)}
        onConfirmar={() => baja.mutate()}
        titulo={textos.maquina.confirmarBajaTitulo(maquina.nombre)}
        confirmar={textos.maquina.darDeBaja}
        peligrosa
        ocupado={baja.isPending}
      >
        <p>{textos.maquina.confirmarBaja}</p>
      </Confirmacion>

      {/* Registrarlo es afirmar que la conversación con el vendedor ya pasó:
          por eso confirma y queda en la auditoría con fecha. */}
      <Confirmacion
        abierto={consintiendo}
        onCerrar={() => setConsintiendo(false)}
        onConfirmar={() => consentir.mutate()}
        titulo={textos.maquina.confirmarConsentimientoTitulo}
        confirmar={textos.maquina.registrarConsentimiento}
        ocupado={consentir.isPending}
      >
        <p>{textos.maquina.confirmarConsentimiento(maquina.nombre)}</p>
        <p className="text-muted-foreground">{textos.maquina.confirmarConsentimientoNota}</p>
      </Confirmacion>

      <Confirmacion
        abierto={reiniciando !== null}
        onCerrar={() => setReiniciando(null)}
        onConfirmar={() => reiniciando && reiniciar.mutate(reiniciando)}
        titulo={
          reiniciando === "ventana"
            ? textos.maquinas.reiniciarVentanaTitulo
            : textos.maquinas.reiniciarBarridoTitulo
        }
        confirmar={textos.maquinas.reiniciar}
        ocupado={reiniciar.isPending}
      >
        <p>
          {reiniciando === "ventana"
            ? textos.maquinas.reiniciarVentana
            : textos.maquinas.reiniciarBarrido}
        </p>
      </Confirmacion>
    </>
  );

  return {
    activar,
    pausar,
    tope,
    rotar,
    reiniciar,
    baja,
    consentir,
    pausadaPorHoy,
    pausarPorHoy: () =>
      pausar.mutate(
        pausadaPorHoy ? { hasta: haceUnMinuto(), pausar: false } : { hasta: finDelDia(), pausar: true },
      ),
    pedirBaja: () => setDandoDeBaja(true),
    pedirConsentimiento: () => setConsintiendo(true),
    pedirReinicio: (cual: "barrido" | "ventana") => setReiniciando(cual),
    dialogos,
  };
}

export type AccionesDeMaquina = ReturnType<typeof useAccionesDeMaquina>;

const CAJA =
  "z-50 min-w-56 rounded-xl border bg-popover p-1.5 text-popover-foreground shadow-lg outline-none";
const ITEM =
  "flex cursor-default items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm outline-none select-none data-[disabled]:opacity-50 data-[highlighted]:bg-muted";

/** El menú `⋯`: las acciones de la tarjeta, sin ocupar lugar hasta que se piden. */
export function MenuDeAcciones({
  maquina,
  acciones,
}: {
  maquina: Maquina;
  acciones: AccionesDeMaquina;
}) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`${textos.maquinas.acciones}: ${maquina.nombre}`}>
          <MoreHorizontal className="size-4" aria-hidden />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className={CAJA}>
          {maquina.activo && (
            <DropdownMenu.Item
              className={ITEM}
              disabled={acciones.pausar.isPending}
              onSelect={acciones.pausarPorHoy}
            >
              {acciones.pausadaPorHoy ? (
                <Play className="size-4 text-muted-foreground" aria-hidden />
              ) : (
                <Pause className="size-4 text-muted-foreground" aria-hidden />
              )}
              {acciones.pausadaPorHoy ? textos.maquina.reanudarHoy : textos.maquina.pausarPorHoy}
            </DropdownMenu.Item>
          )}
          <DropdownMenu.Item
            className={ITEM}
            disabled={acciones.activar.isPending}
            onSelect={() => acciones.activar.mutate(!maquina.activo)}
          >
            {maquina.activo ? (
              <PowerOff className="size-4 text-muted-foreground" aria-hidden />
            ) : (
              <Power className="size-4 text-muted-foreground" aria-hidden />
            )}
            {maquina.activo ? textos.maquina.desactivar : textos.maquina.activar}
          </DropdownMenu.Item>
          {maquina.activo && !maquina.puede_enviar && (
            <DropdownMenu.Item className={ITEM} onSelect={acciones.pedirConsentimiento}>
              <ShieldCheck className="size-4 text-muted-foreground" aria-hidden />
              {textos.maquina.registrarConsentimiento}
            </DropdownMenu.Item>
          )}
          <DropdownMenu.Item
            className={ITEM}
            disabled={acciones.rotar.isPending}
            onSelect={() => acciones.rotar.mutate()}
          >
            <KeyRound className="size-4 text-muted-foreground" aria-hidden />
            {textos.maquina.rotarToken}
          </DropdownMenu.Item>
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          <DropdownMenu.Item className={`${ITEM} text-critico`} onSelect={acciones.pedirBaja}>
            <Trash2 className="size-4" aria-hidden />
            {textos.maquina.darDeBaja}
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
