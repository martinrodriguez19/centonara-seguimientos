"use client";

import { Button } from "@/components/ui/button";
import { Aviso } from "@/components/ui/estado";
import { ErrorDeApi } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Un error al traer datos, dicho según lo que en realidad pasó.
 *
 * Antes todas las pantallas hacían lo mismo: `<p className="text-destructive">
 * {error.message}</p>`. Eso mezcla tres situaciones muy distintas en una sola
 * línea roja:
 *
 * - **El backend no contesta.** No hay nada que hacer más que esperar; el proxy
 *   ya lo distingue con su propio código. Decirlo con calma evita la llamada.
 * - **La sesión venció.** Se resuelve entrando de nuevo, y la pantalla puede
 *   decirlo en vez de dejar un mensaje que no se entiende.
 * - **Cualquier otra cosa.** Ahí sí se muestra el mensaje del servidor, que es
 *   feo pero es información — y sobre todo, aparece.
 */
export function ErrorDeCarga({
  error,
  onReintentar,
}: {
  error: unknown;
  onReintentar?: () => void;
}) {
  const api = error instanceof ErrorDeApi ? error : null;

  if (api?.esBackendCaido) {
    return (
      <Aviso
        nivel="atencion"
        titulo={textos.sinBackend.titulo}
        accion={
          onReintentar && (
            <Button variant="outline" size="sm" onClick={onReintentar}>
              {textos.sinBackend.reintentar}
            </Button>
          )
        }
      >
        {textos.sinBackend.detalle}
      </Aviso>
    );
  }

  return (
    <Aviso
      nivel="critico"
      titulo="No se pudieron traer los datos"
      accion={
        onReintentar && (
          <Button variant="outline" size="sm" onClick={onReintentar}>
            {textos.sinBackend.reintentar}
          </Button>
        )
      }
    >
      {api?.message ?? "Error desconocido."}
    </Aviso>
  );
}
