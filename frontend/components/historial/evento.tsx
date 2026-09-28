import Link from "next/link";

import type { Evento } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Un evento del historial, leído como texto.
 *
 * Vive acá y no en la página del historial porque desde el Panel v2 lo usa
 * también el detalle de cada máquina (su pestaña "Historial").
 */

/** Los nombres técnicos no se le muestran a nadie. */
export const QUE: Record<string, string> = {
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

export function FilaDeEvento({ evento }: { evento: Evento }) {
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
            className="text-accion-tinta underline-offset-2 hover:underline"
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
