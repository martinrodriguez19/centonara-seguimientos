"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * El diálogo del panel, y con él se van los `confirm()` del navegador.
 *
 * **Por qué existe.** Había cuatro `confirm()` nativos —uno de ellos en el kill
 * switch, el control más crítico de todo el panel—. En una Mac eso se ve como
 * una hoja gris del sistema, fuera de todo el diseño, con botones que dicen
 * "Aceptar" y "Cancelar" en vez de decir qué va a pasar. Y no se puede poner
 * fricción adentro: un `confirm()` se acepta con Enter sin leer nada.
 *
 * **Escrito a mano y no traído de una librería** a propósito. Agregar una
 * dependencia obliga a regenerar el lockfile, y el CI instala con
 * `--frozen-lockfile`: un `package.json` que no coincide con el lockfile deja
 * el panel sin compilar. Esto necesita un portal y tres teclas.
 *
 * Lo que sí hace, porque si no un diálogo es peor que nada:
 *
 * - **Escape cierra**, salvo mientras una acción está en curso.
 * - **El foco entra** al diálogo y **vuelve** al elemento que lo abrió.
 * - **Tab queda adentro**: sin esto se puede tabular hasta la página de atrás y
 *   apretar cosas que no se ven.
 * - **El fondo no scrollea** mientras está abierto.
 * - `aria-modal` y `aria-labelledby`, para que un lector de pantalla anuncie de
 *   qué se trata en vez de leer la página entera.
 */
export function Dialogo({
  abierto,
  onCerrar,
  titulo,
  children,
  pie,
  /** Con una acción en curso no se puede cerrar: cerrar no la cancelaría. */
  ocupado = false,
}: {
  abierto: boolean;
  onCerrar: () => void;
  titulo: string;
  children?: React.ReactNode;
  pie?: React.ReactNode;
  ocupado?: boolean;
}) {
  const caja = useRef<HTMLDivElement>(null);
  const idTitulo = useId();
  // El portal necesita `document`, que en el servidor no existe.
  const [montado, setMontado] = useState(false);

  useEffect(() => setMontado(true), []);

  useEffect(() => {
    if (!abierto) return;

    const antes = document.activeElement as HTMLElement | null;
    const scrollDeAntes = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Al primer elemento enfocable del diálogo, o al diálogo mismo.
    const enfocables = () =>
      Array.from(
        caja.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
    enfocables()[0]?.focus() ?? caja.current?.focus();

    const alTeclear = (evento: KeyboardEvent) => {
      if (evento.key === "Escape" && !ocupado) {
        evento.preventDefault();
        onCerrar();
        return;
      }
      if (evento.key !== "Tab") return;

      const lista = enfocables();
      if (lista.length === 0) return;
      const primero = lista[0];
      const ultimo = lista[lista.length - 1];

      if (evento.shiftKey && document.activeElement === primero) {
        evento.preventDefault();
        ultimo.focus();
      } else if (!evento.shiftKey && document.activeElement === ultimo) {
        evento.preventDefault();
        primero.focus();
      }
    };

    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("keydown", alTeclear);
      document.body.style.overflow = scrollDeAntes;
      antes?.focus();
    };
  }, [abierto, ocupado, onCerrar]);

  if (!abierto || !montado) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      {/* El fondo. Cerrar tocando afuera sólo si no hay nada en curso: si la
          acción está corriendo, cerrar no la cancela y da la impresión de que
          sí. */}
      <div
        className="absolute inset-0 bg-foreground/40 backdrop-blur-[2px]"
        onClick={() => !ocupado && onCerrar()}
        aria-hidden
      />
      <div
        ref={caja}
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        tabIndex={-1}
        className="relative w-full max-w-md rounded-lg border bg-card p-5 shadow-lg outline-none"
      >
        <h2 id={idTitulo} className="text-base font-semibold">
          {titulo}
        </h2>
        {children && <div className="mt-2 space-y-2 text-sm">{children}</div>}
        {pie && <div className="mt-4 flex flex-wrap gap-2">{pie}</div>}
      </div>
    </div>,
    document.body,
  );
}

/**
 * Un diálogo de confirmación, con la fricción que corresponda.
 *
 * **La fricción es proporcional al daño, y esa es la única regla.** Ya estaba
 * en el panel de antes y acá queda escrita en un solo lugar:
 *
 * - Lo que se deshace —frenar el sistema, vetar un borrador— confirma y listo.
 *   Ponerle más fricción sólo logra que alguien no lo use, y frenar de más no
 *   le hace daño a nadie.
 * - Lo que **le llega a una persona de afuera** —enviar de verdad, liberar
 *   veinte retenidos de una— pide `escribir`: hay que tipear el número de cosas
 *   que van a pasar. Escribir el número obliga a leerlo, que es todo lo que
 *   hace falta, y es exactamente la acción que alguien apurado haría sin mirar.
 */
export function Confirmacion({
  abierto,
  onCerrar,
  onConfirmar,
  titulo,
  children,
  confirmar,
  /** Si viene, hay que escribir este número para habilitar el botón. */
  escribir,
  peligrosa = false,
  ocupado = false,
}: {
  abierto: boolean;
  onCerrar: () => void;
  onConfirmar: () => void;
  titulo: string;
  children?: React.ReactNode;
  confirmar: string;
  escribir?: number;
  peligrosa?: boolean;
  ocupado?: boolean;
}) {
  const [texto, setTexto] = useState("");
  const idCampo = useId();

  // Que el campo no arrastre lo escrito de la vez anterior: si quedó "3" de un
  // envío previo y ahora son 3 otra vez, el botón aparecería ya habilitado y la
  // fricción no habría ocurrido.
  useEffect(() => {
    if (abierto) setTexto("");
  }, [abierto]);

  const habilitado = escribir === undefined || texto.trim() === String(escribir);

  return (
    <Dialogo
      abierto={abierto}
      onCerrar={onCerrar}
      titulo={titulo}
      ocupado={ocupado}
      pie={
        <>
          <Button
            variant={peligrosa ? "destructive" : "default"}
            disabled={!habilitado || ocupado}
            onClick={onConfirmar}
          >
            {confirmar}
          </Button>
          <Button variant="ghost" disabled={ocupado} onClick={onCerrar}>
            Cancelar
          </Button>
        </>
      }
    >
      {children}
      {escribir !== undefined && (
        <label className="block space-y-1 pt-1" htmlFor={idCampo}>
          <span className="text-sm font-medium">Escribí {escribir} para confirmar</span>
          <input
            id={idCampo}
            inputMode="numeric"
            autoComplete="off"
            className={cn(
              "w-24 rounded-md border border-input bg-background px-3 py-1.5 text-sm tabular-nums",
              "outline-none focus-visible:ring-2 focus-visible:ring-ring",
            )}
            value={texto}
            onChange={(evento) => setTexto(evento.target.value)}
          />
        </label>
      )}
    </Dialogo>
  );
}
