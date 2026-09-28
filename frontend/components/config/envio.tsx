"use client";

import { useState } from "react";

import {
  CampoHora,
  DiasDeLaSemana,
  diasDeLaVentana,
  esPaseUnico,
  Fila,
  HORA,
  Tarjeta,
  TODOS,
  useGuardarConfiguracion,
} from "@/components/config/base";
import { Button } from "@/components/ui/button";
import { Confirmacion } from "@/components/ui/dialogo";
import { Interruptor } from "@/components/ui/interruptor";
import type { Configuracion } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Envío y horarios: lo que decide cuándo pasa algo sin que nadie apriete nada.
 *
 * Va primera porque es donde está el control que más se busca —el envío
 * automático— y que antes estaba casi al final de una página de 1.500 líneas,
 * detrás de un campo donde había que escribir `ENVIAR`.
 */
export function SeccionEnvio({ config }: { config: Configuracion }) {
  return (
    <>
      <Tarjeta titulo="Automático" bajada="Lo que el sistema hace solo.">
        <EnvioAutomatico config={config} />
        {/* La `key` vuelve a armar el formulario cuando el valor guardado
            cambia (otro guardado, "Deshacer"), sin pisar lo que se está
            escribiendo en cada refresco. */}
        <CorridaProgramada key={JSON.stringify(config.programacion)} config={config} />
      </Tarjeta>
      <Tarjeta titulo="Horario de envío" bajada="Se evalúa en hora argentina.">
        <VentanaDeEnvio key={JSON.stringify(config.ventana)} config={config} />
        <Fila
          titulo="Espera entre mensajes"
          ayuda={
            <>
              Entre <span className="font-mono tabular-nums">{config.pausa_entre_envios_s[0]}</span> y{" "}
              <span className="font-mono tabular-nums">{config.pausa_entre_envios_s[1]}</span> segundos, al azar.
            </>
          }
          queHace="Es lo que evita que la línea parezca un robot. Es fijo: no se cambia desde el panel."
        />
      </Tarjeta>
    </>
  );
}

/**
 * El envío automático del pase único (D52), ahora como un switch (D56).
 *
 * **Prender pide una confirmación; apagar, no.** Es el mismo criterio del
 * freno: frenar de más no le hace daño a nadie, soltar sin mirar sí. Antes
 * prender pedía escribir `ENVIAR`; el dueño pidió que fuera tan simple como un
 * switch, y lo que queda es un diálogo del panel que dice qué va a pasar y
 * tiene un solo botón para aceptarlo. El `PATCH` es el mismo de siempre.
 *
 * Sólo existe con el pase único: el circuito de siempre no tiene cómo enviar
 * solo, y el backend lo ignora ahí.
 */
function EnvioAutomatico({ config }: { config: Configuracion }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  const [confirmando, setConfirmando] = useState(false);
  const activo = config.envio_automatico ?? false;
  const paseUnico = esPaseUnico(config);
  const destinosAbiertos = config.destinos_permitidos.includes(TODOS);
  const { inicio, fin, dias } = config.ventana;

  const cambiar = (prender: boolean) => {
    guardar(
      { envio_automatico: prender },
      { sinDeshacer: true, aviso: prender ? textos.config.avisoPrendido : textos.config.avisoApagado },
    );
  };

  return (
    <>
      <Fila
        titulo={textos.config.envioAutomatico}
        ayuda={
          paseUnico
            ? textos.config.envioAutomaticoAyuda(inicio, fin, diasDeLaVentana(dias))
            : "Sólo funciona con el pase único. Se elige en Mensajes › Cómo se dejan los borradores."
        }
        queHace={
          <>
            <p>
              Con esto prendido, el pase único no deja el borrador: lo <strong>envía</strong>, sin que nadie lo
              revise antes. Fuera del horario de envío deja borradores como siempre.
            </p>
            <p>{destinosAbiertos ? textos.config.envioAutomaticoAbierto : textos.config.envioAutomaticoAcotado}</p>
          </>
        }
        control={
          <Interruptor
            prendido={activo}
            peligroso
            etiqueta={textos.config.envioAutomatico}
            deshabilitado={guardando || (!paseUnico && !activo)}
            onCambiar={(prender) => (prender ? setConfirmando(true) : cambiar(false))}
          />
        }
      />
      <Confirmacion
        abierto={confirmando}
        onCerrar={() => setConfirmando(false)}
        onConfirmar={() => {
          cambiar(true);
          setConfirmando(false);
        }}
        titulo={textos.config.envioAutomaticoConfirmarTitulo}
        confirmar={textos.config.prender}
        peligrosa
        ocupado={guardando}
      >
        <p>{textos.config.envioAutomaticoConfirmar}</p>
        <p className="text-muted-foreground">
          {textos.config.envioAutomaticoAyuda(inicio, fin, diasDeLaVentana(dias))}{" "}
          {destinosAbiertos ? textos.config.envioAutomaticoAbierto : textos.config.envioAutomaticoAcotado}
        </p>
      </Confirmacion>
    </>
  );
}

