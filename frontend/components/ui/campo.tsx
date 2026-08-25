"use client";

import { useId } from "react";

import { cn } from "@/lib/utils";

/**
 * Los campos de formulario del panel.
 *
 * **Por qué existe.** El mismo `<input>` con las mismas ocho clases estaba
 * copiado a mano en el alta de máquina, en el login, en la configuración y en
 * dos confirmaciones. Cinco copias que ya habían empezado a separarse: unas
 * tenían texto de ayuda, otras no; ninguna tenía estado de error; ninguna
 * ataba la etiqueta al campo con `id`, así que tocar la etiqueta no enfocaba
 * nada y el lector de pantalla no sabía qué estaba leyendo.
 *
 * La etiqueta es obligatoria, no opcional: un campo sin etiqueta es un campo
 * que alguien va a completar adivinando.
 */

const CLASES_BASE = cn(
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
  "outline-none transition-shadow",
  "focus-visible:ring-2 focus-visible:ring-ring",
  "disabled:cursor-not-allowed disabled:opacity-60",
  // Estado de error visible **y** anunciado. `aria-invalid` lo pone quien usa
  // el componente; el color sale de acá para que se vea igual en todos lados.
  "aria-[invalid=true]:border-critico-borde aria-[invalid=true]:ring-1 aria-[invalid=true]:ring-critico-borde",
);

type Comun = {
  etiqueta: string;
  ayuda?: string;
  /** El problema concreto, dicho para quien completa el formulario. */
  error?: string | null;
  className?: string;
};

function Envoltura({
  etiqueta,
  ayuda,
  error,
  idCampo,
  idAyuda,
  children,
}: Comun & { idCampo: string; idAyuda: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={idCampo} className="block text-sm font-medium">
        {etiqueta}
      </label>
      {children}
      {ayuda && !error && (
        <p id={idAyuda} className="text-xs text-muted-foreground">
          {ayuda}
        </p>
      )}
      {error && (
        <p id={idAyuda} className="text-xs text-critico">
          {error}
        </p>
      )}
    </div>
  );
}

export function Campo({
  etiqueta,
  ayuda,
  error,
  className,
  ...resto
}: Comun & React.InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  const idAyuda = `${id}-ayuda`;
  return (
    <Envoltura etiqueta={etiqueta} ayuda={ayuda} error={error} idCampo={id} idAyuda={idAyuda}>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={ayuda || error ? idAyuda : undefined}
        className={cn(CLASES_BASE, className)}
        {...resto}
      />
    </Envoltura>
  );
}

export function AreaDeTexto({
  etiqueta,
  ayuda,
  error,
  className,
  ...resto
}: Comun & React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  const idAyuda = `${id}-ayuda`;
  return (
    <Envoltura etiqueta={etiqueta} ayuda={ayuda} error={error} idCampo={id} idAyuda={idAyuda}>
      <textarea
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={ayuda || error ? idAyuda : undefined}
        className={cn(CLASES_BASE, "resize-y", className)}
        {...resto}
      />
    </Envoltura>
  );
}

/**
 * Un número que se guarda al confirmar, no mientras se escribe.
 *
 * Guardar en cada tecla contra un backend que valida rangos hace que borrar un
 * dígito para escribir otro mande un valor intermedio inválido: querer pasar el
 * tope de 20 a 5 pasa por el 2, y si el mínimo fuera mayor, por un rechazo.
 *
 * Así que el valor vive acá mientras se edita y sale sólo con Enter o al salir
 * del campo. Es el mismo criterio que ya tenía la pantalla de configuración,
 * ahora en un solo lugar.
 */
export function CampoNumero({
  etiqueta,
  ayuda,
  error,
  valor,
  onGuardar,
  min,
  max,
  guardando = false,
  className,
}: Comun & {
  valor: number;
  onGuardar: (valor: number) => void;
  min?: number;
  max?: number;
  guardando?: boolean;
}) {
  const id = useId();
  const idAyuda = `${id}-ayuda`;

  const confirmar = (crudo: string) => {
    const numero = Number(crudo);
    if (!Number.isFinite(numero) || numero === valor) return;
    if (min !== undefined && numero < min) return;
    if (max !== undefined && numero > max) return;
    onGuardar(numero);
  };

  return (
    <Envoltura etiqueta={etiqueta} ayuda={ayuda} error={error} idCampo={id} idAyuda={idAyuda}>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        defaultValue={valor}
        min={min}
        max={max}
        disabled={guardando}
        aria-invalid={error ? true : undefined}
        aria-describedby={ayuda || error ? idAyuda : undefined}
        className={cn(CLASES_BASE, "tabular-nums", className)}
        onBlur={(evento) => confirmar(evento.target.value)}
        onKeyDown={(evento) => {
          if (evento.key === "Enter") {
            evento.preventDefault();
            confirmar((evento.target as HTMLInputElement).value);
          }
        }}
      />
    </Envoltura>
  );
}
