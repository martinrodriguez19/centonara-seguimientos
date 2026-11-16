"use client";

import { Check } from "lucide-react";
import { useEffect, useState } from "react";

import { BotonGrande } from "@/components/conectar/tarjeta";
import { Aviso } from "@/components/ui/estado";
import { pasoDeReconexion, type ConexionPublica, type Pedido } from "@/lib/conectar";
import { textos } from "@/lib/textos";

const t = textos.conectar;

/** Cuánto se queda el "¡Listo!" antes de volver solo a la lista. */
const SEGUNDOS_LISTO = 4;

/**
 * Los pasos de una reconexión, para una computadora (D71, plan §2.2 y §2.3).
 *
 * La pantalla entera es esto: mientras el vendedor está escaneando no tiene
 * que ver a los demás. El paso sale de `pasoDeReconexion`, que mira lo que
 * dice el servidor cada cinco segundos; acá sólo se dibuja.
 *
 * El reloj propio (`ahora`) hace falta porque el "no se completó" depende del
 * tiempo y no de los datos: si el servidor contesta siempre lo mismo, TanStack
 * no vuelve a dibujar, y los cinco minutos no llegarían nunca.
 */
export function VistaDePasos({
  pedido,
  conexion,
  pedirCodigoA,
  aviso,
  ocupado,
  onVerificar,
  onReintentar,
  onVolver,
}: {
  pedido: Pedido;
  conexion: ConexionPublica | undefined;
  pedirCodigoA: string;
  /** Un 429 o un pedido que no salió, ya en palabras para el vendedor. */
  aviso: string | null;
  ocupado: boolean;
  onVerificar: () => void;
  onReintentar: () => void;
  onVolver: () => void;
}) {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    const reloj = setInterval(() => setAhora(Date.now()), 5000);
    return () => clearInterval(reloj);
  }, []);

  const paso = pasoDeReconexion(pedido, conexion, ahora);

  useEffect(() => {
    if (paso !== "listo") return;
    const volver = setTimeout(onVolver, SEGUNDOS_LISTO * 1000);
    return () => clearTimeout(volver);
  }, [paso, onVolver]);

  const nombre = conexion?.nombre ?? "";
  const esWhatsapp = pedido.tipo === "whatsapp";
  const titulo = esWhatsapp ? t.whatsappTitulo(nombre) : t.claudeTitulo(nombre);

  if (paso === "listo") {
    return (
      <section aria-label={titulo} className="space-y-6 rounded-2xl border bg-card p-6 text-center sombra-suave">
        <span className="mx-auto grid size-20 place-items-center rounded-full bg-ok-suave text-ok">
          <Check className="size-10" aria-hidden />
        </span>
        <p role="status" className="text-2xl font-semibold text-ok">
          {t.listo}
        </p>
        <BotonGrande variant="outline" onClick={onVolver}>
          {t.volver}
        </BotonGrande>
      </section>
    );
  }

  const pasos: readonly string[] = esWhatsapp ? t.whatsappPasos : t.claudePasos(pedirCodigoA);

  return (
    <section aria-label={titulo} className="space-y-5 rounded-2xl border bg-card p-5 sombra-suave">
      <h2 className="text-2xl font-semibold">{titulo}</h2>

      {aviso && <Aviso nivel="atencion" titulo={aviso} />}

      {paso === "vencida" || paso === "no_se_completo" ? (
        <>
          <Aviso nivel="critico" titulo={paso === "vencida" ? t.vencida : t.noSeCompleto} />
          <BotonGrande disabled={ocupado} onClick={onReintentar}>
            {ocupado ? t.pidiendo : t.probarDeNuevo}
          </BotonGrande>
        </>
      ) : paso === "revisando" ? (
        <div role="status" className="space-y-1 rounded-xl bg-muted/60 p-5 text-center">
          <p className="text-2xl font-semibold">{t.revisando}</p>
          <p className="text-lg text-muted-foreground">{t.revisandoDetalle}</p>
        </div>
      ) : (
        <>
          {paso === "todavia_no" && <Aviso nivel="atencion" titulo={t.todaviaNo} />}
          <ol className="space-y-4">
            {pasos.map((texto, i) => (
              <li key={i} className="flex gap-3 text-lg leading-snug">
                <span
                  className="grid size-9 shrink-0 place-items-center rounded-full bg-foreground text-lg font-semibold text-background"
                  aria-hidden
                >
                  {i + 1}
                </span>
                <span className="pt-1">{texto}</span>
              </li>
            ))}
          </ol>
          {esWhatsapp && <p className="text-base text-muted-foreground">{t.whatsappMaximo}</p>}
          <BotonGrande disabled={ocupado} onClick={onVerificar}>
            {esWhatsapp ? t.yaEscanee : t.yaTermine}
          </BotonGrande>
        </>
      )}

      <BotonGrande variant="outline" onClick={onVolver}>
        {t.volver}
      </BotonGrande>
    </section>
  );
}
