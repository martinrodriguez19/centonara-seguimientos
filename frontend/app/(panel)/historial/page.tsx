"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ErrorDeCarga } from "@/components/error-de-carga";
import { Pagina } from "@/components/navegacion/pagina";
import { Button } from "@/components/ui/button";
import { FilaDeEvento } from "@/components/historial/evento";
import { EsqueletoDeLista } from "@/components/ui/esqueleto";
import { traerHistorial } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * El historial.
 *
 * Es la pantalla que se abre cuando un cliente se queja. Diseñada para ese
 * momento: alguien nervioso buscando qué pasó, que necesita el orden
 * cronológico y quién hizo cada cosa, sin tener que interpretar nada.
 *
 * **Lo que se arregló.** Cumplía la mitad de eso y fallaba justo en la otra: el
 * detalle de cada evento se volcaba con `JSON.stringify` en una línea. La
 * pantalla escrita para "alguien nervioso" le mostraba
 * `{"tipo":"generacion","modo":"prueba","maquinas":["mac-rocio"]}`. Ahora el
 * detalle se lee como texto, hay filtros y hay paginado — con 200 eventos en
 * una sola lista, encontrar el martes pasado era desplazarse a ojo.
 *
 * Y cada evento que menciona una corrida ahora **lleva a la corrida**. Antes no
 * había a dónde llevar: esas pantallas no existían.
 */
const POR_PAGINA = 25;


/** Los grupos del filtro. Menos que los tipos de evento, y a propósito. */
const GRUPOS = {
  todo: () => true,
  mensajes: (que: string) =>
    que.startsWith("mensaje_") || que === "envio_abortado" || que === "borrador_dejado",
  corridas: (que: string) => que.startsWith("corrida_"),
  cambios: (que: string) =>
    que.startsWith("configuracion") ||
    que.startsWith("destinos") ||
    que.startsWith("maquina_") ||
    que === "consentimiento_registrado" ||
    que === "kill_switch",
} as const;

type Grupo = keyof typeof GRUPOS;

export default function Historial() {
  const historial = useQuery({ queryKey: ["historial"], queryFn: () => traerHistorial(200) });
  const [grupo, setGrupo] = useState<Grupo>("todo");
  const [pagina, setPagina] = useState(0);

  const filtrados = useMemo(() => {
    const eventos = historial.data?.eventos ?? [];
    return eventos.filter((evento) => GRUPOS[grupo](evento.que));
  }, [historial.data, grupo]);

  const paginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));
  const enPantalla = filtrados.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA);

  const cambiarGrupo = (nuevo: Grupo) => {
    setGrupo(nuevo);
    // Volver a la primera página: quedarse en la 4 de un filtro que ahora tiene
    // 2 páginas muestra una lista vacía y parece que no hay nada.
    setPagina(0);
  };

  return (
    <Pagina titulo={textos.historial.titulo} bajada={textos.navegacion.historialAyuda}>

      <div className="flex flex-wrap gap-1" role="group" aria-label={textos.historial.filtrar}>
        {(Object.keys(GRUPOS) as Grupo[]).map((opcion) => (
          <Button
            key={opcion}
            variant={opcion === grupo ? "default" : "ghost"}
            size="sm"
            aria-pressed={opcion === grupo}
            onClick={() => cambiarGrupo(opcion)}
          >
            {textos.historial.grupos[opcion]}
          </Button>
        ))}
      </div>

      {historial.isPending && <EsqueletoDeLista filas={6} />}

      {historial.isError && (
        <ErrorDeCarga error={historial.error} onReintentar={() => void historial.refetch()} />
      )}

      {historial.data &&
        (filtrados.length === 0 ? (
          <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            {grupo === "todo" ? textos.historial.vacio : textos.historial.vacioFiltrado}
          </p>
        ) : (
          <>
            <ol className="divide-y rounded-lg border bg-card">
              {enPantalla.map((evento) => (
                <FilaDeEvento key={evento._id} evento={evento} />
              ))}
            </ol>

            {paginas > 1 && (
              <div className="flex items-center justify-between gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={pagina === 0}
                  onClick={() => setPagina((p) => p - 1)}
                >
                  {textos.historial.anteriores}
                </Button>
                <p className="text-sm tabular-nums text-muted-foreground">
                  {textos.historial.pagina(pagina + 1, paginas)}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={pagina >= paginas - 1}
                  onClick={() => setPagina((p) => p + 1)}
                >
                  {textos.historial.siguientes}
                </Button>
              </div>
            )}
          </>
        ))}
    </Pagina>
  );
}
