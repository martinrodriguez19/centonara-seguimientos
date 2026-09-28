"use client";

import { useState } from "react";

import { esPaseUnico, Fila, Numero, Tarjeta, useGuardarConfiguracion } from "@/components/config/base";
import { Button } from "@/components/ui/button";
import { AreaDeTexto } from "@/components/ui/campo";
import { Aviso } from "@/components/ui/estado";
import { Interruptor } from "@/components/ui/interruptor";
import { Opciones } from "@/components/ui/opciones";
import type { Configuracion, EtiquetaContacto } from "@/lib/panel";

/**
 * Mensajes: cómo se dejan, cuántos, y qué dicen.
 */
export function SeccionMensajes({ config }: { config: Configuracion }) {
  const { guardar, guardando, error } = useGuardarConfiguracion();
  const paseUnico = esPaseUnico(config);
  const postCompra = config.mensaje_post_compra ?? true;

  return (
    <>
      <Tarjeta titulo="Cómo se dejan los borradores">
        <Fila
          titulo="Circuito"
          ayuda={
            {
              playwright: "Se leen los chats, se redacta aparte y otro navegador deja cada borrador.",
              extension: "La extensión lee cada chat y deja el borrador ahí mismo, en una sola pasada.",
              extension_con_respaldo: "El pase único, y si una máquina agota los reintentos, cae al circuito de siempre.",
            }[config.modo_borrador ?? "playwright"]
          }
          queHace={
            <>
              <p>
                <strong>Circuito de siempre</strong>: se leen los chats, se redacta aparte y otro navegador vuelve a
                abrir cada chat para dejar el borrador.
              </p>
              <p>
                <strong>Pase único</strong>: la extensión lee cada chat y deja el borrador ahí mismo — sin segundo
                navegador y sin volver a buscar el chat. Es el que habilita el envío automático.
              </p>
              <p>
                <strong>Con respaldo</strong>: el pase único, y si a una máquina se le agotan los reintentos, esa
                máquina cae al circuito de siempre.
              </p>
            </>
          }
        >
          <Opciones
            etiqueta="Cómo se dejan los borradores"
            valor={config.modo_borrador ?? "playwright"}
            deshabilitado={guardando}
            opciones={[
              { valor: "playwright", texto: "Circuito de siempre" },
              { valor: "extension", texto: "Pase único" },
              { valor: "extension_con_respaldo", texto: "Pase único con respaldo" },
            ]}
            onCambiar={(modo_borrador) => guardar({ modo_borrador })}
          />
        </Fila>
      </Tarjeta>

      {paseUnico && <Volumen config={config} />}

      <Tarjeta titulo="Qué dicen">
        <Fila
          titulo="Indicaciones para redactar"
          ayuda="Qué vende la empresa, promociones vigentes, qué destacar, qué no mencionar, con qué tono."
          queHace={
            <>
              <p>
                Lo que escribas acá manda sobre lo que dicen los mensajes y cómo lo dicen. Cuanto más concreto, más
                concretos salen los borradores. Cada redacción usa la versión del momento.
              </p>
              <p>
                Dos cosas no las cambia ni pidiéndolo: el sistema no inventa precios, fechas ni plazos que no estén
                acá o en la conversación, y no deja huecos sin completar en el texto.
              </p>
            </>
          }
        >
          <ContextoEmpresa
            key={config.contexto_empresa ?? ""}
            valor={config.contexto_empresa ?? ""}
            guardando={guardando}
            onGuardar={(contexto_empresa) => guardar({ contexto_empresa })}
          />
        </Fila>

        <Fila
          titulo="Largo máximo del mensaje"
          ayuda="En caracteres."
          control={
            <Numero
              etiqueta="Largo máximo del mensaje"
              min={50}
              max={1000}
              valor={config.largo_maximo}
              guardando={guardando}
              onGuardar={(largo_maximo) => guardar({ largo_maximo })}
            />
          }
        />

        {paseUnico && (
          <Fila
            titulo="Escribirle a quien ya compró"
            ayuda={postCompra ? "Se le pregunta si le faltó algo." : "No se le escribe."}
            queHace="Si en el chat se ve que la compra ya se hizo —con nosotros o en otro lado— nunca se le pregunta por esa venta. Lo que se elige acá es si se le deja un mensaje de post-venta («te faltó algo?») o nada."
            control={
              <Interruptor
                prendido={postCompra}
                etiqueta="Escribirle a quien ya compró"
                deshabilitado={guardando}
                onCambiar={(mensaje_post_compra) => guardar({ mensaje_post_compra })}
              />
            }
          >
            {postCompra && (
              <PostVentaOfrecer
                key={config.post_venta_ofrecer ?? ""}
                valor={config.post_venta_ofrecer ?? ""}
                guardando={guardando}
                onGuardar={(post_venta_ofrecer) => guardar({ post_venta_ofrecer })}
              />
            )}
          </Fila>
        )}
      </Tarjeta>

      <Etiquetas
        key={JSON.stringify(config.etiquetas_contacto ?? [])}
        etiquetas={config.etiquetas_contacto ?? []}
        guardando={guardando}
        error={error}
        onGuardar={(etiquetas_contacto) => guardar({ etiquetas_contacto })}
      />
    </>
  );
}

