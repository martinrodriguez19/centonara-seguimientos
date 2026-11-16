"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useAvisos } from "@/components/ui/avisos-flotantes";
import { Button } from "@/components/ui/button";
import { Campo } from "@/components/ui/campo";
import { Aviso, Pildora, type Nivel } from "@/components/ui/estado";
import { haceCuanto } from "@/lib/derivados";
import {
  editarMaquina,
  reconectarMaquina,
  type EstadoDeSesion,
  type Maquina,
  type NombreDeSesion,
} from "@/lib/panel";
import { textos } from "@/lib/textos";

const t = textos.sesiones;

/**
 * Las sesiones de una máquina, para el dueño (D69-D73).
 *
 * Lo que la página pública resume en dos renglones, acá va entero: las cuatro
 * sesiones con quién dijo qué y desde cuándo, la línea de tiempo de los
 * cambios, la línea vinculada (D72), el token (D73) y los mismos botones de
 * reconectar que tiene el vendedor. "Según el disco" se distingue de "según un
 * trabajo" porque no pesan lo mismo: sólo lo segundo saca a la máquina de una
 * corrida (D69.4).
 */

const NIVEL: Record<EstadoDeSesion, Nivel> = { ok: "ok", caida: "critico", desconocido: "neutro" };

const ORDEN: NombreDeSesion[] = ["whatsapp", "claude_extension", "claude_cli", "whatsapp_motor"];

const fecha = (iso: string) =>
  new Date(iso).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });

/** Un semáforo con su nombre: "WhatsApp · Conectado". */
export function Semaforo({ nombre, estado }: { nombre: string; estado: EstadoDeSesion }) {
  return (
    <Pildora nivel={NIVEL[estado] ?? "neutro"}>
      {nombre} · {t.estados[estado] ?? estado}
    </Pildora>
  );
}

/** El cartel rojo de D72, para arriba del detalle: es lo primero que hay que ver. */
export function AvisoDeLinea({ maquina }: { maquina: Maquina }) {
  if (!maquina.linea_equivocada) return null;
  return (
    <Aviso nivel="critico" titulo={t.lineaEquivocadaTitulo} accion={t.lineaEquivocadaAccion}>
      {t.lineaEquivocada(maquina.numero_vinculado ?? "?", maquina.telefono_linea ?? "?")}
    </Aviso>
  );
}

