import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Aviso } from "@/components/ui/estado";
import { textos } from "@/lib/textos";

/**
 * Una dirección que no existe.
 *
 * Pasa de verdad y no es hipotético: los enlaces del panel llevan
 * identificadores de corrida y de mensaje, y una corrida vieja que ya no está
 * —o un enlace pegado a medias en un chat— cae acá. Sin esta pantalla, Next
 * muestra su 404 en inglés y sin forma de volver.
 */
export default function NoEncontrado() {
  return (
    <main className="mx-auto max-w-lg px-6 py-16">
      <Aviso
        nivel="neutro"
        titulo={textos.noEncontrado.titulo}
        accion={
          <Button variant="outline" size="sm" asChild>
            <Link href="/panel">{textos.noEncontrado.volver}</Link>
          </Button>
        }
      >
        {textos.noEncontrado.detalle}
      </Aviso>
    </main>
  );
}
