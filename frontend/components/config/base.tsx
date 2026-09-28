"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";

import { useAvisos } from "@/components/ui/avisos-flotantes";
import { Button } from "@/components/ui/button";
import { guardarConfiguracion, type Configuracion } from "@/lib/panel";
import { textos } from "@/lib/textos";
import { cn } from "@/lib/utils";

/**
 * Las piezas con las que se arma cada sección de la configuración (D56).
 *
 * El criterio: **cada ajuste es una fila igual a las demás** —nombre, una
 * línea de ayuda, el control a la derecha—, y el texto largo que explica el
 * porqué va plegado en "¿Qué hace esto?". Antes cada tarjeta tenía su propio
 * párrafo fijo de cinco líneas, y la página era un texto largo con controles
 * perdidos adentro.
 */

type Guardado = {
  cambios: Partial<Configuracion>;
  /** Los valores de antes, para ofrecer "Deshacer". */
  anterior?: Partial<Configuracion>;
  esDeshacer?: boolean;
  /** Otro texto en vez de "Guardado.", cuando el cambio merece decirse. */
  aviso?: string;
};

/**
 * Guarda un cambio (`PATCH /configuracion`, el mismo de siempre) y avisa.
 *
 * El aviso trae "Deshacer", que vuelve a mandar los valores de antes. **No se
 * ofrece** para lo que pide confirmación al prenderse —el envío automático, la
 * lista de destinos—: deshacer un "apagar" sería prenderlo sin pasar por el
 * diálogo. Esos llaman con `{ sinDeshacer: true }`.
 */
export function useGuardarConfiguracion() {
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();

  const mutacion = useMutation({
    mutationFn: ({ cambios }: Guardado) => guardarConfiguracion(cambios),
    onSuccess: (nueva, { anterior, esDeshacer, aviso }) => {
      clienteQuery.setQueryData(["configuracion"], nueva);
      void clienteQuery.invalidateQueries({ queryKey: ["estado"] });
      if (esDeshacer) {
        avisar(textos.config.deshecho);
      } else {
        avisar(
          aviso ?? textos.config.guardado,
          "ok",
          anterior
            ? {
                texto: textos.config.deshacer,
                alHacer: () => mutacion.mutate({ cambios: anterior, esDeshacer: true }),
              }
            : undefined,
        );
      }
    },
    onError: (error) => avisar(`${textos.config.falloGuardar} ${error.message}`, "critico"),
  });

  const guardar = (
    cambios: Partial<Configuracion>,
    opciones?: { sinDeshacer?: boolean; aviso?: string },
  ) => {
    const actual = clienteQuery.getQueryData<Configuracion>(["configuracion"]);
    const anterior =
      actual && !opciones?.sinDeshacer
        ? (Object.fromEntries(
            Object.keys(cambios).map((clave) => [clave, actual[clave as keyof Configuracion]]),
          ) as Partial<Configuracion>)
        : undefined;
    mutacion.mutate({ cambios, anterior, aviso: opciones?.aviso });
  };

  return {
    guardar,
    guardando: mutacion.isPending,
    error: mutacion.isError ? mutacion.error.message : undefined,
  };
}

/** Un grupo de ajustes con su título. */
export function Tarjeta({
  titulo,
  bajada,
  tono,
  children,
}: {
  titulo: string;
  bajada?: React.ReactNode;
  /** `peligro` para lo que puede hacer que algo le llegue a un cliente real. */
  tono?: "peligro";
  children: React.ReactNode;
}) {
  return (
    <section
      className={cn(
        "rounded-xl border bg-card sombra-suave",
        tono === "peligro" && "border-critico-borde",
      )}
    >
      <header className="border-b px-5 py-4">
        <h2 className="text-[15px] font-semibold">{titulo}</h2>
        {bajada && <p className="mt-0.5 text-sm text-muted-foreground">{bajada}</p>}
      </header>
      <div className="divide-y px-5">{children}</div>
    </section>
  );
}

/**
 * Una fila: qué es, para qué, y el control.
 *
 * `children` va debajo y a todo el ancho: para lo que no entra al costado (un
 * horario, una lista, un texto largo).
 */
