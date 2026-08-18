import { EstadoDelBackend } from "@/components/estado-backend";
import { consultarSalud } from "@/lib/api";
import { textos } from "@/lib/textos";

const t = textos.diagnostico;

// Sin esto Next renderiza la página en el build y quedaría congelada con el
// estado que había en ese momento.
export const dynamic = "force-dynamic";

/**
 * Página de diagnóstico del Sprint 0 (T0.4).
 *
 * Componente de servidor (08 §3): la consulta al backend la hace el servidor y
 * la primera pintura ya trae el estado real. Lo que sigue —el refresco cada
 * cinco segundos— es del cliente, en `EstadoDelBackend`.
 *
 * Las pantallas del producto son del Sprint 3. Acá no hay nada del producto a
 * propósito.
 */
export default async function Diagnostico() {
  const estado = await consultarSalud();

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-16">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">{t.titulo}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t.subtitulo}</p>
      </header>

      <EstadoDelBackend inicial={estado} />
    </main>
  );
}
