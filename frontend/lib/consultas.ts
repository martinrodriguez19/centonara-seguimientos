"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { juntarProblemas } from "@/lib/derivados";
import {
  traerAlertas,
  traerConfiguracion,
  traerCorrida,
  traerCorridas,
  traerEstado,
  type Corrida,
} from "@/lib/panel";
import { useVistos } from "@/lib/vistos";

/**
 * Las consultas que comparten varias pantallas, con la misma clave y el mismo
 * ritmo en todas.
 *
 * Desde el Panel v2 la barra de arriba vive en todas las páginas y necesita el
 * estado (para el chip de modo y el freno) y las alertas (para el contador).
 * Si cada pantalla armara su `useQuery` con otro intervalo, TanStack haría la
 * consulta al ritmo del más rápido pero con opciones distintas según quién
 * montó primero. Acá se decide una vez.
 */

/** Cada cinco segundos: las máquinas laten cada treinta y una corrida avanza sola. */
export const useEstado = () =>
  useQuery({ queryKey: ["estado"], queryFn: traerEstado, refetchInterval: 5000 });

/** Cada quince segundos: se calculan al preguntar, y no cambian tan rápido. */
export const useAlertas = () =>
  useQuery({ queryKey: ["alertas"], queryFn: traerAlertas, refetchInterval: 15_000 });

/** Las últimas 50 corridas: el máximo que devuelve el backend. */
export const useCorridas = (refetchInterval: number | false = 30_000) =>
  useQuery({ queryKey: ["corridas"], queryFn: () => traerCorridas(50), refetchInterval });

/**
 * Las corridas **con sus tandas**, que es de donde sale todo lo que se cuenta
 * por máquina y por día.
 *
 * ⚠️ `GET /corridas` (el listado) no trae las tandas: sólo las trae el detalle,
 * `GET /corridas/{id}`. Para no tocar el backend (Panel v2), esto pide el
 * detalle de las corridas que la pantalla necesita —`elegir` decide cuáles— y
 * lo guarda con la misma clave que usa la página de la corrida.
 *
 * Una corrida terminada no cambia más, así que su detalle no se vuelve a pedir
 * nunca (`staleTime: Infinity`). Sólo la que está en curso se refresca.
 */
export function useCorridasConTandas(elegir: (corridas: Corrida[]) => Corrida[]) {
  const lista = useCorridas();
  const elegidas = lista.data ? elegir(lista.data.corridas) : [];
  const detalles = useQueries({
    queries: elegidas.map((c) => ({
      queryKey: ["corrida", c.id],
      queryFn: () => traerCorrida(c.id),
      staleTime: c.terminada ? Infinity : 0,
      refetchInterval: c.terminada ? (false as const) : 30_000,
    })),
  });
  const corridas = elegidas.map((c, i) => detalles[i]?.data ?? c);
  return {
    corridas,
    cargando: lista.isPending || detalles.some((d) => d.isPending),
    /** El listado entero, sin detalle: para saber hasta dónde llega. */
    todas: lista.data?.corridas ?? [],
  };
}

export const useConfiguracion = () =>
  useQuery({ queryKey: ["configuracion"], queryFn: traerConfiguracion });

/**
 * Los errores y avisos de ahora, con lo marcado como visto aparte.
 *
 * Lo usan la barra (para el contador) y la página de errores, así que el
 * número de arriba y la lista de abajo nunca dicen cosas distintas.
 */
export function useProblemas() {
  const estado = useEstado();
  const alertas = useAlertas();
  const { vistos, marcar, desmarcar, podar } = useVistos();

  const todos = useMemo(
    () => juntarProblemas(alertas.data?.alertas ?? [], estado.data?.maquinas ?? []),
    [alertas.data, estado.data],
  );
  const nuevos = todos.filter((p) => !vistos.includes(p.firma));
  const yaVistos = todos.filter((p) => vistos.includes(p.firma));

  return {
    cargando: alertas.isPending || estado.isPending,
    error: alertas.error,
    todos,
    nuevos,
    yaVistos,
    urgentes: nuevos.filter((p) => p.nivel === "urgente").length,
    marcar,
    desmarcar,
    podar,
  };
}
