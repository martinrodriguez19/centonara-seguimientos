"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, DollarSign, FileText, PencilLine, Send, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { Barras, Columnas } from "@/components/graficos/graficos";
import { Pagina } from "@/components/navegacion/pagina";
import { Indicador } from "@/components/ui/indicador";
import { Esqueleto } from "@/components/ui/esqueleto";
import { Opciones } from "@/components/ui/opciones";
import { Cuerpo, Encabezado, Fila, SinFilas, Tabla, Td, Th } from "@/components/ui/tabla";
import { useCorridasConTandas, useEstado } from "@/lib/consultas";
import {
  costoPorCorrida,
  dejadosPorDia,
  delPeriodo,
  diaCorto,
  generaciones,
  motivosDeSalteo,
  porMaquina,
} from "@/lib/derivados";
import { traerMetricas } from "@/lib/panel";
import { textos } from "@/lib/textos";

const PERIODOS = ["7", "30", "90"] as const;
const t = textos.estadisticas;

/**
 * Estadísticas (Panel v2).
 *
 * El bloque "Cómo viene" del inicio creció a página propia. Dos fuentes, y la
 * página dice cuál es cuál:
 *
 * - **Los números del período** salen de `GET /metricas?dias=`: los calcula el
 *   servidor sobre todos los mensajes, así que son exactos.
 * - **Los gráficos** salen de las tandas de `GET /corridas`, que devuelve hasta
 *   50 corridas. Para 90 días con más de una corrida por día eso queda corto,
 *   y la página lo dice en vez de mostrar un número incompleto como si fuera
 *   el total.
 *
 * El número que importa sigue siendo la **tasa de edición**: "23 enviados" no
 * distingue un sistema que funciona de uno que la gente corrige a mano todos
 * los días. En rojo pasada la mitad.
 */
