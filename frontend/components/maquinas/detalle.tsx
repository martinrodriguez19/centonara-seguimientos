"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";

import type { AccionesDeMaquina } from "@/components/maquinas/acciones";
import { Columnas } from "@/components/graficos/graficos";
import { FilaDeEvento } from "@/components/historial/evento";
import { Button } from "@/components/ui/button";
import { CampoNumero } from "@/components/ui/campo";
import { EsqueletoDeLista } from "@/components/ui/esqueleto";
import { Pildora, type Nivel } from "@/components/ui/estado";
import { Cuerpo, Encabezado, Fila, SinFilas, Tabla, Td, Th } from "@/components/ui/tabla";
import { useCorridas, useCorridasConTandas } from "@/lib/consultas";
import { actividadDe, deLaMaquina, diaArgentino, diaCorto, haceCuanto, situacion } from "@/lib/derivados";
import { traerHistorial, traerMensajes, type Corrida, type Maquina } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Las pestañas del detalle de una máquina (Panel v2).
 *
 * Todo sale de lo que el backend ya devuelve: el estado de la máquina viene en
 * `GET /estado`, su actividad en las tandas de `GET /corridas`, sus mensajes
 * en `GET /corridas/{id}/mensajes` y su historial en `GET /historial`. Nada se
 * le pide al agente: la máquina reporta lo que reportaba, esta página lo junta.
 */

const t = textos.maquinas;

// ---------------------------------------------------------------------------
// Resumen
// ---------------------------------------------------------------------------

export function Resumen({
  maquina,
  acciones,
  dejadosHoy,
  topeDelDia,
}: {
  maquina: Maquina;
  acciones: AccionesDeMaquina;
  dejadosHoy?: number;
  topeDelDia?: number;
}) {
  const estado = situacion(maquina);
  const sha = maquina.version_agente?.split(" ")[0];

  const version: { texto: string; nivel: Nivel } | null =
    maquina.actualizada === true
      ? { texto: textos.maquina.versionAlDia, nivel: "ok" }
      : maquina.actualizada === false
        ? { texto: textos.maquina.versionAtrasada, nivel: "atencion" }
        : maquina.version_agente && maquina.version_esperada
          ? { texto: textos.maquina.versionSinActualizador, nivel: "neutro" }
          : null;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Bloque titulo={t.estado}>
        <Dato nombre={t.estado}>
          <Pildora nivel={estado.nivel}>{estado.texto}</Pildora>
        </Dato>
        <Dato nombre={textos.maquina.ultimoLatido}>
          <span className="font-mono tabular-nums">{haceCuanto(maquina.ultimo_latido)}</span>
          {maquina.ultimo_latido && (
            <span className="block text-xs text-muted-foreground">
              {new Date(maquina.ultimo_latido).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "medium" })}
            </span>
          )}
        </Dato>
        <Dato nombre={t.puedeEnviar}>
          {maquina.puede_enviar ? (
            t.si
          ) : (
            <span className="inline-flex flex-wrap items-center gap-2">
              {t.no} · {textos.maquina.sinConsentimiento}
              {maquina.activo && (
                <Button size="xs" variant="outline" onClick={acciones.pedirConsentimiento}>
                  {textos.maquina.registrarConsentimiento}
                </Button>
              )}
            </span>
          )}
        </Dato>
        <Dato nombre={textos.maquina.modo}>
          {maquina.modo_agente === "simulado" ? (
            <Pildora nivel="atencion">{maquina.modo_agente}</Pildora>
          ) : (
            <span className="font-mono">{maquina.modo_agente ?? "—"}</span>
          )}
        </Dato>
        <Dato nombre={textos.maquina.version}>
          <span className="font-mono">{sha ?? "—"}</span> {version && <Pildora nivel={version.nivel}>{version.texto}</Pildora>}
          {maquina.actualizada === false && maquina.version_esperada && (
            <span className="block text-xs text-muted-foreground">
              {textos.maquina.versionEsperada(maquina.version_esperada)}
            </span>
          )}
        </Dato>
      </Bloque>

      <Bloque titulo={t.hoy}>
        <Dato nombre={t.usoHoy}>
          <span className="font-mono text-lg font-semibold tabular-nums">{dejadosHoy ?? "—"}</span>
          {topeDelDia ? <span className="font-mono text-muted-foreground tabular-nums"> / {topeDelDia}</span> : null}
        </Dato>
        <div className="py-3">
          {/* Lo que protege la línea de ESTE vendedor: no todas las líneas
              aguantan lo mismo. */}
          <CampoNumero
            etiqueta={textos.maquina.topeDiario}
            ayuda={textos.maquina.topeDiarioAyuda}
            valor={maquina.tope_diario}
            min={1}
            max={100}
            guardando={acciones.tope.isPending}
            onGuardar={(valor) => acciones.tope.mutate(valor)}
            className="w-28"
          />
        </div>
        {maquina.barrido && (
          <Dato nombre={t.barrido}>
            {maquina.barrido.completado_en
              ? `${t.barridoAlDia} ✓`
              : maquina.barrido.hasta_dias != null
                ? t.vaPor(maquina.barrido.hasta_dias)
                : t.arrancando}{" "}
            <Button size="xs" variant="ghost" disabled={acciones.reiniciar.isPending} onClick={() => acciones.pedirReinicio("barrido")}>
              {t.reiniciar}
            </Button>
          </Dato>
        )}
        {maquina.ventana && (
          <Dato nombre={t.ventana}>
            {maquina.ventana.hasta_dias != null
              ? t.vaPor(maquina.ventana.hasta_dias)
              : maquina.ventana.completado_en
                ? t.ventanaCompleta
                : t.arrancando}{" "}
            <Button size="xs" variant="ghost" disabled={acciones.reiniciar.isPending} onClick={() => acciones.pedirReinicio("ventana")}>
              {t.reiniciar}
            </Button>
          </Dato>
        )}
      </Bloque>

      <p className="text-xs text-muted-foreground lg:col-span-2">{t.sinLatidosGuardados}</p>
    </div>
  );
}

