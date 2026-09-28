"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Fila, Tarjeta, useGuardarConfiguracion } from "@/components/config/base";
import { Button } from "@/components/ui/button";
import { Campo } from "@/components/ui/campo";
import { Interruptor } from "@/components/ui/interruptor";
import { empezarDeCero, type Configuracion } from "@/lib/panel";

/**
 * Sistema: la versión del agente y, al final y aparte, empezar de cero.
 */
export function SeccionSistema({ config }: { config: Configuracion }) {
  return (
    <>
      <Tarjeta titulo="Versión del agente">
        <VersionDelAgente key={config.version_agente_esperada ?? ""} valor={config.version_agente_esperada ?? ""} />
      </Tarjeta>
      {/* Última de la pantalla, y a propósito: es la que borra. */}
      <EmpezarDeCero />
    </>
  );
}

/**
 * El commit al que convergen las máquinas (D45).
 *
 * Se guarda al confirmar y no por tecla: un sha a medio escribir no es un sha,
 * y el backend lo rechaza — con razón, porque todas las máquinas se lo
 * pedirían a GitHub y fallarían juntas.
 */
function VersionDelAgente({ valor }: { valor: string }) {
  const { guardar, guardando, error } = useGuardarConfiguracion();
  const [borrador, setBorrador] = useState(valor);
  const limpio = borrador.trim().toLowerCase();
  const parece = limpio === "" || /^[0-9a-f]{7,40}$/.test(limpio);

  return (
    <Fila
      titulo="Commit fijado"
      ayuda={
        <>
          Hoy: <span className="font-mono">{valor ? valor.slice(0, 7) : "lo último publicado"}</span>. Cada máquina
          muestra en su detalle qué commit corre y si está al día.
        </>
      }
      queHace="Las computadoras de los vendedores se actualizan solas, al iniciar sesión y cada hora, a la versión que se fije acá. Vacío es «lo último que se publicó». Con un commit, todas van a ése: es la forma de volver atrás sin tocar ninguna computadora."
    >
      <div className="flex flex-wrap items-end gap-2">
        <Campo
          etiqueta="Commit"
          ayuda="Vacío: lo último publicado. Si no, el sha del commit (7 a 40 dígitos)."
          placeholder="ej. 7912e13"
          value={borrador}
          spellCheck={false}
          className="w-64 font-mono"
          onChange={(evento) => setBorrador(evento.target.value)}
          error={!parece ? "Eso no es un sha de git." : error}
        />
        <Button size="sm" disabled={guardando || !parece || limpio === valor} onClick={() => guardar({ version_agente_esperada: limpio })}>
          Fijar versión
        </Button>
        {valor && (
          <Button size="sm" variant="outline" disabled={guardando} onClick={() => guardar({ version_agente_esperada: "" })}>
            Volver a lo último
          </Button>
        )}
      </div>
    </Fila>
  );
}

/**
 * Vaciar el sistema para entregárselo a alguien (D28).
 *
 * Lo peligroso no es perder las corridas de prueba: es entregar el sistema con
 * los destinos permitidos de otra persona cargados. Por eso restablecer la
 * configuración viene marcado, y por eso hay que escribir la palabra — igual
 * que antes del rediseño: borrar no se deshace.
 */
function EmpezarDeCero() {
  const clienteQuery = useQueryClient();
  const [confirmacion, setConfirmacion] = useState("");
  const [restablecer, setRestablecer] = useState(true);
  const [borrarMaquinas, setBorrarMaquinas] = useState(false);
  const [hecho, setHecho] = useState<string | null>(null);

  const borrar = useMutation({
    mutationFn: () =>
      empezarDeCero({
        confirmacion,
        restablecer_configuracion: restablecer,
        borrar_maquinas: borrarMaquinas,
      }),
    onSuccess: (resultado) => {
      const total = Object.values(resultado.borrados).reduce((a, b) => a + b, 0);
      setHecho(`Listo: se borraron ${total} registros. El sistema quedó como recién instalado.`);
      setConfirmacion("");
      void clienteQuery.invalidateQueries();
    },
  });

  return (
    <Tarjeta titulo="Empezar de cero" bajada="Para entregar el sistema sin los datos de las pruebas." tono="peligro">
      <div className="grid gap-3 py-4 text-sm sm:grid-cols-2">
        <div>
          <p className="font-medium">Se borra</p>
          <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            <li>Las corridas y sus borradores</li>
            <li>Los mensajes enviados y descartados</li>
            <li>Los números que el sistema había averiguado</li>
            <li>El avance del barrido de cada máquina</li>
          </ul>
        </div>
        <div>
          <p className="font-medium">No se borra</p>
          <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            <li>El historial de auditoría: no se puede borrar ni desde acá ni desde la base</li>
            <li>Las máquinas instaladas, salvo que lo pidas abajo</li>
            <li>Nada de WhatsApp: los chats del vendedor no se tocan nunca</li>
          </ul>
        </div>
      </div>

      <Fila
        titulo="Volver la configuración a cero"
        ayuda="Deja la lista de destinos vacía —que significa a nadie— y borra la información de la empresa."
        queHace="Es lo que corresponde al entregar: si no, el cliente hereda los números con los que probaste."
        control={<Interruptor prendido={restablecer} etiqueta="Volver la configuración a cero" onCambiar={setRestablecer} />}
      />
      <Fila
        titulo="Dar de baja las máquinas"
        ayuda="Revoca sus tokens: hay que volver a instalarlas una por una."
        queHace="Sólo si las computadoras de prueba no son las del cliente."
        control={<Interruptor prendido={borrarMaquinas} etiqueta="Dar de baja las máquinas" peligroso onCambiar={setBorrarMaquinas} />}
      />

      <div className="py-4">
        <div className="space-y-2 rounded-lg border border-critico-borde p-3">
          <p className="text-sm">
            Esto no se puede deshacer. Para confirmar, escribí <code className="font-mono">BORRAR</code>.
          </p>
          <div className="flex gap-2">
            <input
              className="h-8 w-32 rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={confirmacion}
              onChange={(evento) => setConfirmacion(evento.target.value)}
              aria-label="Escribí BORRAR para confirmar"
            />
            <Button
              variant="destructive"
              size="sm"
              disabled={confirmacion.trim().toUpperCase() !== "BORRAR" || borrar.isPending}
              onClick={() => borrar.mutate()}
            >
              {borrar.isPending ? "Borrando…" : "Empezar de cero"}
            </Button>
          </div>
          {hecho && <p className="text-sm text-muted-foreground">{hecho}</p>}
          {borrar.error && <p className="text-sm text-destructive">{borrar.error.message}</p>}
        </div>
      </div>
    </Tarjeta>
  );
}
