import { MenuDeAjustes, ProbarMaquinas } from "@/components/config/menu";
import { Pagina } from "@/components/navegacion/pagina";
import { textos } from "@/lib/textos";

/**
 * Ajustes, partidos en secciones (D56).
 *
 * Antes era una sola página de 1.500 líneas con quince tarjetas en fila, y lo
 * más buscado —el envío automático— estaba casi al final. Ahora cada sección
 * es una subruta (`/config/envio`, `/config/lectura`, …) y el menú de la
 * izquierda dice qué hay en cada una. Los datos y los `PATCH` son los mismos.
 */
export default function LayoutDeAjustes({ children }: { children: React.ReactNode }) {
  return (
    <Pagina titulo={textos.config.titulo} bajada="Cada cambio se guarda al momento y queda en el historial, con quién y cuándo." acciones={<ProbarMaquinas />}>
      <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
        <aside className="lg:sticky lg:top-20 lg:self-start">
          <MenuDeAjustes />
        </aside>
        <div className="min-w-0 space-y-6">{children}</div>
      </div>
    </Pagina>
  );
}
