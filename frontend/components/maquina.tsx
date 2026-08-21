"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, KeyRound, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { bajaMaquina, editarMaquina, rotarToken, type Maquina } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Cómo se ve una máquina. Cuatro situaciones, distinguibles de un vistazo.
 *
 * El orden de las comprobaciones importa y es el orden en que le importan a
 * quien mira: primero si está frenada, después si está rota, después si está
 * viva.
 */
function situacion(maquina: Maquina) {
  if (!maquina.activo) {
    return { texto: textos.maquina.inactiva, variante: "outline" as const };
  }
  if (maquina.pausada) {
    return { texto: textos.maquina.pausada, variante: "secondary" as const };
  }
  if (!maquina.online) {
    return { texto: textos.maquina.offline, variante: "destructive" as const };
  }
  if (maquina.chequeos_fallando.length > 0) {
    return { texto: textos.maquina.degradada, variante: "secondary" as const };
  }
  return { texto: textos.maquina.online, variante: "default" as const };
}

function haceCuanto(iso: string | null): string {
  if (!iso) return textos.maquina.nunca;
  const segundos = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (segundos < 60) return "hace instantes";
  if (segundos < 3600) return `hace ${Math.floor(segundos / 60)} min`;
  if (segundos < 86_400) return `hace ${Math.floor(segundos / 3600)} h`;
  return `hace ${Math.floor(segundos / 86_400)} días`;
}

export function TarjetaMaquina({
  maquina,
  onToken,
}: {
  maquina: Maquina;
  onToken: (token: string, nombre: string) => void;
}) {
  const clienteQuery = useQueryClient();
  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ["estado"] });

  const activar = useMutation({
    mutationFn: (activo: boolean) => editarMaquina(maquina.maquina, { activo }),
    onSettled: refrescar,
  });

  const rotar = useMutation({
    mutationFn: () => rotarToken(maquina.maquina),
    onSuccess: (nuevo) => onToken(nuevo.token, nuevo.maquina),
    onSettled: refrescar,
  });

  const baja = useMutation({
    mutationFn: () => bajaMaquina(maquina.maquina),
    onSettled: refrescar,
  });

  const estado = situacion(maquina);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div className="min-w-0">
          <CardTitle className="truncate text-base">{maquina.nombre}</CardTitle>
          <p className="truncate font-mono text-xs text-muted-foreground">{maquina.maquina}</p>
        </div>
        <Badge variant={estado.variante}>{estado.texto}</Badge>
      </CardHeader>

      <CardContent className="space-y-3 text-sm">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <dt>{textos.maquina.ultimoLatido}</dt>
          <dd className="text-right tabular-nums">{haceCuanto(maquina.ultimo_latido)}</dd>
          <dt>{textos.maquina.version}</dt>
          <dd className="text-right font-mono">{maquina.version_agente ?? "—"}</dd>
        </dl>

        {/* ⚠️ Lo que separa esto del HTTP 502 mudo del MVP: el panel dice QUÉ
            chequeo falló, que es lo único con lo que alguien puede hacer algo. */}
        {maquina.chequeos_fallando.length > 0 && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2">
            <p className="text-xs font-semibold text-amber-700 dark:text-amber-400">
              {textos.maquina.fallando}
            </p>
            <ul className="mt-1 space-y-0.5">
              {maquina.chequeos_fallando.map((chequeo) => (
                <li key={chequeo} className="font-mono text-xs">
                  {chequeo}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Sin consentimiento el backend no le encola envíos (R6). Se avisa acá
            porque desde afuera se vería como una máquina que "no hace nada". */}
        {!maquina.puede_enviar && (
          <div className="flex items-start gap-2 rounded-md border border-border bg-muted/50 p-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
            <div>
              <p className="text-xs font-semibold">{textos.maquina.sinConsentimiento}</p>
              <p className="text-xs text-muted-foreground">
                {textos.maquina.sinConsentimientoDetalle}
              </p>
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          <Button
            variant={maquina.activo ? "outline" : "default"}
            size="sm"
            disabled={activar.isPending}
            onClick={() => activar.mutate(!maquina.activo)}
          >
            {maquina.activo ? textos.maquina.desactivar : textos.maquina.activar}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            disabled={rotar.isPending}
            onClick={() => rotar.mutate()}
          >
            <KeyRound className="size-4" aria-hidden />
            {textos.maquina.rotarToken}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            disabled={baja.isPending}
            onClick={() => {
              // La única confirmación de esta tarjeta. Dar de baja borra la
              // máquina y revoca su token: no se deshace con otro click.
              if (confirm(`¿Dar de baja ${maquina.maquina}? Se revoca su token.`)) {
                baja.mutate();
              }
            }}
          >
            <Trash2 className="size-4" aria-hidden />
            {textos.maquina.darDeBaja}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
