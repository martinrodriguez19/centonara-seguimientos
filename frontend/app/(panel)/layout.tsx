import { Barra } from "@/components/navegacion/barra";

/**
 * El marco de todas las pantallas con sesión (D54).
 *
 * Es un *route group*: el `(panel)` no aparece en la URL, así que `/panel`,
 * `/config`, `/corridas` y el resto siguen donde estaban — el middleware, el
 * recorrido de Playwright y cualquier enlace guardado no se enteran.
 */
export default function LayoutDelPanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-svh">
      <Barra />
      {children}
    </div>
  );
}