/**
 * La corrida programada (D51): que arranque sola a la hora que se fije, en
 * hora argentina. El switch la prende con el horario que ya estaba; el horario
 * se cambia abajo y se guarda aparte.
 */
function CorridaProgramada({ config }: { config: Configuracion }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  const programacion = config.programacion;
  const [hora, setHora] = useState(programacion.hora);
  const [dias, setDias] = useState<number[]>([...programacion.dias].sort((a, b) => a - b));

  const valido = HORA.test(hora) && dias.length > 0;
  const cambiado = hora !== programacion.hora || dias.join() !== [...programacion.dias].sort((a, b) => a - b).join();

  return (
    <Fila
      titulo="Corrida automática"
      ayuda={
        programacion.activa
          ? `Arranca sola a las ${programacion.hora}, ${diasDeLaVentana(programacion.dias)}.`
          : "Apagada: la corrida arranca sólo cuando alguien aprieta «Generar seguimientos»."
      }
      queHace="Las computadoras tienen que estar prendidas a esa hora. Si el servidor estaba caído, la corrida sale cuando vuelve, hasta dos horas después. Con el sistema frenado o una corrida en curso, ese día se saltea y queda en el historial."
      control={
        <Interruptor
          prendido={programacion.activa}
          etiqueta="Corrida automática"
          deshabilitado={guardando || (!programacion.activa && !valido)}
          onCambiar={(activa) => guardar({ programacion: { activa, hora, dias } })}
        />
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <CampoHora valor={hora} onCambiar={setHora} etiqueta="Hora (HH:MM)" placeholder="17:00" />
        <DiasDeLaSemana dias={dias} onCambiar={setDias} />
        {cambiado && (
          <Button
            size="sm"
            disabled={guardando || !valido}
            onClick={() => guardar({ programacion: { activa: programacion.activa, hora, dias } })}
          >
            Guardar horario
          </Button>
        )}
      </div>
    </Fila>
  );
}

/**
 * El horario de envío, editable (D26). `24:00` como fin es "hasta el final del
 * día". El atajo 24/7 deja la ventana sin efecto práctico, y el cambio queda en
 * la auditoría como cualquier otro.
 */
function VentanaDeEnvio({ config }: { config: Configuracion }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  const ventana = config.ventana;
  const [inicio, setInicio] = useState(ventana.inicio);
  const [fin, setFin] = useState(ventana.fin);
  const [dias, setDias] = useState<number[]>([...ventana.dias].sort((a, b) => a - b));

  const sinRestriccion = ventana.inicio === "00:00" && ventana.fin === "24:00" && ventana.dias.length === 7;
  const cambiado =
    inicio !== ventana.inicio || fin !== ventana.fin || dias.join() !== [...ventana.dias].sort((a, b) => a - b).join();

  return (
    <Fila
      titulo="Cuándo puede salir un mensaje"
      ayuda={`Hoy: de ${ventana.inicio} a ${ventana.fin}, ${diasDeLaVentana(ventana.dias)}.`}
      queHace="Fuera de este horario no sale ningún mensaje: el botón de enviar contesta que no es horario, y el envío automático deja borradores. Formato HH:MM; 24:00 vale como fin del día."
      control={
        !sinRestriccion && (
          <Button
            size="sm"
            variant="outline"
            disabled={guardando}
            onClick={() => guardar({ ventana: { inicio: "00:00", fin: "24:00", dias: [1, 2, 3, 4, 5, 6, 7] } })}
          >
            Sin restricción (24/7)
          </Button>
        )
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <CampoHora valor={inicio} onCambiar={setInicio} etiqueta="Desde (HH:MM)" placeholder="09:00" />
        <span className="text-sm text-muted-foreground">a</span>
        <CampoHora valor={fin} onCambiar={setFin} etiqueta="Hasta (HH:MM, 24:00 = fin del día)" placeholder="19:00" />
        <DiasDeLaSemana dias={dias} onCambiar={setDias} />
        {cambiado && (
          <Button size="sm" disabled={guardando || dias.length === 0} onClick={() => guardar({ ventana: { inicio, fin, dias } })}>
            Guardar horario
          </Button>
        )}
      </div>
    </Fila>
  );
}