/** Cuánto tarda una tanda del pase único, de punta a punta (`TIMEOUT_BORRADORES`, D44). */
const MINUTOS_POR_TANDA = 35;

/**
 * El volumen del pase único: cuántos borradores salen, y cuánto tarda eso.
 *
 * Los tres números que lo deciden no dicen nada por separado. El dueño piensa
 * "quiero veinte por día"; el sistema piensa en tandas, topes y minutos. Esto
 * hace la cuenta a la vista, con los valores puestos, y dice el tiempo.
 */
function Volumen({ config }: { config: Configuracion }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  const porDia = config.tope_diario_borradores ?? 20;
  const porTanda = config.chats_por_tanda ?? 8;
  const maxTandas = config.max_tandas_por_maquina ?? 6;
  const maxVisitas = config.max_visitas_por_tanda ?? 20;

  // El más chico de los tres manda, igual que en el backend.
  const porCorrida = Math.min(porDia, config.tope_por_corrida, maxTandas * porTanda);
  const tandas = Math.ceil(porCorrida / porTanda);
  const minutos = tandas * MINUTOS_POR_TANDA;
  // Que el techo de tandas sea el que corta es casi siempre un descuido.
  const cortaElTiempo = maxTandas * porTanda < Math.min(porDia, config.tope_por_corrida);

  return (
    <Tarjeta
      titulo="Cuántos borradores se dejan"
      bajada={
        <>
          Cada máquina deja hasta <strong className="font-mono tabular-nums">{porCorrida}</strong> por corrida, en{" "}
          <span className="font-mono tabular-nums">{tandas}</span> {tandas === 1 ? "tanda" : "tandas"}, y tarda{" "}
          <strong className="font-mono tabular-nums">hasta {minutos} min</strong>. Las máquinas trabajan en paralelo.
        </>
      }
    >
      <Fila
        titulo="Borradores por día, por máquina"
        ayuda="El número que manda: lo que cada vendedor encuentra en su WhatsApp al final del día."
        control={
          <Numero
            etiqueta="Borradores por día, por máquina"
            max={100}
            valor={porDia}
            guardando={guardando}
            onGuardar={(tope_diario_borradores) => guardar({ tope_diario_borradores })}
          />
        }
      />
      <Fila
        titulo="Borradores por tanda"
        ayuda="Ocho entra en el tiempo límite; más de doce no se puede."
        queHace="El pase trabaja de a tandas y reporta al terminar cada una."
        control={
          <Numero
            etiqueta="Borradores por tanda"
            max={12}
            valor={porTanda}
            guardando={guardando}
            onGuardar={(chats_por_tanda) => guardar({ chats_por_tanda })}
          />
        }
      />
      <Fila
        titulo="Chats abiertos por tanda"
        ayuda="Contando los que saltea."
        queHace="Hasta cuántos chats abre una tanda buscando sus borradores. Cuando llega, devuelve lo que tiene y sigue en la próxima."
        control={
          <Numero
            etiqueta="Chats abiertos por tanda"
            max={60}
            valor={maxVisitas}
            guardando={guardando}
            onGuardar={(max_visitas_por_tanda) => guardar({ max_visitas_por_tanda })}
          />
        }
      />
      <Fila
        titulo="Tandas por corrida"
        ayuda="El tope de tiempo: cada tanda es una pasada entera del modelo por el navegador."
        control={
          <Numero
            etiqueta="Tandas por corrida"
            max={12}
            valor={maxTandas}
            guardando={guardando}
            onGuardar={(max_tandas_por_maquina) => guardar({ max_tandas_por_maquina })}
          />
        }
      />
      {(maxVisitas < porTanda || cortaElTiempo) && (
        <div className="space-y-3 py-4">
          {maxVisitas < porTanda && (
            <Aviso nivel="atencion" titulo="Abre menos chats de los que tiene que llenar" className="p-3">
              Una tanda no puede dejar <span className="tabular-nums">{porTanda}</span> borradores abriendo{" "}
              <span className="tabular-nums">{maxVisitas}</span> chats. El sistema usa el más grande de los dos.
            </Aviso>
          )}
          {cortaElTiempo && (
            <Aviso
              nivel="atencion"
              titulo="Corta el tope de tandas, no el de borradores"
              className="p-3"
              accion={
                <>
                  Para llegar a <span className="tabular-nums">{porDia}</span> por día hacen falta{" "}
                  <span className="tabular-nums">{Math.ceil(porDia / porTanda)}</span> tandas — o tandas más grandes.
                </>
              }
            >
              Se dejan <span className="tabular-nums">{porCorrida}</span> por corrida aunque los otros dos topes
              permitan más.
            </Aviso>
          )}
        </div>
      )}
    </Tarjeta>
  );
}

