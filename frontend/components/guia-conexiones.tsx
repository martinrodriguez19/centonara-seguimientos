"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, CircleDashed, Copy, ExternalLink, PlugZap } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useConfiguracion } from "@/lib/consultas";
import { traerTokenClaude, type Maquina } from "@/lib/panel";
import { textos } from "@/lib/textos";

const t = textos.guiaConexiones;

/**
 * La guía de las conexiones, en el inicio (D69-D73).
 *
 * El dueño preguntó lo obvio: "¿el vendedor ve el botón de Claude, o era un
 * token?". Son dos Claude distintos y se manejan distinto, y eso tiene que
 * estar escrito donde se mira todos los días, no en un documento.
 *
 * Arriba, lo que falta configurar —con el estado real, no una lista para
 * tildar a mano—; abajo, qué hacer en cada caso. Se abre sola mientras falte
 * algo o haya una conexión caída; si todo anda, queda plegada en una línea.
 */
export function GuiaConexiones({ maquinas }: { maquinas: Maquina[] }) {
  const token = useQuery({ queryKey: ["token-claude"], queryFn: traerTokenClaude });
  const config = useConfiguracion();

  const activas = maquinas.filter((m) => m.activo);
  const caidas = activas.filter(
    (m) => m.semaforos?.whatsapp === "caida" || m.semaforos?.claude === "caida",
  ).length;

  const tokenListo = Boolean(token.data?.cargado);
  const alDia = token.data?.maquinas_al_dia ?? 0;
  const conToken = token.data?.maquinas_activas ?? 0;
  const tokenAlDia = tokenListo && alDia >= conToken;
  const quien = config.data?.cuenta_claude_codigo_quien ?? "";
  const cuentaLista = Boolean(config.data?.cuenta_claude_mail && quien);
  const falta = !tokenListo || !cuentaLista;

  return (
    <details
      open={falta || caidas > 0 || undefined}
      className="group rounded-xl bg-card text-sm ring-1 ring-border sombra-suave"
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 font-medium">
        <PlugZap className="size-4 text-accion-tinta" aria-hidden />
        {t.titulo}
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {falta ? t.faltaConfigurar : caidas > 0 ? t.caidas(caidas) : t.todoListo}
        </span>
      </summary>

      <div className="grid gap-5 border-t px-4 py-4">
        <section className="grid gap-2">
          <h3 className="font-medium">{t.configurarTitulo}</h3>
          <ol className="grid gap-2">
            <Paso
              hecho={tokenListo}
              titulo={t.paso1}
              detalle={
                tokenListo
                  ? t.paso1Hecho(alDia, conToken)
                  : t.paso1Falta
              }
              aviso={tokenListo && !tokenAlDia ? t.paso1Repartiendo : undefined}
              href="/config/sistema"
              enlace={t.irASistema}
            />
            <Paso
              hecho={cuentaLista}
              titulo={t.paso2}
              detalle={cuentaLista ? t.paso2Hecho(quien) : t.paso2Falta}
              href="/config/sistema"
              enlace={t.irASistema}
            />
            <PasoEnlace />
          </ol>
        </section>

        <section className="grid gap-3">
          <h3 className="font-medium">{t.dosClaudeTitulo}</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <Caso titulo={t.extensionTitulo} lineas={t.extension} />
            <Caso titulo={t.claudeCodeTitulo} lineas={t.claudeCode} />
          </div>
        </section>

        <section className="grid gap-3">
          <h3 className="font-medium">{t.cuandoSeCaeTitulo}</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <Caso titulo={t.whatsappTitulo} lineas={t.whatsapp} />
            <Caso titulo={t.claudeCaeTitulo} lineas={t.claudeCae} />
          </div>
        </section>

        <p className="text-muted-foreground">{t.alertas}</p>
      </div>
    </details>
  );
}

function Paso({
  hecho,
  titulo,
  detalle,
  aviso,
  href,
  enlace,
}: {
  hecho: boolean;
  titulo: string;
  detalle: string;
  aviso?: string;
  href?: string;
  enlace?: string;
}) {
  return (
    <li className="flex items-start gap-2.5">
      {hecho ? (
        <Check className="mt-0.5 size-4 shrink-0 text-ok" aria-label={t.hecho} />
      ) : (
        <CircleDashed className="mt-0.5 size-4 shrink-0 text-atencion" aria-label={t.pendiente} />
      )}
      <div className="grid gap-0.5">
        <span className="font-medium">{titulo}</span>
        <span className="text-muted-foreground">{detalle}</span>
        {aviso && <span className="text-atencion">{aviso}</span>}
        {href && enlace && !hecho && (
          <Link href={href} className="font-medium text-accion-tinta hover:underline">
            {enlace}
          </Link>
        )}
      </div>
    </li>
  );
}

/** El tercer paso: el link que se les manda a los vendedores, con botón para copiarlo. */
function PasoEnlace() {
  const [url, setUrl] = useState("/conectar");
  const [copiado, setCopiado] = useState(false);

  //  El dominio sale de donde está abierto el panel: el mismo link funciona
  //  con el dominio propio y con el de Render.
  useEffect(() => setUrl(`${window.location.origin}/conectar`), []);

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      setCopiado(false);
    }
  };

  return (
    <li className="flex items-start gap-2.5">
      <PlugZap className="mt-0.5 size-4 shrink-0 text-accion-tinta" aria-hidden />
      <div className="grid gap-1">
        <span className="font-medium">{t.paso3}</span>
        <span className="text-muted-foreground">{t.paso3Detalle}</span>
        <div className="flex flex-wrap items-center gap-2">
          <code className="rounded-md bg-muted px-2 py-1 font-mono text-xs">{url}</code>
          <button
            type="button"
            onClick={() => void copiar()}
            className="inline-flex items-center gap-1 text-xs font-medium text-accion-tinta hover:underline"
          >
            <Copy className="size-3.5" aria-hidden />
            {copiado ? t.copiado : t.copiar}
          </button>
          <a
            href="/conectar"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs font-medium text-accion-tinta hover:underline"
          >
            <ExternalLink className="size-3.5" aria-hidden />
            {t.abrir}
          </a>
        </div>
      </div>
    </li>
  );
}

function Caso({ titulo, lineas }: { titulo: string; lineas: readonly string[] }) {
  return (
    <div className="grid content-start gap-1.5 rounded-lg bg-muted/50 p-3">
      <span className="font-medium">{titulo}</span>
      <ul className="grid list-disc gap-1 pl-4 text-muted-foreground">
        {lineas.map((linea) => (
          <li key={linea}>{linea}</li>
        ))}
      </ul>
    </div>
  );
}