function Bloque({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border bg-card px-5 sombra-suave">
      <h2 className="border-b py-3 text-sm font-semibold">{titulo}</h2>
      <dl className="divide-y">{children}</dl>
    </section>
  );
}

function Dato({ nombre, children }: { nombre: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] items-baseline gap-3 py-3 text-sm">
      <dt className="text-muted-foreground">{nombre}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chequeos
// ---------------------------------------------------------------------------

/**
 * Los chequeos, todos y no sólo los que fallan: ver ocho en verde y dos en "no
 * aplica" dice que la máquina está bien, no solamente que no está mal.
 */
export function Chequeos({ maquina }: { maquina: Maquina }) {
  const lista = Object.entries(maquina.diagnostico ?? {});
  // Los que fallan primero: es lo que se viene a buscar.
  const orden = { falla: 0, ok: 1 } as Record<string, number>;
  lista.sort((a, b) => (orden[a[1]] ?? 2) - (orden[b[1]] ?? 2));

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t.chequeosBajada}</p>
      {lista.length === 0 ? (
        <p className="rounded-xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">{t.sinChequeos}</p>
      ) : (
        <ul className="divide-y overflow-hidden rounded-xl border bg-card sombra-suave">
          {lista.map(([clave, resultado]) => {
            const texto = textos.chequeos[clave];
            const nivel: Nivel = resultado === "ok" ? "ok" : resultado === "falla" ? "atencion" : "neutro";
            return (
              <li key={clave} className="space-y-1 px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{texto?.nombre ?? clave}</span>
                  <Pildora nivel={nivel}>
                    {resultado === "ok"
                      ? textos.maquina.chequeoOk
                      : resultado === "falla"
                        ? textos.maquina.chequeoFalla
                        : textos.maquina.chequeoNoAplica}
                  </Pildora>
                </div>
                {resultado === "falla" && texto && (
                  <p className="text-sm text-muted-foreground">
                    {texto.detalle} <span className="text-foreground">{texto.queHacer}</span>
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Actividad
// ---------------------------------------------------------------------------

function describirSalteos(salteados: number, motivos: Record<string, number>): string {
  if (salteados === 0) return "—";
  const partes = Object.entries(motivos)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([motivo, n]) => `${n} ${textos.corrida.motivosDeSalteo[motivo] ?? motivo}`);
  return partes.length > 0 ? partes.join(", ") : String(salteados);
}

export function Actividad({ maquina }: { maquina: Maquina }) {
  const suyas = useCorridasConTandas((todas) => deLaMaquina(todas, maquina.maquina));
  const filas = actividadDe(suyas.corridas, maquina.maquina);

  if (suyas.cargando) return <EsqueletoDeLista filas={3} />;
  if (filas.length === 0) {
    return <p className="rounded-xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">{t.sinActividad}</p>;
  }

  // Para el gráfico, de la más vieja a la más nueva, y hasta veinte.
  const enOrden = [...filas].reverse().slice(-20);

  return (
    <div className="space-y-4">
      <section className="rounded-xl border bg-card p-5 sombra-suave">
        <h2 className="text-sm font-semibold">{t.dejados}</h2>
        <p className="mb-4 text-xs text-muted-foreground">{t.actividadBajada(enOrden.length)}</p>
        <Columnas
          titulo={t.dejados}
          puntos={enOrden.map((f) => ({
            clave: f.corrida.id,
            etiqueta: diaCorto(diaArgentino(f.corrida.creada_en)),
            valor: f.dejados,
            detalle: `${f.pedidos} ${t.pedidos.toLowerCase()} · ${f.salteados} ${t.salteados.toLowerCase()}`,
          }))}
        />
      </section>

      <Tabla etiqueta={t.pestanas.actividad}>
        <Encabezado>
          <Th>{t.cuando}</Th>
          <Th numerica>{t.pedidos}</Th>
          <Th numerica>{t.dejados}</Th>
          <Th numerica>{t.salteados}</Th>
          <Th>{t.porQueSalteo}</Th>
          <Th>{t.corte}</Th>
        </Encabezado>
        <Cuerpo>
          {filas.map((f) => (
            <Fila key={f.corrida.id}>
              <Td>
                <Link href={`/corrida/${f.corrida.id}`} className="text-accion-tinta hover:underline">
                  {new Date(f.corrida.creada_en).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" })}
                </Link>
              </Td>
              <Td numerica>{f.pedidos}</Td>
              <Td numerica>{f.dejados}</Td>
              <Td numerica>{f.salteados}</Td>
              <Td>{describirSalteos(f.salteados, f.motivos)}</Td>
              <Td>
                {f.error ? (
                  <span className="text-critico">{textos.corrida.porQueFallo(f.error.codigo, f.error.motivo)}</span>
                ) : f.corte ? (
                  (textos.corrida.finDeTanda[f.corte] ?? f.corte)
                ) : (
                  "—"
                )}
              </Td>
            </Fila>
          ))}
        </Cuerpo>
      </Tabla>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mensajes
// ---------------------------------------------------------------------------

const CORRIDAS_DE_MENSAJES = 3;

export function Mensajes({ maquina }: { maquina: Maquina }) {
  const corridas = useCorridas();
  // Las últimas corridas en las que participó, no las últimas en general: una
  // máquina que estuvo pausada una semana igual muestra lo suyo.
  const suyas: Corrida[] = (corridas.data?.corridas ?? [])
    .filter((c) => c.tipo === "generacion" && c.maquinas.includes(maquina.maquina))
    .slice(0, CORRIDAS_DE_MENSAJES);

  const revisiones = useQueries({
    queries: suyas.map((c) => ({ queryKey: ["mensajes", c.id], queryFn: () => traerMensajes(c.id) })),
  });

  if (corridas.isPending || revisiones.some((r) => r.isPending)) return <EsqueletoDeLista filas={3} />;

  const filas = suyas.flatMap((corrida, i) =>
    (revisiones[i]?.data?.mensajes ?? [])
      .filter((m) => m.maquina === maquina.maquina)
      .map((mensaje) => ({ corrida, mensaje })),
  );

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t.mensajesBajada(suyas.length)}</p>
      <Tabla etiqueta={t.pestanas.mensajes}>
        <Encabezado>
          <Th>{t.contacto}</Th>
          <Th>{t.estadoMensaje}</Th>
          <Th>{t.etiqueta}</Th>
          <Th>{textos.corrida.quePaso}</Th>
          <Th>{t.cuando}</Th>
        </Encabezado>
        <Cuerpo>
          {filas.length === 0 && <SinFilas columnas={5}>{t.sinMensajes}</SinFilas>}
          {filas.map(({ corrida, mensaje }) => (
            <Fila key={mensaje.id}>
              <Td>
                <span className="font-medium">{mensaje.contacto_nombre}</span>
                <span className="block max-w-xs truncate text-xs text-muted-foreground" title={mensaje.texto}>
                  {mensaje.resumen || mensaje.texto}
                </span>
              </Td>
              <Td>{textos.estados[mensaje.estado] ?? mensaje.estado}</Td>
              <Td>{mensaje.etiqueta ? <span className="font-mono text-xs">{mensaje.etiqueta}</span> : "—"}</Td>
              <Td>{mensaje.motivo ? (textos.motivos[mensaje.motivo] ?? mensaje.motivo) : "—"}</Td>
              <Td>
                <Link href={`/revision/${corrida.id}`} className="text-accion-tinta hover:underline">
                  {new Date(corrida.creada_en).toLocaleDateString("es-AR", { dateStyle: "short" })}
                </Link>
              </Td>
            </Fila>
          ))}
        </Cuerpo>
      </Tabla>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Historial
// ---------------------------------------------------------------------------

/**
 * Los eventos de esta máquina: los que hizo ella (`quien`) y los que la
 * nombran en el detalle (un alta, una baja, un cambio de tope). El filtro es
 * del lado del panel, sobre los últimos 500.
 */
export function HistorialDeMaquina({ maquina }: { maquina: Maquina }) {
  const historial = useQuery({ queryKey: ["historial", 500], queryFn: () => traerHistorial(500) });
  const eventos = useMemo(() => {
    const id = maquina.maquina;
    return (historial.data?.eventos ?? []).filter((evento) => {
      if (evento.quien === id) return true;
      const detalle = evento.detalle ?? {};
      if (detalle.maquina === id) return true;
      return Array.isArray(detalle.maquinas) && detalle.maquinas.includes(id);
    });
  }, [historial.data, maquina.maquina]);

  if (historial.isPending) return <EsqueletoDeLista filas={4} />;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t.historialBajada}</p>
      {eventos.length === 0 ? (
        <p className="rounded-xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">{t.sinHistorial}</p>
      ) : (
        <ol className="divide-y rounded-xl border bg-card sombra-suave">
          {eventos.slice(0, 50).map((evento) => (
            <FilaDeEvento key={evento._id} evento={evento} />
          ))}
        </ol>
      )}
    </div>
  );
}
