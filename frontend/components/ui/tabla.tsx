import { cn } from "@/lib/utils";

/**
 * La tabla del panel.
 *
 * **Siempre dentro de un contenedor que scrollea solo.** Es la regla que
 * importa: una tabla ancha sin esto hace scrollear la página entera de costado,
 * y en una Mac con trackpad eso se dispara sin querer y deja al operador
 * mirando una columna vacía sin entender qué pasó.
 *
 * Las cifras van tabulares por defecto desde `globals.css`: los números de una
 * columna tienen que alinearse para poder compararse de un vistazo.
 */
export function Tabla({
  children,
  etiqueta,
  className,
}: {
  children: React.ReactNode;
  /** Qué se está listando. Lo lee el lector de pantalla antes de la tabla. */
  etiqueta: string;
  className?: string;
}) {
  return (
    <div className={cn("overflow-x-auto rounded-lg border bg-card", className)}>
      <table className="w-full text-sm">
        <caption className="sr-only">{etiqueta}</caption>
        {children}
      </table>
    </div>
  );
}

export function Encabezado({ children }: { children: React.ReactNode }) {
  return (
    <thead className="border-b bg-muted/60">
      <tr>{children}</tr>
    </thead>
  );
}

export function Th({
  children,
  className,
  numerica,
}: {
  children?: React.ReactNode;
  className?: string;
  numerica?: boolean;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "px-4 py-2.5 text-left text-xs font-medium tracking-wide text-muted-foreground uppercase",
        numerica && "text-right",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Cuerpo({ children }: { children: React.ReactNode }) {
  return <tbody className="divide-y">{children}</tbody>;
}

export function Fila({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <tr className={cn("hover:bg-muted/40", className)}>{children}</tr>;
}

export function Td({
  children,
  className,
  numerica,
}: {
  children?: React.ReactNode;
  className?: string;
  numerica?: boolean;
}) {
  return (
    <td className={cn("px-4 py-2.5 align-top", numerica && "text-right", className)}>
      {children}
    </td>
  );
}

/**
 * Lo que se muestra cuando no hay filas.
 *
 * Una tabla vacía sin explicación se lee como una falla. Casi siempre no lo es
 * —todavía no pasó nada, o el filtro no encontró—, y decirlo es más barato que
 * el rato que alguien pierde averiguándolo.
 */
export function SinFilas({ columnas, children }: { columnas: number; children: React.ReactNode }) {
  return (
    <tr>
      <td colSpan={columnas} className="px-4 py-10 text-center text-sm text-muted-foreground">
        {children}
      </td>
    </tr>
  );
}
