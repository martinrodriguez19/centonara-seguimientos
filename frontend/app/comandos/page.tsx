import Link from "next/link";

import { Comando } from "@/components/comando";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { grupos } from "@/lib/comandos";
import { textos } from "@/lib/textos";

export const metadata = {
  title: `${textos.comandos.titulo} — ${textos.app.titulo}`,
};

/**
 * La documentación operativa, adentro del panel.
 *
 * Existe porque el momento en que hacen falta estos comandos es siempre el
 * mismo: alguien está parado frente a la Mac de un vendedor, algo no anda, y la
 * guía está en un PDF que quedó en otra computadora. El panel ya está abierto
 * —es desde donde se mira si la máquina está online— así que los comandos
 * tienen que estar ahí.
 *
 * Es un componente de servidor: el catálogo es estático y no hay nada que
 * consultar. Lo único que necesita el navegador es el botón de copiar, y eso
 * vive en `components/comando.tsx`.
 */
export default function Comandos() {
  return (
    <main className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between gap-4">
        <h1 className="font-heading text-lg font-semibold">{textos.comandos.titulo}</h1>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/panel">{textos.revision.volver}</Link>
        </Button>
      </div>

      <p className="text-sm text-muted-foreground">{textos.comandos.intro}</p>

      <p className="rounded-md border border-atencion-borde bg-atencion-suave px-3 py-2 text-sm text-atencion">
        {textos.comandos.aviso}
      </p>

      {/* El índice. Con tres grupos y veinte comandos, entrar por arriba y
          scrollear hasta encontrar el que se busca es exactamente lo que no
          sirve cuando algo está roto. */}
      <nav aria-label={textos.comandos.indice} className="flex flex-wrap gap-1">
        {grupos.map((grupo) => (
          <Button key={grupo.id} variant="ghost" size="sm" asChild>
            <a href={`#${grupo.id}`}>{grupo.titulo}</a>
          </Button>
        ))}
      </nav>

      {grupos.map((grupo) => (
        <Card key={grupo.id} id={grupo.id} className="scroll-mt-4">
          <CardHeader>
            <CardTitle>{grupo.titulo}</CardTitle>
            <CardDescription>{grupo.descripcion}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* El aviso va ANTES de los comandos, no después: en el apartado de
                macOS viejo lo que dice es que hay algo para probar primero, y
                leerlo al final es haber perdido la tarde. */}
            {grupo.aviso && (
              <p className="rounded-md border border-atencion-borde bg-atencion-suave px-3 py-2 text-sm text-atencion">
                {grupo.aviso}
              </p>
            )}

            {grupo.comandos.map((comando) => (
              <Comando key={comando.id} datos={comando} />
            ))}

            {grupo.pie && (
              <p className="border-t pt-5 text-sm text-muted-foreground">{grupo.pie}</p>
            )}
          </CardContent>
        </Card>
      ))}

      <p className="text-sm text-muted-foreground">{textos.comandos.pie}</p>
    </main>
  );
}
