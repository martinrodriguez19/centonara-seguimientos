import type { Nivel } from "@/components/ui/estado";
import type { Alerta, Corrida, Maquina } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Lo que el panel calcula a partir de lo que ya devuelve el backend.
 *
 * ⚠️ **Nada de esto va en `lib/panel.ts`.** Ese archivo lo lee
 * `backend/tests/test_contrato_panel.py` y compara cada `export type` con la
 * respuesta real de un endpoint. Un tipo que no sale de ningún endpoint —el uso
 * de hoy de una máquina, los borradores por día— pondría ese test en rojo. Por
 * eso vive acá (Panel v2, sin tocar el backend).
 *
 * Son funciones puras: se prueban sin red en `tests/derivados.test.ts`.
 */

export const ZONA = "America/Argentina/Buenos_Aires";

/** "2026-09-28" en hora argentina. `en-CA` es el locale que ya formatea así. */
export function diaArgentino(fecha: Date | string): string {
  const d = typeof fecha === "string" ? new Date(fecha) : fecha;
  return d.toLocaleDateString("en-CA", { timeZone: ZONA });
}

/** "hace instantes", "hace 3 min", "hace 2 h", "hace 4 días". */
export function haceCuanto(iso: string | null, ahora: number = Date.now()): string {
  if (!iso) return textos.maquina.nunca;
  const segundos = Math.floor((ahora - new Date(iso).getTime()) / 1000);
  if (segundos < 60) return "hace instantes";
  const minutos = Math.floor(segundos / 60);
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;
  const dias = Math.floor(horas / 24);
  return `hace ${dias} ${dias === 1 ? "día" : "días"}`;
}

/**
 * Cómo está una máquina, en una palabra y un nivel.
 *
 * El orden de las comprobaciones es el orden en que le importan a quien mira:
 * primero si está frenada, después si está rota, después si está viva.
 */
export function situacion(maquina: Maquina): { texto: string; nivel: Nivel } {
  if (!maquina.activo) return { texto: textos.maquina.inactiva, nivel: "neutro" };
  if (maquina.pausada) return { texto: textos.maquina.pausada, nivel: "neutro" };
  if (!maquina.online) return { texto: textos.maquina.offline, nivel: "critico" };
  if (maquina.chequeos_fallando.length > 0) {
    return { texto: textos.maquina.degradada, nivel: "atencion" };
  }
  return { texto: textos.maquina.online, nivel: "ok" };
}

/** Los chips chicos de la tarjeta: lo que hoy eran avisos grandes. */
export function chipsDeMaquina(maquina: Maquina): { texto: string; nivel: Nivel }[] {
  const chips: { texto: string; nivel: Nivel }[] = [];
  if (maquina.chequeos_fallando.length > 0) {
    chips.push({
      texto: textos.maquinas.chequeosFallando(maquina.chequeos_fallando.length),
      nivel: "atencion",
    });
  }
  if (maquina.activo && !maquina.puede_enviar) {
    chips.push({ texto: textos.maquinas.sinConsentimiento, nivel: "neutro" });
  }
  if (maquina.actualizada === false) {
    chips.push({ texto: textos.maquinas.atrasada, nivel: "atencion" });
  }
  if (maquina.modo_agente === "simulado") {
    chips.push({ texto: textos.maquinas.simulado, nivel: "atencion" });
  }
  return chips;
}

// ---------------------------------------------------------------------------
// Errores y avisos
// ---------------------------------------------------------------------------

/**
 * Una cosa para revisar: una alerta del backend o un problema de una máquina.
 *
 * `firma` es lo que se recuerda al apretar "Ya lo vi". Lleva el detalle
 * adentro a propósito: si la misma alerta vuelve con otro número ("5 envíos
 * fallaron" en vez de "3"), es otra cosa y tiene que volver a verse.
 */
export type Problema = {
  firma: string;
  nivel: "urgente" | "aviso";
  codigo: string;
  maquina: string | null;
  titulo: string;
  detalle: string;
  accion: string;
  corrida_id: string | null;
};

const firmaDe = (p: Omit<Problema, "firma">) =>
  [p.codigo, p.maquina ?? "", p.corrida_id ?? "", p.titulo, p.detalle].join("|");

