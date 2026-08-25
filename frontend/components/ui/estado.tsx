import { AlertTriangle, Ban, Check, Info } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * ⚠️ Los íconos de acá son a propósito los que el CI ya compiló alguna vez.
 *
 * `lucide-react` renombra íconos entre versiones y deja alias que después
 * saca: un import que no existe es un error de tipos que sólo aparece al
 * compilar. Como el panel no se puede compilar en la máquina donde se escribió
 * esto, se usa el vocabulario ya verificado en vez de estrenar nombres.
 *
 * El tipo también va escrito a mano por lo mismo: `LucideIcon` existe, pero no
 * hace falta atarse a él para cuatro íconos.
 */
type Icono = React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;

/**
 * Los estados de la interfaz, en un solo lugar.
 *
 * **Por qué existe este archivo.** Antes cada componente decidía por su cuenta
 * cómo se veía un aviso: había 41 usos sueltos de `amber-500/40`,
 * `border-destructive/40`, `bg-amber-500/10`, `text-amber-800 dark:text-amber-300`
 * repartidos por seis componentes, cada uno con su propia intensidad. Dos
 * pantallas nunca se veían igual porque nada las obligaba.
 *
 * Ahora hay tres niveles y salen de los tokens de `globals.css`. Ningún
 * componente vuelve a escribir un color.
 *
 * **Y el color nunca va solo.** Cada nivel lleva su ícono y su fondo teñido,
 * por dos motivos: uno de cada doce varones no distingue rojo de verde, y —más
 * concreto acá— la paleta de Centonara es cálida, así que el ámbar y el rojo
 * tienen que apoyarse en algo más que el tono para que se lean como lo que son.
 */
export type Nivel = "ok" | "atencion" | "critico" | "neutro";

const ICONOS: Record<Nivel, Icono> = {
  ok: Check,
  atencion: AlertTriangle,
  critico: Ban,
  neutro: Info,
};

const PILDORA: Record<Nivel, string> = {
  ok: "border-ok-borde bg-ok-suave text-ok",
  atencion: "border-atencion-borde bg-atencion-suave text-atencion",
  critico: "border-critico-borde bg-critico-suave text-critico",
  neutro: "border-border bg-muted text-muted-foreground",
};

const PANEL: Record<Nivel, string> = {
  ok: "border-ok-borde bg-ok-suave",
  atencion: "border-atencion-borde bg-atencion-suave",
  critico: "border-critico-borde bg-critico-suave",
  neutro: "border-border bg-muted/50",
};

const TINTA: Record<Nivel, string> = {
  ok: "text-ok",
  atencion: "text-atencion",
  critico: "text-critico",
  neutro: "text-muted-foreground",
};

/**
 * Una píldora de estado: "Conectada", "Degradada", "Sin conexión".
 *
 * Se usa donde antes iba un `<Badge>` gris. La diferencia es que un badge
 * `secondary` y uno `outline` se ven casi igual, y "degradada" y "pausada" son
 * cosas distintas que pedían distinguirse de un vistazo.
 */
export function Pildora({
  nivel,
  children,
  conIcono = true,
  className,
}: {
  nivel: Nivel;
  children: React.ReactNode;
  conIcono?: boolean;
  className?: string;
}) {
  const Icono = ICONOS[nivel];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        PILDORA[nivel],
        className,
      )}
    >
      {conIcono && <Icono className="size-3.5 shrink-0" aria-hidden />}
      {children}
    </span>
  );
}

/**
 * Un bloque de aviso, con su ícono y su acción.
 *
 * `role` se elige por nivel y no se pasa desde afuera: `alert` interrumpe al
 * lector de pantalla y `status` no. Un aviso crítico tiene que interrumpir; uno
 * informativo que interrumpe enseña a ignorar al lector.
 */
export function Aviso({
  nivel,
  titulo,
  children,
  accion,
  className,
}: {
  nivel: Nivel;
  titulo: React.ReactNode;
  children?: React.ReactNode;
  /** Qué hacer. Una alerta sin acción es una queja. */
  accion?: React.ReactNode;
  className?: string;
}) {
  const Icono = ICONOS[nivel];
  return (
    <div
      role={nivel === "critico" ? "alert" : "status"}
      className={cn("flex items-start gap-3 rounded-lg border p-4", PANEL[nivel], className)}
    >
      <Icono className={cn("mt-0.5 size-5 shrink-0", TINTA[nivel])} aria-hidden />
      <div className="min-w-0 space-y-1">
        <p className={cn("font-medium", TINTA[nivel])}>{titulo}</p>
        {children && <div className="text-sm">{children}</div>}
        {accion && <div className="text-sm text-muted-foreground">{accion}</div>}
      </div>
    </div>
  );
}

/** Sólo la tinta de un nivel, para cuando hace falta teñir un número o un ícono suelto. */
export const tintaDe = (nivel: Nivel) => TINTA[nivel];