/**
 * Las indicaciones del dueño sobre su empresa (D27, ampliado en D33).
 *
 * El contador avisa pasada la mitad del tope: este texto viaja en CADA
 * redacción y a partir de ahí empieza a pesar en la factura.
 */
function ContextoEmpresa({
  valor,
  guardando,
  onGuardar,
}: {
  valor: string;
  guardando: boolean;
  onGuardar: (texto: string) => void;
}) {
  const [borrador, setBorrador] = useState(valor);
  const LIMITE = 20000;
  const pesado = borrador.length > LIMITE / 2;

  return (
    <div className="space-y-2">
      <textarea
        rows={10}
        maxLength={LIMITE}
        aria-label="Indicaciones para redactar"
        className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        placeholder={
          "Ejemplo:\nSomos E-Ticketpro, vendemos entradas y gestión de eventos.\n" +
          "Productos: ticketera online, control de accesos, cashless.\n" +
          "Promo vigente: 20% de descuento en la primera fecha.\n" +
          "Tono: cercano y profesional, tuteo rioplatense.\n" +
          "No mencionar: precios de la competencia, plazos de instalación."
        }
        value={borrador}
        onChange={(evento) => setBorrador(evento.target.value)}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button size="sm" disabled={guardando || borrador === valor} onClick={() => onGuardar(borrador)}>
          Guardar indicaciones
        </Button>
        <span className="font-mono text-xs text-muted-foreground tabular-nums">
          {pesado && <span className="mr-2 font-sans">Cada mensaje lo lee entero.</span>}
          {borrador.length.toLocaleString("es-AR")} / {LIMITE.toLocaleString("es-AR")}
        </span>
      </div>
    </div>
  );
}

/** Qué ofrecerle a quien ya compró (D41). Vacío no cambia nada en el prompt. */
function PostVentaOfrecer({
  valor,
  guardando,
  onGuardar,
}: {
  valor: string;
  guardando: boolean;
  onGuardar: (texto: string) => void;
}) {
  const [borrador, setBorrador] = useState(valor);
  const LIMITE = 500;
  return (
    <div className="space-y-2">
      <AreaDeTexto
        etiqueta="Y ofrecerle algo (opcional)"
        ayuda="Vacío: sólo pregunta cómo le fue. Con texto, lo ofrece en la misma línea, con estas palabras. Nunca le vuelve a hablar de la venta que ya cerró."
        rows={3}
        maxLength={LIMITE}
        placeholder="Ejemplo: tenemos 10% en accesorios para lo que compró, hasta fin de mes."
        value={borrador}
        onChange={(evento) => setBorrador(evento.target.value)}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button size="sm" variant="outline" disabled={guardando || borrador === valor} onClick={() => onGuardar(borrador.trim())}>
          {borrador.trim() ? "Guardar la oferta" : "Guardar sin oferta"}
        </Button>
        <span className="font-mono text-xs text-muted-foreground tabular-nums">
          {borrador.length} / {LIMITE}
        </span>
      </div>
    </div>
  );
}