/**
 * Las alertas del backend y los problemas de cada máquina, en una sola lista.
 *
 * Los de máquina son los que el backend **no** convierte en alerta pero la
 * tarjeta mostraba como aviso grande: sin consentimiento y modo simulado.
 *
 * ⚠️ "Sin conexión" **no** está a propósito. El backend no alerta por una Mac
 * apagada sin trabajo esperando —"una Mac apagada no es noticia"—, y sumarla
 * acá sería el ruido que el Panel v2 vino a sacar. Con trabajo esperando, el
 * backend ya manda `maquina_caida`. El punto rojo de la tarjeta alcanza.
 *
 * Urgentes primero; dentro de cada nivel, el orden del backend.
 */
export function juntarProblemas(alertas: Alerta[], maquinas: Maquina[]): Problema[] {
  const lista: Problema[] = alertas.map((a) => {
    const base = {
      nivel: a.nivel,
      codigo: a.codigo,
      maquina: a.maquina ?? null,
      titulo: a.titulo,
      detalle: a.detalle,
      accion: a.accion,
      corrida_id: a.corrida_id,
    };
    return { ...base, firma: firmaDe(base) };
  });

  for (const m of maquinas) {
    const extras: Omit<Problema, "firma">[] = [];
    const comun = { nivel: "aviso" as const, maquina: m.maquina, corrida_id: null };

    if (m.activo && !m.puede_enviar) {
      extras.push({
        ...comun,
        codigo: "sin_consentimiento",
        titulo: textos.errores.sinConsentimiento(m.nombre),
        detalle: textos.errores.sinConsentimientoDetalle,
        accion: textos.errores.sinConsentimientoAccion,
      });
    }
    if (m.modo_agente === "simulado") {
      extras.push({
        ...comun,
        codigo: "modo_simulado",
        titulo: textos.errores.simulado(m.nombre),
        detalle: textos.errores.simuladoDetalle,
        accion: textos.errores.simuladoAccion,
      });
    }
    for (const e of extras) lista.push({ ...e, firma: firmaDe(e) });
  }

  const orden = { urgente: 0, aviso: 1 } as const;
  // `sort` es estable: dentro de cada nivel queda el orden de arriba.
  return lista.sort((a, b) => orden[a.nivel] - orden[b.nivel]);
}

// ---------------------------------------------------------------------------
// Corridas y tandas
// ---------------------------------------------------------------------------

type Tanda = Corrida["tandas"][number];

/** Sólo las generaciones: los diagnósticos no tienen tandas ni costo. */
export const generaciones = (corridas: Corrida[]) => corridas.filter((c) => c.tipo === "generacion");

/** Las generaciones de hoy, en hora argentina. */
export function deHoy(corridas: Corrida[], ahora: Date = new Date()): Corrida[] {
  const hoy = diaArgentino(ahora);
  return generaciones(corridas).filter((c) => diaArgentino(c.creada_en) === hoy);
}

/** Las últimas generaciones en las que participó una máquina. */
export const deLaMaquina = (corridas: Corrida[], maquina: string, cuantas = 20) =>
  generaciones(corridas)
    .filter((c) => c.maquinas.includes(maquina))
    .slice(0, cuantas);

/** Las corridas creadas dentro de los últimos `dias`, contando hoy. */
export function delPeriodo(corridas: Corrida[], dias: number, ahora: Date = new Date()): Corrida[] {
  const desde = ahora.getTime() - dias * 24 * 60 * 60 * 1000;
  return corridas.filter((c) => new Date(c.creada_en).getTime() >= desde);
}

/** Los borradores que dejó una máquina hoy (hora argentina), sumando corridas. */
export function dejadosHoy(corridas: Corrida[], maquina: string, ahora: Date = new Date()): number {
  const hoy = diaArgentino(ahora);
  return corridas
    .filter((c) => diaArgentino(c.creada_en) === hoy)
    .flatMap((c) => c.tandas ?? [])
    .filter((t) => t.maquina === maquina)
    .reduce((suma, t) => suma + (t.dejados ?? 0), 0);
}

/** Los borradores de todas las máquinas hoy. */
export function dejadosHoyTotal(corridas: Corrida[], ahora: Date = new Date()): number {
  const hoy = diaArgentino(ahora);
  return corridas
    .filter((c) => diaArgentino(c.creada_en) === hoy)
    .flatMap((c) => c.tandas ?? [])
    .reduce((suma, t) => suma + (t.dejados ?? 0), 0);
}