export function Sesiones({ maquina }: { maquina: Maquina }) {
  const sesiones = maquina.sesiones ?? {};
  const historial = maquina.sesiones_historial ?? [];

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t.bajada}</p>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border bg-card px-5 sombra-suave">
          <h2 className="border-b py-3 text-sm font-semibold">{t.titulo}</h2>
          <ul className="divide-y">
            {ORDEN.map((nombre) => {
              const sesion = sesiones[nombre];
              return (
                <li key={nombre} className="space-y-1 py-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">{t.nombres[nombre] ?? nombre}</span>
                    {sesion ? (
                      <Pildora nivel={NIVEL[sesion.estado] ?? "neutro"}>
                        {t.estados[sesion.estado] ?? sesion.estado}
                      </Pildora>
                    ) : (
                      <span className="text-muted-foreground">{t.sinReporte}</span>
                    )}
                  </div>
                  {sesion && (
                    <p className="text-xs text-muted-foreground">
                      <span title={fecha(sesion.desde)}>{t.desde(haceCuanto(sesion.desde))}</span>
                      {sesion.fuente && <> · {t.segun(t.fuentes[sesion.fuente] ?? sesion.fuente)}</>}
                    </p>
                  )}
                  {sesion?.detalle && <p className="text-xs break-words">{sesion.detalle}</p>}
                </li>
              );
            })}
          </ul>
        </section>

        <div className="space-y-4">
          {/* Con `key`: cuando el backend devuelve el número normalizado, el
              campo vuelve a mostrar el guardado y no lo que se tipeó. */}
          <Linea key={maquina.telefono_linea ?? ""} maquina={maquina} />
          <Reconectar maquina={maquina} />
        </div>
      </div>

      <section className="space-y-2">
        <div>
          <h2 className="text-sm font-semibold">{t.historial}</h2>
          <p className="text-xs text-muted-foreground">{t.historialAyuda}</p>
        </div>
        {historial.length === 0 ? (
          <p className="rounded-xl border border-dashed bg-card p-6 text-center text-sm text-muted-foreground">
            {t.sinHistorial}
          </p>
        ) : (
          <ol className="divide-y rounded-xl border bg-card sombra-suave">
            {historial.map((cambio, i) => (
              <li key={`${cambio.cuando}-${cambio.sesion}-${i}`} className="grid gap-1 px-4 py-3 text-sm sm:grid-cols-[9rem_1fr]">
                <span className="font-mono text-xs text-muted-foreground tabular-nums">{fecha(cambio.cuando)}</span>
                <span className="min-w-0 space-y-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{t.nombres[cambio.sesion] ?? cambio.sesion}</span>
                    {cambio.antes && (
                      <>
                        <span className="text-muted-foreground">{t.estados[cambio.antes] ?? cambio.antes}</span>
                        <span aria-hidden className="text-muted-foreground">
                          →
                        </span>
                      </>
                    )}
                    <Pildora nivel={NIVEL[cambio.estado] ?? "neutro"}>{t.estados[cambio.estado] ?? cambio.estado}</Pildora>
                    {cambio.fuente && (
                      <span className="text-xs text-muted-foreground">{t.segun(t.fuentes[cambio.fuente] ?? cambio.fuente)}</span>
                    )}
                  </span>
                  {cambio.detalle && <span className="block text-xs break-words">{cambio.detalle}</span>}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

/**
 * El número de la línea (D72), con el vinculado al lado.
 *
 * Se guarda con el botón y no por tecla: un número a medio escribir no es un
 * número, y el backend lo rechaza (422) si no lo puede pasar a E.164.
 */
function Linea({ maquina }: { maquina: Maquina }) {
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();
  const actual = maquina.telefono_linea ?? "";
  const [borrador, setBorrador] = useState(actual);

  const guardar = useMutation({
    mutationFn: (telefono_linea: string) => editarMaquina(maquina.maquina, { telefono_linea }),
    onSuccess: (_, numero) => avisar(numero ? t.lineaGuardada : t.lineaBorrada),
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["estado"] }),
  });

  const tokenTexto =
    maquina.claude_token_al_dia === true
      ? t.tokenAlDia
      : maquina.claude_token_al_dia === false
        ? t.tokenOtro
        : t.tokenSinCargar;

  return (
    <section className="space-y-3 rounded-xl border bg-card p-5 sombra-suave">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-0 flex-1">
          <Campo
            etiqueta={t.linea}
            ayuda={t.lineaAyuda}
            placeholder="+54 9 11 …"
            inputMode="tel"
            value={borrador}
            onChange={(evento) => setBorrador(evento.target.value)}
            error={guardar.isError ? guardar.error.message : null}
          />
        </div>
        <Button
          size="sm"
          className="mb-5"
          disabled={guardar.isPending || borrador.trim() === actual}
          onClick={() => guardar.mutate(borrador.trim())}
        >
          {t.lineaGuardar}
        </Button>
      </div>
      <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-2 text-sm">
        <dt className="text-muted-foreground">{t.vinculado}</dt>
        <dd className={maquina.linea_equivocada ? "font-mono text-critico" : "font-mono"}>
          {maquina.numero_vinculado ? `+${maquina.numero_vinculado}` : <span className="font-sans text-muted-foreground">{t.vinculadoNoSe}</span>}
        </dd>
        <dt className="text-muted-foreground">{t.token}</dt>
        <dd>
          {maquina.claude_token_al_dia === false ? <Pildora nivel="atencion">{tokenTexto}</Pildora> : tokenTexto}
        </dd>
      </dl>
    </section>
  );
}

/** Los botones del vendedor, apretados por el dueño (D70). */
function Reconectar({ maquina }: { maquina: Maquina }) {
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();
  const pedir = useMutation({
    mutationFn: (tipo: "whatsapp" | "claude" | "verificar") => reconectarMaquina(maquina.maquina, tipo),
    onSuccess: () => avisar(t.avisoPedido),
    // El 429 trae "ya se pidió hace poco; probá de nuevo en N s": dice más que
    // el aviso genérico.
    onError: (error) => avisar(error.message || t.avisoFallo, "critico"),
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["estado"] }),
  });

  return (
    <section className="space-y-3 rounded-xl border bg-card p-5 sombra-suave">
      <div>
        <h2 className="text-sm font-semibold">{t.reconectar}</h2>
        <p className="text-xs text-muted-foreground">{t.reconectarAyuda}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={pedir.isPending} onClick={() => pedir.mutate("whatsapp")}>
          {t.reconectarWhatsapp}
        </Button>
        <Button size="sm" variant="outline" disabled={pedir.isPending} onClick={() => pedir.mutate("claude")}>
          {t.reconectarClaude}
        </Button>
        <Button size="sm" variant="outline" disabled={pedir.isPending} onClick={() => pedir.mutate("verificar")}>
          {t.verificar}
        </Button>
      </div>
    </section>
  );
}