/**
 * Las etiquetas del nombre del contacto (D50).
 *
 * Los vendedores agendan a algunos contactos con una palabra en mayúsculas al
 * final del nombre: qué tipo de cliente es. Se guarda la lista entera al
 * confirmar: una etiqueta a medio escribir no es una etiqueta.
 */
function Etiquetas({
  etiquetas,
  guardando,
  error,
  onGuardar,
}: {
  etiquetas: EtiquetaContacto[];
  guardando: boolean;
  error?: string;
  onGuardar: (etiquetas: EtiquetaContacto[]) => void;
}) {
  const [filas, setFilas] = useState<EtiquetaContacto[]>(etiquetas);
  const cambiado = JSON.stringify(filas) !== JSON.stringify(etiquetas);
  const validas = filas.every((f) => /^[A-Za-z]{1,8}$/.test(f.etiqueta.trim()));

  const cambiar = (i: number, cambios: Partial<EtiquetaContacto>) =>
    setFilas((antes) => antes.map((f, j) => (j === i ? { ...f, ...cambios } : f)));

  const CAMPO =
    "w-full rounded-lg border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

  return (
    <Tarjeta
      titulo="Etiquetas de contacto"
      bajada="La palabra en MAYÚSCULAS al final del nombre («Juan Pérez ARQ») que dice qué tipo de cliente es."
    >
      <Fila
        titulo={`${etiquetas.length} ${etiquetas.length === 1 ? "etiqueta" : "etiquetas"}`}
        queHace="Acá se define qué significa cada una y cómo se le habla. Una marcada «no contactar» hace que ese chat ni se abra, y el contacto queda excluido para siempre. Sin etiqueta, el sistema sigue como siempre."
      >
        <div className="space-y-2">
          {filas.map((fila, i) => (
            <div key={i} className="grid gap-2 rounded-lg border bg-muted/40 p-3 sm:grid-cols-[6rem_1fr_auto] sm:items-start">
              <input
                className={`${CAMPO} font-mono uppercase`}
                value={fila.etiqueta}
                maxLength={8}
                aria-label="Etiqueta"
                placeholder="ARQ"
                onChange={(evento) => cambiar(i, { etiqueta: evento.target.value.toUpperCase() })}
              />
              <div className="space-y-2">
                <input
                  className={CAMPO}
                  value={fila.significado}
                  maxLength={80}
                  aria-label="Qué es"
                  placeholder="Arquitecto"
                  onChange={(evento) => cambiar(i, { significado: evento.target.value })}
                />
                {fila.contactar && (
                  <textarea
                    rows={2}
                    className={CAMPO}
                    value={fila.enfoque}
                    maxLength={300}
                    aria-label="Cómo se le habla"
                    placeholder="Cómo enfocar el mensaje para este tipo de cliente (opcional)"
                    onChange={(evento) => cambiar(i, { enfoque: evento.target.value })}
                  />
                )}
              </div>
              <div className="flex items-center gap-3 sm:flex-col sm:items-end">
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  {fila.contactar ? "Se contacta" : "No contactar"}
                  <Interruptor
                    prendido={fila.contactar}
                    etiqueta={`Contactar a los ${fila.etiqueta || "contactos con esta etiqueta"}`}
                    onCambiar={(contactar) => cambiar(i, { contactar })}
                  />
                </label>
                <Button size="sm" variant="ghost" onClick={() => setFilas((antes) => antes.filter((_, j) => j !== i))}>
                  Quitar
                </Button>
              </div>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              size="sm"
              variant="outline"
              disabled={filas.length >= 20}
              onClick={() => setFilas((antes) => [...antes, { etiqueta: "", significado: "", contactar: true, enfoque: "" }])}
            >
              Agregar etiqueta
            </Button>
            <Button
              size="sm"
              disabled={guardando || !cambiado || !validas}
              onClick={() => onGuardar(filas.map((f) => ({ ...f, etiqueta: f.etiqueta.trim().toUpperCase() })))}
            >
              Guardar etiquetas
            </Button>
            {!validas && (
              <span className="text-xs text-destructive">Una etiqueta son letras solas, hasta 8, sin espacios ni tildes.</span>
            )}
            {error && <span className="text-xs text-destructive">{error}</span>}
          </div>
        </div>
      </Fila>
    </Tarjeta>
  );
}
