"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { Aviso } from "@/components/ui/estado";
import { textos } from "@/lib/textos";

/**
 * Lo que se ve cuando una pantalla se rompe.
 *
 * Sin esto, un error de render en cualquier componente deja la pantalla en
 * blanco: Next muestra su propia página, que en producción dice "Application
 * error: a client-side exception has occurred" y nada más. Para quien usa el
 * panel eso es indistinguible de que se cortó internet.
 *
 * Dos cosas y nada más: qué pasó, y el botón de reintentar. `reset()` vuelve a
 * montar el árbol que falló sin recargar la página entera, así que la sesión y
 * lo que había en caché siguen ahí.
 */
export default function ErrorDePantalla({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Al log del navegador, que es lo que se pide cuando alguien reporta algo.
    // No a la pantalla: el mensaje de un error de React no le dice nada a quien
    // vende materiales.
    console.error("pantalla_rota", error);
  }, [error]);

  return (
    <main className="mx-auto max-w-lg px-6 py-16">
      <Aviso
        nivel="critico"
        titulo={textos.error.titulo}
        accion={
          <Button variant="outline" size="sm" onClick={reset}>
            {textos.error.reintentar}
          </Button>
        }
      >
        <p>{textos.error.detalle}</p>
        {/* El identificador que Next le pone a cada error en producción. Es lo
            único de esta pantalla que sirve para encontrarlo en el log. */}
        {error.digest && (
          <p className="pt-1 font-mono text-xs opacity-80">
            {textos.error.codigo}: {error.digest}
          </p>
        )}
      </Aviso>
    </main>
  );
}
