"use client";

import { AlertTriangle } from "lucide-react";
import { useState } from "react";

import { Fila, Numero, Tarjeta, TODOS, useGuardarConfiguracion } from "@/components/config/base";
import { Button } from "@/components/ui/button";
import type { Configuracion } from "@/lib/panel";

/**
 * Seguridad: a quién se le puede escribir y cuánto, como máximo.
 */
export function SeccionSeguridad({ config }: { config: Configuracion }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  return (
    <>
      <DestinosPermitidos key={config.destinos_permitidos.join()} destinos={config.destinos_permitidos} />

      <Tarjeta titulo="Topes" bajada="Lo que protege la línea de cada vendedor, pase lo que pase.">
        <Fila
          titulo="Mensajes por máquina por día"
          ayuda="Es lo que protege la línea del vendedor."
          control={
            <Numero
              etiqueta="Mensajes por máquina por día"
              max={100}
              valor={config.tope_diario_maquina}
              guardando={guardando}
              onGuardar={(tope_diario_maquina) => guardar({ tope_diario_maquina })}
            />
          }
        />
        <Fila
          titulo="Mensajes por corrida, por máquina"
          ayuda="Protege de un error que encole de más."
          queHace="No es el volumen: el volumen lo decide el tope diario. Esto es la red por si algo encola más de lo que debería."
          control={
            <Numero
              etiqueta="Mensajes por corrida, por máquina"
              max={200}
              valor={config.tope_por_corrida}
              guardando={guardando}
              onGuardar={(tope_por_corrida) => guardar({ tope_por_corrida })}
            />
          }
        />
        <Fila
          titulo="Días sin repetirle a un contacto"
          ayuda="A quien ya recibió un mensaje no se le vuelve a escribir antes."
          control={
            <Numero
              etiqueta="Días sin repetirle a un contacto"
              max={90}
              sufijo="días"
              valor={config.dias_anti_duplicado}
              guardando={guardando}
              onGuardar={(dias_anti_duplicado) => guardar({ dias_anti_duplicado })}
            />
          }
        />
      </Tarjeta>
    </>
  );
}

/**
 * A quién puede escribirle el sistema (regla R4).
 *
 * Es el control más peligroso de todo el panel: abrirlo es lo que hace que una
 * corrida pueda alcanzar a un cliente real. **Por eso abrirlo sigue pidiendo
 * escribir `ABRIR`** —no un switch, no un click—: es lo único que el rediseño
 * de la configuración (D56) no simplificó a propósito. Y por eso tampoco se
 * ofrece "Deshacer": deshacer un cierre sería abrir sin escribir nada.
 */
function DestinosPermitidos({ destinos }: { destinos: string[] }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  const abierto = destinos.includes(TODOS);
  const [lista, setLista] = useState(destinos.filter((d) => d !== TODOS).join("\n"));
  const [confirmacion, setConfirmacion] = useState("");

  const numeros = () =>
    lista
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
  const guardarLista = (nuevos: string[]) => guardar({ destinos_permitidos: nuevos }, { sinDeshacer: true });

  return (
    <Tarjeta
      titulo="Destinos permitidos"
      tono={abierto ? "peligro" : undefined}
      bajada={
        <>
          El sistema sólo le escribe a estos números. Una lista vacía significa <strong>a nadie</strong>.
        </>
      }
    >
      {abierto ? (
        <div className="py-4">
          <div className="flex items-start gap-3 rounded-lg border border-critico-borde bg-critico-suave p-3">
            <AlertTriangle className="mt-0.5 size-5 shrink-0 text-critico" aria-hidden />
            <div className="space-y-2">
              <p className="font-semibold text-critico">Abierto a todos los contactos</p>
              <p className="text-sm text-muted-foreground">Cualquier chat que el sistema lea puede recibir un mensaje.</p>
              <Button variant="outline" size="sm" disabled={guardando} onClick={() => guardarLista(numeros())}>
                Volver a la lista acotada
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <>
          <Fila titulo="Números, uno por línea" ayuda={`${numeros().length} en la lista.`}>
            <textarea
              rows={4}
              aria-label="Números, uno por línea"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="+5491144405036"
              value={lista}
              onChange={(evento) => setLista(evento.target.value)}
            />
            <Button
              size="sm"
              disabled={guardando || numeros().join() === destinos.join()}
              onClick={() => guardarLista(numeros())}
            >
              Guardar lista
            </Button>
          </Fila>
          <Fila
            titulo="Abrir a todos los contactos"
            ayuda="A partir de ese momento el sistema puede escribirle a cualquier chat que lea."
          >
            <div className="space-y-2 rounded-lg border border-critico-borde p-3">
              <p className="text-sm">
                Para confirmar, escribí <code className="font-mono">ABRIR</code>.
              </p>
              <div className="flex gap-2">
                <input
                  className="h-8 w-32 rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={confirmacion}
                  onChange={(evento) => setConfirmacion(evento.target.value)}
                  aria-label="Escribí ABRIR para confirmar"
                />
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={confirmacion !== "ABRIR" || guardando}
                  onClick={() => {
                    guardarLista([TODOS]);
                    setConfirmacion("");
                  }}
                >
                  Abrir
                </Button>
              </div>
            </div>
          </Fila>
        </>
      )}
    </Tarjeta>
  );
}