/**
 * Lo que hizo una máquina, corrida por corrida.
 *
 * Una máquina puede tener varias tandas en una corrida (D44): se suman en una
 * fila, y el error y el corte que se muestran son los de la última.
 */
export function actividadDe(
  corridas: Corrida[],
  maquina: string,
): { corrida: Corrida; tandas: number; pedidos: number; dejados: number; salteados: number; vetados: number; motivos: Record<string, number>; corte: string | null; error: Tanda["error"] }[] {
  const filas = [];
  for (const corrida of corridas) {
    const propias = (corrida.tandas ?? []).filter((t) => t.maquina === maquina);
    if (propias.length === 0) continue;
    const ultima = propias[propias.length - 1];
    filas.push({
      corrida,
      tandas: propias.length,
      pedidos: propias.reduce((s, t) => s + (t.pedidos ?? 0), 0),
      dejados: propias.reduce((s, t) => s + (t.dejados ?? 0), 0),
      salteados: propias.reduce((s, t) => s + (t.salteados ?? 0), 0),
      vetados: propias.reduce((s, t) => s + (t.vetados ?? 0), 0),
      motivos: sumarMotivos(propias),
      corte: ultima.corte ?? null,
      error: propias.find((t) => t.error)?.error ?? null,
    });
  }
  return filas;
}

function sumarMotivos(tandas: Tanda[]): Record<string, number> {
  const total: Record<string, number> = {};
  for (const t of tandas) {
    for (const [motivo, cuantos] of Object.entries(t.motivos ?? {})) {
      total[motivo] = (total[motivo] ?? 0) + cuantos;
    }
  }
  return total;
}

/** Los motivos de salteo de todas las corridas, de más a menos. */
export function motivosDeSalteo(corridas: Corrida[]): [string, number][] {
  const total = sumarMotivos(corridas.flatMap((c) => c.tandas ?? []));
  return Object.entries(total)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
}

/**
 * Borradores dejados por día, con los días sin nada en cero.
 *
 * Los ceros importan: un gráfico que salta del lunes al jueves esconde que el
 * martes y el miércoles no corrió nada, que es justamente lo que hay que ver.
 */
export function dejadosPorDia(
  corridas: Corrida[],
  dias: number,
  ahora: Date = new Date(),
): { dia: string; valor: number }[] {
  const porDia = new Map<string, number>();
  for (let i = dias - 1; i >= 0; i--) {
    porDia.set(diaArgentino(new Date(ahora.getTime() - i * 24 * 60 * 60 * 1000)), 0);
  }
  for (const c of corridas) {
    const dia = diaArgentino(c.creada_en);
    if (!porDia.has(dia)) continue;
    const dejados = (c.tandas ?? []).reduce((s, t) => s + (t.dejados ?? 0), 0);
    porDia.set(dia, (porDia.get(dia) ?? 0) + dejados);
  }
  return [...porDia.entries()].map(([dia, valor]) => ({ dia, valor }));
}

/** Por máquina: dejados, salteados y tandas con error. De más a menos dejados. */
export function porMaquina(
  corridas: Corrida[],
): { maquina: string; dejados: number; salteados: number; conError: number; tandas: number }[] {
  const filas = new Map<string, { maquina: string; dejados: number; salteados: number; conError: number; tandas: number }>();
  for (const t of corridas.flatMap((c) => c.tandas ?? [])) {
    const fila = filas.get(t.maquina) ?? { maquina: t.maquina, dejados: 0, salteados: 0, conError: 0, tandas: 0 };
    fila.dejados += t.dejados ?? 0;
    fila.salteados += t.salteados ?? 0;
    fila.conError += t.error ? 1 : 0;
    fila.tandas += 1;
    filas.set(t.maquina, fila);
  }
  return [...filas.values()].sort((a, b) => b.dejados - a.dejados);
}

/** El costo de cada corrida, de la más vieja a la más nueva. */
export function costoPorCorrida(corridas: Corrida[]): { dia: string; valor: number; id: string }[] {
  return [...corridas]
    .sort((a, b) => new Date(a.creada_en).getTime() - new Date(b.creada_en).getTime())
    .map((c) => ({ id: c.id, dia: diaArgentino(c.creada_en), valor: c.costo_usd ?? 0 }));
}

/** "28/09" para un eje. */
export function diaCorto(dia: string): string {
  const [, mes, d] = dia.split("-");
  return `${d}/${mes}`;
}
