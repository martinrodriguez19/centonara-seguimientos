"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { ErrorDeCarga } from "@/components/error-de-carga";
import { Button } from "@/components/ui/button";
import { EsqueletoDeLista } from "@/components/ui/esqueleto";
import { traerHistorial, type Evento } from "@/lib/panel";
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

/** Los nombres técnicos no se le muestran a nadie. */
const QUE: Record<string, string> = {
  corrida_disparada: "Se disparó una corrida",
  corrida_cancelada: "Se canceló una corrida",
  corrida_reanudada: "Se reanudó una corrida frenada",
  datos_borrados: "Se vació el sistema para entregarlo",
  mensaje_enviado: "Se envió un mensaje",
  borrador_dejado: "Se dejó un borrador en el WhatsApp del vendedor",
  mensaje_vetado: "Se frenó un mensaje",
  mensaje_editado: "Se editó un mensaje",
  mensaje_liberado: "Se liberó un mensaje retenido",
  mensaje_descartado: "Se descartó un mensaje",
  envio_abortado: "Se abortó un envío",
  kill_switch: "Se usó el freno de emergencia",
  configuracion_cambiada: "Cambió la configuración",
  destinos_cambiados: "Cambiaron los destinos permitidos",
  maquina_alta: "Se dio de alta una máquina",
  maquina_baja: "Se dio de baja una máquina",
  consentimiento_registrado: "Se registró el consentimiento de un vendedor",
};

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
    <main className="mx-auto max-w-4xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">{textos.historial.titulo}</h1>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/panel">{textos.revision.volver}</Link>
        </Button>
      </div>

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
                <Fila key={evento._id} evento={evento} />
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
    </main>
  );
}

function Fila({ evento }: { evento: Evento }) {
  const cuando = new Date(evento.cuando);
  return (
    <li className="space-y-1 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <time dateTime={evento.cuando} className="w-40 shrink-0 tabular-nums text-muted-foreground">
          {cuando.toLocaleString("es-AR", { dateStyle: "short", timeStyle: "medium" })}
        </time>
        <span className="font-medium">{QUE[evento.que] ?? evento.que}</span>
        <span className="text-muted-foreground">— {evento.quien}</span>
        {/* Ahora hay a dónde ir. Antes el identificador de la corrida estaba
            adentro del JSON y no llevaba a ninguna parte. */}
        {evento.corrida_id && (
          <Link
            href={`/corrida/${evento.corrida_id}`}
            className="text-accion underline-offset-2 hover:underline"
          >
            {textos.historial.verCorrida}
          </Link>
        )}
      </div>
      <Detalle detalle={evento.detalle} />
    </li>
  );
}

/**
 * El detalle de un evento, en castellano.
 *
 * Antes era `JSON.stringify(evento.detalle)` en una línea de ancho completo.
 * Acá cada clave conocida se dice como la diría una persona, y lo que no se
 * conoce cae en `clave: valor` — que es feo pero se lee, y sobre todo aparece.
 * Perder un dato del registro porque no se supo cómo mostrarlo sería peor.
 */
function Detalle({ detalle }: { detalle: Record<string, unknown> }) {
  const claves = Object.keys(detalle ?? {});
  if (claves.length === 0) return null;

  const NOMBRES: Record<string, string> = {
    tipo: "Tipo",
    modo: "Modo",
    maquinas: "Máquinas",
    maquina: "Máquina",
    pausado: "Frenado",
    campos: "Qué cambió",
    cantidad: "Cantidad",
    motivo: "Motivo",
    codigo: "Código",
    contacto_id: "Contacto",
  };

  const comoTexto = (valor: unknown): string => {
    if (Array.isArray(valor)) return valor.join(", ");
    if (typeof valor === "boolean") return valor ? "sí" : "no";
    if (valor === null || valor === undefined) return "—";
    if (typeof valor === "object") return JSON.stringify(valor);
    return String(valor);
  };

  return (
    <dl className="flex flex-wrap gap-x-4 gap-y-0.5 pl-0 text-xs text-muted-foreground sm:pl-[10.75rem]">
      {claves.map((clave) => (
        <div key={clave} className="flex gap-1">
          <dt className="font-medium">{NOMBRES[clave] ?? clave}:</dt>
          <dd>
            {clave === "motivo" || clave === "codigo"
              ? (textos.motivos[String(detalle[clave])] ?? comoTexto(detalle[clave]))
              : comoTexto(detalle[clave])}
          </dd>
        </div>
      ))}
    </dl>
  );
}