export function Fila({
  titulo,
  ayuda,
  queHace,
  control,
  children,
}: {
  titulo: React.ReactNode;
  ayuda?: React.ReactNode;
  queHace?: React.ReactNode;
  control?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const [abierta, setAbierta] = useState(false);
  return (
    <div className="space-y-3 py-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-0.5">
          <p className="font-medium">{titulo}</p>
          {ayuda && <p className="text-sm text-muted-foreground">{ayuda}</p>}
          {queHace && (
            <>
              <button
                type="button"
                aria-expanded={abierta}
                onClick={() => setAbierta((a) => !a)}
                className="inline-flex items-center gap-0.5 pt-0.5 text-xs font-medium text-accion-tinta hover:underline"
              >
                <ChevronRight className={cn("size-3 transition-transform", abierta && "rotate-90")} aria-hidden />
                {textos.config.queHace}
              </button>
              {abierta && <div className="max-w-2xl space-y-2 pt-1 text-sm text-muted-foreground">{queHace}</div>}
            </>
          )}
        </div>
        {control && <div className="shrink-0 pt-0.5">{control}</div>}
      </div>
      {children}
    </div>
  );
}

/**
 * Un número que se guarda con su botón, que aparece sólo si cambió.
 *
 * No se guarda por tecla: "2" camino a "20" no es un valor que convenga
 * mandarle al servidor.
 */
export function Numero({
  valor,
  onGuardar,
  etiqueta,
  min = 1,
  max,
  sufijo,
  guardando = false,
}: {
  valor: number;
  onGuardar: (valor: number) => void;
  etiqueta: string;
  min?: number;
  max?: number;
  sufijo?: string;
  guardando?: boolean;
}) {
  const [borrador, setBorrador] = useState(String(valor));
  // Si el valor cambia desde afuera —guardado, "Deshacer"—, el campo lo sigue.
  useEffect(() => setBorrador(String(valor)), [valor]);
  const numero = Number(borrador);
  const valido =
    borrador.trim() !== "" &&
    Number.isInteger(numero) &&
    numero >= min &&
    (max === undefined || numero <= max);
  const cambiado = borrador !== String(valor);

  return (
    <div className="flex items-center gap-2">
      {cambiado && (
        <Button size="sm" disabled={!valido || guardando} onClick={() => onGuardar(numero)}>
          Guardar
        </Button>
      )}
      <input
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        aria-label={etiqueta}
        aria-invalid={!valido || undefined}
        className="h-8 w-20 rounded-lg border border-input bg-background px-2.5 text-right font-mono text-sm tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring aria-invalid:border-destructive"
        value={borrador}
        onChange={(evento) => setBorrador(evento.target.value)}
        onKeyDown={(evento) => {
          if (evento.key === "Enter" && valido && cambiado) onGuardar(numero);
        }}
      />
      {sufijo && <span className="text-sm text-muted-foreground">{sufijo}</span>}
    </div>
  );
}

const DIAS_CORTOS = ["", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

/** Los siete días, para marcar y desmarcar. ISO: 1 es lunes. */
export function DiasDeLaSemana({
  dias,
  onCambiar,
}: {
  dias: number[];
  onCambiar: (dias: number[]) => void;
}) {
  const alternar = (dia: number) =>
    onCambiar(dias.includes(dia) ? dias.filter((d) => d !== dia) : [...dias, dia].sort((a, b) => a - b));
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-lg border bg-muted p-1" role="group" aria-label="Días">
      {[1, 2, 3, 4, 5, 6, 7].map((dia) => (
        <button
          key={dia}
          type="button"
          aria-pressed={dias.includes(dia)}
          onClick={() => alternar(dia)}
          className={cn(
            "w-11 rounded-md py-1 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
            dias.includes(dia) ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {DIAS_CORTOS[dia]}
        </button>
      ))}
    </div>
  );
}

/** Un campo de hora HH:MM. */
export function CampoHora({
  valor,
  onCambiar,
  etiqueta,
  placeholder,
}: {
  valor: string;
  onCambiar: (valor: string) => void;
  etiqueta: string;
  placeholder?: string;
}) {
  return (
    <input
      className="h-8 w-20 rounded-lg border border-input bg-background px-2 text-center font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      value={valor}
      onChange={(evento) => onCambiar(evento.target.value)}
      placeholder={placeholder}
      aria-label={etiqueta}
    />
  );
}

export const HORA = /^([01]\d|2[0-3]):[0-5]\d$/;

/**
 * Los días de la ventana, en palabras.
 *
 * El backend los manda como números de ISO (1 es lunes). "1,2,3,4,5" no le dice
 * nada a nadie, y el caso normal —de lunes a viernes— merece decirse así y no
 * como una enumeración de cinco días.
 */
export function diasDeLaVentana(dias: number[]): string {
  const NOMBRES = ["", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
  const ordenados = [...dias].sort((a, b) => a - b);

  if (ordenados.length === 0) return "ningún día";
  if (ordenados.length === 7) return "todos los días";

  // Un rango corrido se dice como rango. Lunes a viernes es el caso de fábrica.
  const corrido = ordenados.every((dia, i) => i === 0 || dia === ordenados[i - 1] + 1);
  if (corrido && ordenados.length > 2) {
    return `de ${NOMBRES[ordenados[0]]} a ${NOMBRES[ordenados[ordenados.length - 1]]}`;
  }
  return ordenados.map((dia) => NOMBRES[dia]).join(", ");
}

/** El pase único (D38) es la condición de varios ajustes: el volumen, el envío automático. */
export const esPaseUnico = (config: Configuracion) => (config.modo_borrador ?? "playwright") !== "playwright";

/** "*" en la lista de destinos es "todos" (R4). */
export const TODOS = "*";
