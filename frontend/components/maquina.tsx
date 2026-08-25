"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Trash2 } from "lucide-react";
import { useState } from "react";

import { useAvisos } from "@/components/ui/avisos-flotantes";
import { Button } from "@/components/ui/button";
import { CampoNumero } from "@/components/ui/campo";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Confirmacion, Dialogo } from "@/components/ui/dialogo";
import { Aviso, Pildora, type Nivel } from "@/components/ui/estado";
import { bajaMaquina, editarMaquina, rotarToken, type Maquina } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Cómo se ve una máquina. Cinco situaciones, distinguibles de un vistazo.
 *
 * El orden de las comprobaciones importa y es el orden en que le importan a
 * quien mira: primero si está frenada, después si está rota, después si está
 * viva.
 *
 * Antes cada situación era un `<Badge>` con una variante distinta, y el
 * problema es que todas las variantes eran del mismo gris: "pausada" y
 * "degradada" —que son cosas muy distintas— se veían igual. Ahora cada una
 * tiene su nivel, y el nivel decide color e ícono.
 */
function situacion(maquina: Maquina): { texto: string; nivel: Nivel } {
  if (!maquina.activo) {
    return { texto: textos.maquina.inactiva, nivel: "neutro" };
  }
  if (maquina.pausada) {
    return { texto: textos.maquina.pausada, nivel: "neutro" };
  }
  if (!maquina.online) {
    return { texto: textos.maquina.offline, nivel: "critico" };
  }
  if (maquina.chequeos_fallando.length > 0) {
    return { texto: textos.maquina.degradada, nivel: "atencion" };
  }
  return { texto: textos.maquina.online, nivel: "ok" };
}

function haceCuanto(iso: string | null): string {
  if (!iso) return textos.maquina.nunca;
  const segundos = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (segundos < 60) return "hace instantes";
  if (segundos < 3600) return `hace ${Math.floor(segundos / 60)} min`;
  if (segundos < 86_400) return `hace ${Math.floor(segundos / 3600)} h`;
  return `hace ${Math.floor(segundos / 86_400)} días`;
}

/** Fin del día de hoy, en la hora de la computadora de quien mira. */
function finDelDia(): string {
  const hasta = new Date();
  hasta.setHours(23, 59, 59, 999);
  return hasta.toISOString();
}

