"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { ErrorDeCarga } from "@/components/error-de-carga";
import { Button } from "@/components/ui/button";
import { EsqueletoDeLista } from "@/components/ui/esqueleto";
import { Pildora } from "@/components/ui/estado";
import { Cuerpo, Encabezado, Fila, SinFilas, Tabla, Td, Th } from "@/components/ui/tabla";
import { traerCorridas } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Las corridas de los últimos días.
 *
 * **No es el historial.** El historial es el registro de auditoría y sirve para
 * reconstruir qué pasó con *un mensaje* el día que alguien se queja. Esto es
 * para la otra pregunta, la que el dueño va a hacer cuando el sistema lleve un
 * mes andando: "¿qué se hizo esta semana, y cuánto salió?".
 *
 * Antes no tenía respuesta en ninguna parte: `GET /estado` trae la última
 * corrida y nada más.
 */
export default function Corridas() {
  const corridas = useQuery({ queryKey: ["corridas"], queryFn: () => traerCorridas(50) });

  return (
    <main className="mx-auto max-w-4xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">{textos.corridas.titulo}</h1>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/panel">{textos.revision.volver}</Link>
        </Button>
      </div>

      {corridas.isPending && <EsqueletoDeLista filas={5} />}

      {corridas.isError && (
        <ErrorDeCarga error={corridas.error} onReintentar={() => void corridas.refetch()} />
      )}

      {corridas.data && (
        <>
          <Tabla etiqueta={textos.corridas.titulo}>
            <Encabezado>
              <Th>{textos.corridas.cuando}</Th>
              <Th>{textos.corridas.que}</Th>
              <Th>{textos.corridas.comoTermino}</Th>
              <Th numerica>{textos.corridas.maquinas}</Th>
              <Th numerica>{textos.corridas.costo}</Th>
            </Encabezado>
            <Cuerpo>
              {corridas.data.corridas.length === 0 && (
                <SinFilas columnas={5}>{textos.corridas.ninguna}</SinFilas>
              )}
              {corridas.data.corridas.map((corrida) => (
                <Fila key={corrida.id}>
                  <Td>
                    {/* Toda la fila lleva a la corrida, pero el enlace vive en
                        una celda: una fila entera clickeable no se puede
                        alcanzar con el teclado ni abrir en otra pestaña. */}
                    <Link
                      href={`/corrida/${corrida.id}`}
                      className="font-medium underline-offset-2 hover:underline"
                    >
                      {new Date(corrida.creada_en).toLocaleString("es-AR", {
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </Link>
                  </Td>
                  <Td>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span>
                        {corrida.tipo === "generacion"
                          ? textos.corridas.generacion
                          : textos.corridas.diagnostico}
                      </span>
                      {/* El modo sólo se marca cuando fue real: una píldora en
                          cada fila diciendo "ensayo" es ruido, y la que importa
                          se pierde entre ellas. */}
                      {corrida.modo === "real" && (
                        <Pildora nivel="critico">{textos.corrida.modoReal}</Pildora>
                      )}
                    </div>
                  </Td>
                  <Td>
                    {/* Frenada y cancelada primero: eran invisibles (D31) y
                        una corrida frenada se veía "en curso" para siempre. */}
                    {corrida.estado === "frenada" ? (
                      <Pildora nivel="critico">{textos.corrida.frenada}</Pildora>
                    ) : corrida.estado === "cancelada" ? (
                      <Pildora nivel="neutro">{textos.corrida.cancelada}</Pildora>
                    ) : corrida.terminada ? (
                      <Pildora nivel={corrida.jobs.fallido ? "atencion" : "ok"}>
                        {corrida.jobs.fallido
                          ? textos.corridas.conFallas(corrida.jobs.fallido)
                          : textos.corrida.terminada}
                      </Pildora>
                    ) : (
                      <Pildora nivel="neutro">{textos.corrida.enCurso}</Pildora>
                    )}
                  </Td>
                  <Td numerica>{corrida.maquinas.length}</Td>
                  <Td numerica>US$ {corrida.costo_usd.toFixed(3)}</Td>
                </Fila>
              ))}
            </Cuerpo>
          </Tabla>

          {corridas.data.corridas.length > 0 && (
            <p className="text-sm text-muted-foreground">
              {textos.corridas.costoTotal(
                corridas.data.corridas.reduce((suma, c) => suma + c.costo_usd, 0),
                corridas.data.corridas.length,
              )}
            </p>
          )}
        </>
      )}
    </main>
  );
}
