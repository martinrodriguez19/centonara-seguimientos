"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import type { Comando as Datos } from "@/lib/comandos";
import { textos } from "@/lib/textos";

/**
 * Un comando, listo para copiar.
 *
 * La razón de que esta página exista: alguien está parado frente a la Mac de un
 * vendedor con el panel abierto en el teléfono o en otra ventana, y necesita
 * pegar un comando **exacto** en una Terminal. Tipearlo a mano es donde
 * aparecen los errores que después nadie encuentra —una barra de más, un guión
 * que el PDF convirtió en raya—, así que lo único que este componente tiene que
 * hacer bien es entregar el texto sin tocarlo.
 *
 * Por eso el `<pre>` muestra el comando **entero**, cortándolo en varios
 * renglones si hace falta. La alternativa —una sola línea que desborda hacia el
 * costado— dejaba a la vista `… uv run --directory agente python -m age`, y con
 * eso nadie puede verificar qué está por pegar en una Terminal. El salto de
 * línea es visual: lo que el botón copia es siempre el comando completo, en una
 * línea.
 */
export function Comando({ datos }: { datos: Datos }) {
  const [copiado, setCopiado] = useState(false);
  const [fallo, setFallo] = useState(false);

  // Vuelve a "Copiar" solo. Con veinte comandos en la pantalla, tres que digan
  // "Copiado" a la vez no dejan saber cuál se copió último.
  useEffect(() => {
    if (!copiado) return;
    const reloj = setTimeout(() => setCopiado(false), 2000);
    return () => clearTimeout(reloj);
  }, [copiado]);

  const copiar = async () => {
    try {
      // Sin contexto seguro —http a secas, un navegador viejo— la API ni
      // siquiera existe. Se avisa, no se rompe: el texto está a la vista y se
      // puede seleccionar con el mouse.
      await navigator.clipboard.writeText(datos.comando);
      setFallo(false);
      setCopiado(true);
    } catch {
      setFallo(true);
    }
  };

  return (
    <article id={datos.id} className="scroll-mt-20 space-y-2 border-t pt-5 first:border-t-0 first:pt-0">
      <h3 className="font-heading text-base font-medium">{datos.titulo}</h3>
      <p className="text-sm text-muted-foreground">{datos.queHace}</p>

      <div className="flex items-start gap-2">
        <pre className="min-w-0 flex-1 rounded-md border bg-muted p-3">
          <code className="font-mono text-sm whitespace-pre-wrap wrap-anywhere">{datos.comando}</code>
        </pre>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => void copiar()}
          aria-label={`${textos.comandos.copiar}: ${datos.titulo}`}
        >
          {copiado ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
          {copiado ? textos.comandos.copiado : textos.comandos.copiar}
        </Button>
      </div>

      {fallo && <p className="text-sm text-destructive">{textos.comandos.noSePudoCopiar}</p>}

      {datos.hueco && (
        <p className="text-sm">
          <strong className="font-medium">{textos.comandos.reemplazar}:</strong>{" "}
          <span className="text-muted-foreground">{datos.hueco}</span>
        </p>
      )}

      {datos.cuando && (
        <p className="text-sm">
          <strong className="font-medium">{textos.comandos.cuando}:</strong>{" "}
          <span className="text-muted-foreground">{datos.cuando}</span>
        </p>
      )}

      {datos.aviso && (
        <p className="rounded-md border border-atencion-borde bg-atencion-suave px-3 py-2 text-sm text-atencion">
          {datos.aviso}
        </p>
      )}
    </article>
  );
}