export function TarjetaMaquina({
  maquina,
  onToken,
}: {
  maquina: Maquina;
  onToken: (token: string, nombre: string) => void;
}) {
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();
  const [dandoDeBaja, setDandoDeBaja] = useState(false);
  const [consintiendo, setConsintiendo] = useState(false);
  const [viendoChequeos, setViendoChequeos] = useState(false);

  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ["estado"] });

  const activar = useMutation({
    mutationFn: (activo: boolean) => editarMaquina(maquina.maquina, { activo }),
    onSuccess: (_, activo) =>
      avisar(activo ? textos.maquina.avisoActivada : textos.maquina.avisoDesactivada),
    onError: () => avisar(textos.maquina.avisoFallo, "critico"),
    onSettled: refrescar,
  });

  // "Pausar por hoy" es de otra persona que activar: activar lo decide el
  // dueño, pausar lo decide el vendedor sobre su propia máquina. Mientras la
  // Mac no tenga su ícono en la barra de menú (fase 5), el panel es el único
  // lugar donde se puede hacer — y el instructivo de instalación ya dice que se
  // hace desde acá.
  const pausar = useMutation({
    mutationFn: (hasta: string | null) =>
      editarMaquina(maquina.maquina, { pausado_hasta: hasta }),
    onSuccess: (_, hasta) =>
      avisar(hasta ? textos.maquina.avisoPausada : textos.maquina.avisoDespausada),
    onError: () => avisar(textos.maquina.avisoFallo, "critico"),
    onSettled: refrescar,
  });

  const tope = useMutation({
    mutationFn: (tope_diario: number) => editarMaquina(maquina.maquina, { tope_diario }),
    onSuccess: () => avisar(textos.maquina.avisoTope),
    onError: () => avisar(textos.maquina.avisoFallo, "critico"),
    onSettled: refrescar,
  });

  const rotar = useMutation({
    mutationFn: () => rotarToken(maquina.maquina),
    onSuccess: (nuevo) => onToken(nuevo.token, nuevo.maquina),
    onError: () => avisar(textos.maquina.avisoFallo, "critico"),
    onSettled: refrescar,
  });

  const baja = useMutation({
    mutationFn: () => bajaMaquina(maquina.maquina),
    onSuccess: () => {
      setDandoDeBaja(false);
      avisar(textos.maquina.avisoBaja(maquina.nombre));
    },
    onError: () => avisar(textos.maquina.avisoFallo, "critico"),
    onSettled: refrescar,
  });

  const consentir = useMutation({
    mutationFn: () => editarMaquina(maquina.maquina, { acepto_condiciones: true }),
    onSuccess: () => {
      setConsintiendo(false);
      avisar(textos.maquina.avisoConsentimiento);
    },
    onError: () => avisar(textos.maquina.avisoFallo, "critico"),
    onSettled: refrescar,
  });

  const estado = situacion(maquina);
  // Sólo tiene sentido pausar por hoy una máquina que si no estaría trabajando.
  const pausadaPorHoy = maquina.activo && maquina.pausada;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div className="min-w-0">
          <CardTitle className="truncate text-base">{maquina.nombre}</CardTitle>
          <p className="truncate font-mono text-xs text-muted-foreground">{maquina.maquina}</p>
        </div>
        <Pildora nivel={estado.nivel}>{estado.texto}</Pildora>
      </CardHeader>

      <CardContent className="space-y-3 text-sm">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <dt>{textos.maquina.ultimoLatido}</dt>
          <dd className="text-right tabular-nums">{haceCuanto(maquina.ultimo_latido)}</dd>
          <dt>{textos.maquina.version}</dt>
          <dd className="text-right font-mono">{maquina.version_agente ?? "—"}</dd>
        </dl>

        {/* ⚠️ Lo que separa esto del HTTP 502 mudo del MVP: el panel dice QUÉ
            chequeo falló, en castellano y con qué hacer. Antes decía
            `claude_bin` y ahí terminaba. */}
        {maquina.chequeos_fallando.length > 0 && (
          <Aviso
            nivel="atencion"
            titulo={textos.maquina.fallando}
            className="p-3"
            accion={
              <Button variant="outline" size="sm" onClick={() => setViendoChequeos(true)}>
                {textos.maquina.verChequeos}
              </Button>
            }
          >
            <ul className="space-y-1">
              {maquina.chequeos_fallando.map((clave) => (
                <li key={clave}>{textos.chequeos[clave]?.nombre ?? clave}</li>
              ))}
            </ul>
          </Aviso>
        )}

        {/* Sin consentimiento el backend no le encola envíos. Se avisa acá
            porque desde afuera se vería como una máquina que "no hace nada". */}
        {!maquina.puede_enviar && (
          <Aviso
            nivel="neutro"
            titulo={textos.maquina.sinConsentimiento}
            className="p-3"
            accion={
              <Button variant="outline" size="sm" onClick={() => setConsintiendo(true)}>
                {textos.maquina.registrarConsentimiento}
              </Button>
            }
          >
            {textos.maquina.sinConsentimientoDetalle}
          </Aviso>
        )}

        {/* Lo que protege la línea de ESTE vendedor. Antes sólo se podía tocar
            el tope global, y las líneas no son todas iguales: una que recién se
            da de alta aguanta menos que una que viene andando hace meses. */}
        <CampoNumero
          etiqueta={textos.maquina.topeDiario}
          ayuda={textos.maquina.topeDiarioAyuda}
          valor={maquina.tope_diario}
          min={1}
          max={100}
          guardando={tope.isPending}
          onGuardar={(valor) => tope.mutate(valor)}
          className="w-28"
        />

        <div className="flex flex-wrap gap-2 pt-1">
          <Button
            variant={maquina.activo ? "outline" : "default"}
            size="sm"
            disabled={activar.isPending}
            onClick={() => activar.mutate(!maquina.activo)}
          >
            {maquina.activo ? textos.maquina.desactivar : textos.maquina.activar}
          </Button>

          {maquina.activo && (
            <Button
              variant="outline"
              size="sm"
              disabled={pausar.isPending}
              onClick={() => pausar.mutate(pausadaPorHoy ? null : finDelDia())}
            >
              {pausadaPorHoy ? textos.maquina.reanudarHoy : textos.maquina.pausarPorHoy}
            </Button>
          )}

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
            onClick={() => setDandoDeBaja(true)}
          >
            <Trash2 className="size-4" aria-hidden />
            {textos.maquina.darDeBaja}
          </Button>
        </div>
      </CardContent>

      {/* Los diez chequeos, no sólo los que fallan. Ver ocho en verde y dos en
          "no aplica" es información: dice que la máquina está bien, no
          solamente que no está mal. */}
      <Dialogo
        abierto={viendoChequeos}
        onCerrar={() => setViendoChequeos(false)}
        titulo={`${textos.maquina.chequeosDe} ${maquina.nombre}`}
        pie={
          <Button variant="outline" onClick={() => setViendoChequeos(false)}>
            Cerrar
          </Button>
        }
      >
        <ul className="space-y-3">
          {Object.entries(maquina.diagnostico).map(([clave, resultado]) => {
            const texto = textos.chequeos[clave];
            const nivel: Nivel =
              resultado === "ok" ? "ok" : resultado === "falla" ? "atencion" : "neutro";
            return (
              <li key={clave} className="space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{texto?.nombre ?? clave}</span>
                  <Pildora nivel={nivel}>
                    {resultado === "ok"
                      ? textos.maquina.chequeoOk
                      : resultado === "falla"
                        ? textos.maquina.chequeoFalla
                        : textos.maquina.chequeoNoAplica}
                  </Pildora>
                </div>
                {resultado === "falla" && texto && (
                  <p className="text-xs text-muted-foreground">
                    {texto.detalle} <span className="text-foreground">{texto.queHacer}</span>
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      </Dialogo>

      {/* Dar de baja borra la máquina y revoca su token: no se deshace con otro
          click, así que confirma. No pide escribir el nombre porque no le llega
          a nadie de afuera — la fricción de escribir está reservada para eso. */}
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

      {/* Registrarlo es afirmar que la conversación con el vendedor ya pasó, no
          destrabar un aviso molesto: por eso confirma y queda en la auditoría
          con fecha. */}
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
    </Card>
  );
}
