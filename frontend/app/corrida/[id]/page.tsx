"use client";

import { useQuery } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import Link from "next/link";
import { use } from "react";

import { ErrorDeCarga } from "@/components/error-de-carga";
import { Button } from "@/components/ui/button";
import { EsqueletoDeLista } from "@/components/ui/esqueleto";
import { Pildora, type Nivel } from "@/components/ui/estado";
import { Cuerpo, Encabezado, Fila, SinFilas, Tabla, Td, Th } from "@/components/ui/tabla";
import {
  traerCorrida,
  traerMensajes,
  traerMetricasDeCorrida,
  type Mensaje,
} from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Una corrida, de punta a punta.
 *
 * **Es la pantalla que faltaba, y el hueco que tapaba era grande.** El panel
 * acompañaba hasta que alguien apretaba enviar, decía "se encolaron 3 mensajes"
 * y a partir de ahí no volvía a hablar del tema: los estados `ENVIANDO` y
 * `ENVIADO` no se mostraban en ningún lado. No había forma de saber si salieron,
 * si alguno abortó, ni por qué.
 *
 * Y tampoco había forma de abrir una corrida de la semana pasada: `traerCorrida`
 * estaba escrito en el cliente de API y no lo usaba nadie, y la ruta de métricas
 * por corrida ni siquiera estaba en el cliente.
 *
 * Se refresca sola mientras haya algo en movimiento, y deja de hacerlo cuando
 * todo terminó. Una pantalla que consulta para siempre contra un backend que ya
 * no tiene nada que decir es ruido.
 */
export default function DetalleDeCorrida({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const corrida = useQuery({
    queryKey: ["corrida", id],
    queryFn: () => traerCorrida(id),
    refetchInterval: (consulta) => (consulta.state.data?.terminada ? false : 4000),
  });

  const revision = useQuery({
    queryKey: ["mensajes", id],
    queryFn: () => traerMensajes(id),
    refetchInterval: (consulta) => {
      const enMovimiento = consulta.state.data?.mensajes.some(
        (m) => m.estado === "ENVIANDO" || m.estado === "EN_ESPERA",
      );
      return enMovimiento ? 4000 : false;
    },
  });

  const metricas = useQuery({
    queryKey: ["metricas-corrida", id],
    queryFn: () => traerMetricasDeCorrida(id),
    refetchInterval: (consulta) => (corrida.data?.terminada ? false : 8000),
  });

  if (corrida.isPending) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-8">
        <EsqueletoDeLista filas={3} />
      </main>
    );
  }

  if (corrida.isError) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-8">
        <ErrorDeCarga error={corrida.error} onReintentar={() => void corrida.refetch()} />
      </main>
    );
  }

  const datos = corrida.data;
  const mensajes = revision.data?.mensajes ?? [];
  const enviados = mensajes.filter((m) => m.estado === "ENVIADO" || m.estado === "ENVIANDO");
  const hayBorradores = mensajes.some(
    (m) => m.estado === "RETENIDO" || m.estado === "EN_ESPERA" || m.estado === "BORRADOR",
  );
  const hechos = datos.jobs.total - datos.jobs.pendientes;

  return (
    <main className="mx-auto max-w-4xl space-y-6 px-6 py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">
            {datos.tipo === "generacion" ? textos.corrida.tituloGeneracion : textos.corrida.tituloDiagnostico}
          </h1>
          <p className="text-sm text-muted-foreground">
            {new Date(datos.creada_en).toLocaleString("es-AR", {
              dateStyle: "long",
              timeStyle: "short",
            })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* ⚠️ El modo, siempre visible. Mirando una corrida vieja, saber si
              fue un ensayo o salieron mensajes de verdad es lo primero. */}
          <Pildora nivel={datos.modo === "real" ? "critico" : "neutro"}>
            {datos.modo === "real" ? textos.corrida.modoReal : textos.corrida.modoPrueba}
          </Pildora>
          <Pildora nivel={datos.terminada ? "ok" : "atencion"}>
            {datos.terminada ? textos.corrida.terminada : textos.corrida.enCurso}
          </Pildora>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/corridas">{textos.corrida.verTodas}</Link>
          </Button>
        </div>
      </div>

      <section className="grid gap-3 sm:grid-cols-4" aria-label={textos.corrida.resumen}>
        <Dato titulo={textos.corrida.avance} valor={`${hechos} / ${datos.jobs.total}`} ayuda={textos.corrida.avanceAyuda} />
        <Dato titulo={textos.corrida.maquinas} valor={String(datos.maquinas.length)} />
        <Dato
          titulo={textos.corrida.borradores}
          valor={metricas.data ? String(metricas.data.mensajes) : "—"}
          ayuda={
            metricas.data && metricas.data.editados > 0
              ? textos.corrida.editados(metricas.data.editados)
              : undefined
          }
        />
        <Dato
          titulo={textos.corrida.costo}
          valor={`US$ ${datos.costo_usd.toFixed(3)}`}
          ayuda={
            metricas.data && metricas.data.mensajes > 0
              ? textos.corrida.costoPorBorrador(datos.costo_usd / metricas.data.mensajes)
              : undefined
          }
        />
      </section>

      {hayBorradores && (
        <Button variant="outline" asChild>
          <Link href={`/revision/${id}`}>
            <ClipboardList className="size-4" aria-hidden />
            {textos.corrida.irARevision}
          </Link>
        </Button>
      )}

      {/* El tramo que no existía: qué pasó con cada mensaje después de apretar
          enviar. Si todavía no se envió nada, la sección no aparece. */}
      {enviados.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-base font-semibold">{textos.corrida.envio}</h2>
          <p className="text-sm text-muted-foreground">{textos.corrida.envioAyuda}</p>
          <TablaDeEnvio mensajes={enviados} />
        </section>
      )}

      {metricas.data && metricas.data.mensajes > 0 && (
        <section className="space-y-2">
          <h2 className="text-base font-semibold">{textos.corrida.reparto}</h2>
          <Tabla etiqueta={textos.corrida.reparto}>
            <Encabezado>
              <Th>{textos.corrida.estado}</Th>
              <Th numerica>{textos.corrida.cuantos}</Th>
            </Encabezado>
            <Cuerpo>
              {Object.entries(metricas.data.por_estado).map(([estado, cuantos]) => (
                <Fila key={estado}>
                  <Td>{textos.estados[estado] ?? estado}</Td>
                  <Td numerica>{cuantos}</Td>
                </Fila>
              ))}
            </Cuerpo>
          </Tabla>
        </section>
      )}
    </main>
  );
}