export default function Estadisticas() {
  const [periodo, setPeriodo] = useState<(typeof PERIODOS)[number]>("30");
  const dias = Number(periodo);
  const metricas = useQuery({ queryKey: ["metricas", dias], queryFn: () => traerMetricas(dias) });
  const corridas = useCorridasConTandas((todas) => delPeriodo(generaciones(todas), dias));
  const estado = useEstado();
  const enPeriodo = corridas.corridas;
  const nombres = useMemo(
    () => Object.fromEntries((estado.data?.maquinas ?? []).map((m) => [m.maquina, m.nombre])),
    [estado.data],
  );
  // El servidor devuelve hasta 50. Si la más vieja de esas 50 todavía cae
  // dentro del período, puede haber más atrás que no se ven.
  const masVieja = corridas.todas.at(-1);
  const recortado = corridas.todas.length >= 50 && !!masVieja && delPeriodo([masVieja], dias).length === 1;

  const m = metricas.data;
  const porcentaje = (valor: number) => `${Math.round(valor * 100)}%`;
  const dolares = (valor: number) => `US$ ${valor.toFixed(valor >= 10 ? 0 : 2)}`;
  const fallidos = Object.entries(m?.fallidos ?? {}).sort((a, b) => b[1] - a[1]);
  const maquinas = porMaquina(enPeriodo);
  const maximoDejados = Math.max(1, ...maquinas.map((f) => f.dejados));

  return (
    <Pagina
      titulo={t.titulo}
      bajada={t.bajada}
      acciones={
        <Opciones
          etiqueta={textos.metricas.periodo}
          valor={periodo}
          opciones={PERIODOS.map((p) => ({ valor: p, texto: textos.metricas.dias(Number(p)) }))}
          onCambiar={setPeriodo}
        />
      }
    >
      {!m ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Esqueleto key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Indicador
            etiqueta={textos.metricas.enviados}
            valor={m.enviados.toLocaleString("es-AR")}
            ayuda={textos.metricas.enviadosAyuda(m.corridas, m.mensajes)}
            icono={Send}
          />
          <Indicador
            etiqueta={textos.metricas.reescritos}
            valor={porcentaje(m.tasa_edicion)}
            ayuda={textos.metricas.reescritosAyuda}
            icono={PencilLine}
            tinta={m.tasa_edicion > 0.5 ? "text-critico" : undefined}
          />
          <Indicador
            etiqueta={t.tasaRetencion}
            valor={porcentaje(m.tasa_retencion)}
            ayuda={textos.metricas.apartadosAyuda}
            icono={ShieldAlert}
            tinta={m.tasa_retencion > 0.35 ? "text-atencion" : undefined}
          />
          <Indicador
            etiqueta={textos.metricas.costoPorMensaje}
            valor={m.enviados ? `US$ ${m.costo_por_enviado.toFixed(3)}` : "—"}
            ayuda={textos.metricas.costoTotal(m.costo_usd)}
            icono={DollarSign}
          />
          <Indicador etiqueta={t.corridas} valor={m.corridas} icono={Activity} />
          <Indicador etiqueta={textos.corrida.borradores} valor={m.mensajes.toLocaleString("es-AR")} icono={FileText} />
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        {t.basadoEn(enPeriodo.length)} {recortado && t.limite}
      </p>

      <Panel titulo={t.porDia} ayuda={t.porDiaAyuda}>
        {corridas.cargando ? (
          <Esqueleto className="h-40" />
        ) : (
          <Columnas
            titulo={t.porDia}
            puntos={dejadosPorDia(enPeriodo, dias).map((p) => ({ clave: p.dia, etiqueta: diaCorto(p.dia), valor: p.valor }))}
          />
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel titulo={t.porQueSalteo} ayuda={t.porQueSalteoAyuda}>
          <Barras
            vacio={t.sinDatos}
            filas={motivosDeSalteo(enPeriodo).map(([motivo, n]) => ({
              clave: motivo,
              etiqueta: textos.corrida.motivosDeSalteo[motivo] ?? motivo,
              valor: n,
            }))}
          />
        </Panel>
        <Panel titulo={t.porQueFallo} ayuda={t.porQueFalloAyuda}>
          <Barras
            vacio={t.sinDatos}
            filas={fallidos.map(([codigo, n]) => ({
              clave: codigo,
              // El texto largo de `motivos` es una oración; acá alcanza el código.
              etiqueta: codigo,
              valor: n,
            }))}
          />
        </Panel>
      </div>

      <Panel titulo={t.porMaquina} ayuda={t.porMaquinaAyuda}>
        <Tabla etiqueta={t.porMaquina}>
          <Encabezado>
            <Th>{t.maquina}</Th>
            <Th>{t.dejados}</Th>
            <Th numerica>{t.salteados}</Th>
            <Th numerica>{t.conError}</Th>
          </Encabezado>
          <Cuerpo>
            {maquinas.length === 0 && <SinFilas columnas={4}>{t.sinDatos}</SinFilas>}
            {maquinas.map((fila) => (
              <Fila key={fila.maquina}>
                <Td>{nombres[fila.maquina] ?? fila.maquina}</Td>
                <Td>
                  <span className="flex items-center gap-3">
                    <span className="h-2 w-32 rounded-full bg-muted" aria-hidden>
                      <span
                        className="block h-full rounded-full bg-accion"
                        style={{ width: `${Math.max(2, (fila.dejados / maximoDejados) * 100)}%` }}
                      />
                    </span>
                    <span className="font-mono tabular-nums">{fila.dejados}</span>
                  </span>
                </Td>
                <Td numerica>{fila.salteados}</Td>
                <Td numerica>
                  <span className={fila.conError > 0 ? "text-critico" : undefined}>{fila.conError}</span>
                </Td>
              </Fila>
            ))}
          </Cuerpo>
        </Tabla>
      </Panel>

      <Panel titulo={t.costo} ayuda={t.costoAyuda}>
        {corridas.cargando ? (
          <Esqueleto className="h-40" />
        ) : (
          <Columnas
            titulo={t.costo}
            formato={dolares}
            puntos={costoPorCorrida(enPeriodo).map((p) => ({ clave: p.id, etiqueta: diaCorto(p.dia), valor: p.valor }))}
          />
        )}
      </Panel>
    </Pagina>
  );
}

function Panel({ titulo, ayuda, children }: { titulo: string; ayuda?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border bg-card p-5 sombra-suave">
      <h2 className="text-sm font-semibold">{titulo}</h2>
      {ayuda && <p className="text-xs text-muted-foreground">{ayuda}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}
