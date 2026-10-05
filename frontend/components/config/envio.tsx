"use client";

import { useState } from "react";

import {
  CampoHora,
  DiasDeLaSemana,
  diasDeLaVentana,
  esPaseUnico,
  Fila,
  HORA,
  Numero,
  Tarjeta,
  TODOS,
  useGuardarConfiguracion,
} from "@/components/config/base";
import { Button } from "@/components/ui/button";
import { Aviso } from "@/components/ui/estado";
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
        <Repesca key={JSON.stringify(config.repesca)} config={config} />
        <PausaPorCuota config={config} />
        <Descanso key={JSON.stringify(config.descanso)} config={config} />
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
 * La repesca (D61): a esta hora revisa qué hizo cada máquina hoy y completa lo
 * que le faltó. Misma forma que la corrida automática.
 *
 * Envía si el envío automático está prendido, **dentro del horario de envío**:
 * si la hora cae afuera, avisa acá mismo que sólo va a dejar borradores. No
 * amplía el horario sola: eso lo decide quien maneja el panel.
 */
function Repesca({ config }: { config: Configuracion }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  const repesca = config.repesca;
  const [hora, setHora] = useState(repesca.hora);
  const [dias, setDias] = useState<number[]>([...repesca.dias].sort((a, b) => a - b));

  const valido = HORA.test(hora) && dias.length > 0;
  const cambiado = hora !== repesca.hora || dias.join() !== [...repesca.dias].sort((a, b) => a - b).join();
  const fuera = fueraDelHorarioDeEnvio(hora, dias, config.ventana);

  return (
    <Fila
      titulo={textos.repesca.titulo}
      ayuda={
        repesca.activa
          ? textos.repesca.prendida(repesca.hora, diasDeLaVentana(repesca.dias))
          : textos.repesca.apagada
      }
      queHace={textos.repesca.queHace}
      control={
        <Interruptor
          prendido={repesca.activa}
          etiqueta={textos.repesca.titulo}
          deshabilitado={guardando || (!repesca.activa && !valido)}
          onCambiar={(activa) => guardar({ repesca: { activa, hora, dias } })}
        />
      }
    >
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <CampoHora valor={hora} onCambiar={setHora} etiqueta="Hora de la repesca (HH:MM)" placeholder="21:00" />
          <DiasDeLaSemana dias={dias} onCambiar={setDias} />
          {cambiado && (
            <Button
              size="sm"
              disabled={guardando || !valido}
              onClick={() => guardar({ repesca: { activa: repesca.activa, hora, dias } })}
            >
              Guardar horario
            </Button>
          )}
        </div>
        {config.envio_automatico && valido && fuera && (
          <Aviso nivel="atencion" titulo={textos.repesca.soloBorradoresTitulo(hora)}>
            {textos.repesca.soloBorradores(config.ventana.inicio, config.ventana.fin)}
          </Aviso>
        )}
      </div>
    </Fila>
  );
}

/** ¿La repesca cae, algún día, fuera del horario de envío? Ahí no envía (D61). */
function fueraDelHorarioDeEnvio(
  hora: string,
  dias: number[],
  ventana: Configuracion["ventana"],
): boolean {
  const minutos = (hhmm: string) => {
    const [h, m] = hhmm.split(":").map(Number);
    return h * 60 + m;
  };
  const enHora = minutos(hora) >= minutos(ventana.inicio) && minutos(hora) < minutos(ventana.fin);
  return !enHora || dias.some((d) => !ventana.dias.includes(d));
}

/**
 * El descanso (D64): las noches marcadas de «desde» a «hasta», y los días libres
 * enteros, nada trabaja; con «Suspender», las computadoras además se duermen y
 * se despiertan solas. Se guarda junto, con un botón, como los horarios.
 */