function Dato({
  titulo,
  valor,
  ayuda,
}: {
  titulo: string;
  valor: string;
  ayuda?: string;
}) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <p className="text-xs text-muted-foreground">{titulo}</p>
      <p className="text-2xl font-semibold tabular-nums">{valor}</p>
      {ayuda && <p className="text-xs text-muted-foreground">{ayuda}</p>}
    </div>
  );
}

/**
 * Qué pasó con cada mensaje que se mandó a enviar.
 *
 * El motivo se traduce. Un `SIN_CONFIRMAR` crudo en la pantalla no le dice a
 * nadie que **el mensaje puede haber salido** y que conviene mirar el teléfono
 * del vendedor antes de tocar nada — y esa es exactamente la única fila de esta
 * tabla que pide una acción inmediata.
 */
function TablaDeEnvio({ mensajes }: { mensajes: Mensaje[] }) {
  const nivelDe = (mensaje: Mensaje): Nivel => {
    if (mensaje.estado === "ENVIADO") return "ok";
    if (mensaje.estado === "ENVIANDO") return "neutro";
    return "critico";
  };

  return (
    <Tabla etiqueta={textos.corrida.envio}>
      <Encabezado>
        <Th>{textos.corrida.contacto}</Th>
        <Th>{textos.corrida.maquina}</Th>
        <Th>{textos.corrida.estado}</Th>
        <Th>{textos.corrida.quePaso}</Th>
      </Encabezado>
      <Cuerpo>
        {mensajes.length === 0 && (
          <SinFilas columnas={4}>{textos.corrida.sinEnvios}</SinFilas>
        )}
        {mensajes.map((mensaje) => (
          <Fila key={mensaje.id}>
            <Td>
              <span className="font-medium">{mensaje.contacto_nombre || "Sin nombre"}</span>
              <span className="block font-mono text-xs text-muted-foreground">
                {mensaje.contacto_id}
              </span>
            </Td>
            <Td className="font-mono text-xs">{mensaje.maquina}</Td>
            <Td>
              <Pildora nivel={nivelDe(mensaje)}>
                {textos.estados[mensaje.estado] ?? mensaje.estado}
              </Pildora>
            </Td>
            <Td className="text-muted-foreground">
              {mensaje.motivo ? (textos.motivos[mensaje.motivo] ?? mensaje.motivo) : "—"}
            </Td>
          </Fila>
        ))}
      </Cuerpo>
    </Tabla>
  );
}