function Descanso({ config }: { config: Configuracion }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  const actual = config.descanso;
  const [desde, setDesde] = useState(actual.desde);
  const [hasta, setHasta] = useState(actual.hasta);
  const [noches, setNoches] = useState<number[]>([...actual.dias]);
  const [libres, setLibres] = useState<number[]>([...actual.dia_libre]);
  const [suspender, setSuspender] = useState(actual.suspender);

  const nuevo = { activa: actual.activa, desde, hasta, dias: noches, dia_libre: libres, suspender };
  const valido = HORA.test(desde) && HORA.test(hasta) && desde !== hasta && libres.length < 7;
  const cambiado = JSON.stringify(nuevo) !== JSON.stringify({ ...actual, dias: [...actual.dias], dia_libre: [...actual.dia_libre] });

  const choques = [
    config.programacion.activa && caeEnDescanso(config.programacion.hora, config.programacion.dias, nuevo)
      ? "corrida automática"
      : null,
    config.repesca.activa && caeEnDescanso(config.repesca.hora, config.repesca.dias, nuevo) ? "repesca" : null,
  ].filter((c): c is string => c !== null);

  return (
    <Fila
      titulo={textos.descanso.titulo}
      ayuda={
        actual.activa
          ? textos.descanso.prendido(
              actual.desde,
              actual.hasta,
              diasDeLaVentana(actual.dias),
              actual.dia_libre.length ? diasDeLaVentana(actual.dia_libre) : "",
            )
          : textos.descanso.apagado
      }
      queHace={textos.descanso.queHace}
      control={
        <Interruptor
          prendido={actual.activa}
          etiqueta={textos.descanso.titulo}
          deshabilitado={guardando || (!actual.activa && !valido)}
          onCambiar={(activa) => guardar({ descanso: { ...nuevo, activa } })}
        />
      }
    >
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <CampoHora valor={desde} onCambiar={setDesde} etiqueta="Desde (HH:MM)" placeholder="00:00" />
          <CampoHora valor={hasta} onCambiar={setHasta} etiqueta="Hasta (HH:MM)" placeholder="08:00" />
        </div>
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">{textos.descanso.noches}</p>
          <DiasDeLaSemana dias={noches} onCambiar={setNoches} />
        </div>
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">{textos.descanso.diaLibre}</p>
          <DiasDeLaSemana dias={libres} onCambiar={setLibres} />
        </div>
        <div className="flex items-center gap-3">
          <Interruptor prendido={suspender} etiqueta={textos.descanso.suspender} onCambiar={setSuspender} />
          <span className="text-sm">{textos.descanso.suspender}</span>
        </div>
        {cambiado && (
          <Button size="sm" disabled={guardando || !valido} onClick={() => guardar({ descanso: nuevo })}>
            {textos.descanso.guardar}
          </Button>
        )}
        {nuevo.activa &&
          choques.map((que) => (
            <Aviso key={que} nivel="atencion" titulo={textos.descanso.choca(que)} />
          ))}
      </div>
    </Fila>
  );
}

/** ¿Alguno de esos días, a esa hora, cae dentro del descanso? Lo mismo que el backend (D64). */
function caeEnDescanso(hora: string, dias: number[], descanso: Configuracion["descanso"]): boolean {
  const minutos = (hhmm: string) => {
    const [h, m] = hhmm.split(":").map(Number);
    return h * 60 + m;
  };
  const m = minutos(hora);
  const desde = minutos(descanso.desde);
  const hasta = minutos(descanso.hasta);
  return dias.some((dia) => {
    if (descanso.dia_libre.includes(dia)) return true;
    if (desde < hasta) return descanso.dias.includes(dia) && m >= desde && m < hasta;
    const anterior = ((dia + 5) % 7) + 1;
    return (descanso.dias.includes(dia) && m >= desde) || (descanso.dias.includes(anterior) && m < hasta);
  });
}

/** D60: cuánto se pausa una máquina sin cuota cuando Claude no dice cuándo vuelve. */
function PausaPorCuota({ config }: { config: Configuracion }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  return (
    <Fila
      titulo={textos.repesca.pausaCuotaTitulo}
      ayuda={textos.repesca.pausaCuotaAyuda}
      queHace={textos.repesca.pausaCuotaQueHace}
      control={
        <Numero
          etiqueta={textos.repesca.pausaCuotaTitulo}
          max={24}
          sufijo="horas"
          valor={config.horas_pausa_cuota}
          guardando={guardando}
          onGuardar={(horas_pausa_cuota) => guardar({ horas_pausa_cuota })}
        />
      }
    />
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
