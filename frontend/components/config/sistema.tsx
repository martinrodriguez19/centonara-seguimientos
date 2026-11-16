"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { CampoHora, Fila, HORA, Tarjeta, useGuardarConfiguracion } from "@/components/config/base";
import { useAvisos } from "@/components/ui/avisos-flotantes";
import { Button } from "@/components/ui/button";
import { Campo } from "@/components/ui/campo";
import { Confirmacion } from "@/components/ui/dialogo";
import { Pildora } from "@/components/ui/estado";
import { Interruptor } from "@/components/ui/interruptor";
import {
  actualizarAhora,
  borrarTokenClaude,
  cargarTokenClaude,
  empezarDeCero,
  traerTokenClaude,
  type Configuracion,
  type TokenClaude,
} from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Sistema: la versión del agente, Claude (el token y la cuenta compartida) y,
 * al final y aparte, empezar de cero.
 */
export function SeccionSistema({ config }: { config: Configuracion }) {
  return (
    <>
      <Tarjeta titulo="Versión del agente">
        <VersionDelAgente key={config.version_agente_esperada ?? ""} valor={config.version_agente_esperada ?? ""} />
        <ActualizacionProgramada key={JSON.stringify(config.actualizacion)} config={config} />
        <ActualizarAhora />
      </Tarjeta>
      <Tarjeta titulo={textos.cuentaClaude.tarjeta} bajada={textos.cuentaClaude.ayuda}>
        <TokenDeClaude />
        <CuentaDeClaude
          key={`${config.cuenta_claude_mail ?? ""}|${config.cuenta_claude_codigo_quien ?? ""}`}
          config={config}
        />
      </Tarjeta>
      {/* Última de la pantalla, y a propósito: es la que borra. */}
      <EmpezarDeCero />
    </>
  );
}

/**
 * El commit al que convergen las máquinas (D45).
 *
 * Se guarda al confirmar y no por tecla: un sha a medio escribir no es un sha,
 * y el backend lo rechaza — con razón, porque todas las máquinas se lo
 * pedirían a GitHub y fallarían juntas.
 */
function VersionDelAgente({ valor }: { valor: string }) {
  const { guardar, guardando, error } = useGuardarConfiguracion();
  const [borrador, setBorrador] = useState(valor);
  const limpio = borrador.trim().toLowerCase();
  const parece = limpio === "" || /^[0-9a-f]{7,40}$/.test(limpio);

  return (
    <Fila
      titulo="Commit fijado"
      ayuda={
        <>
          Hoy: <span className="font-mono">{valor ? valor.slice(0, 7) : "lo último publicado"}</span>. Cada máquina
          muestra en su detalle qué commit corre y si está al día.
        </>
      }
      queHace="Las computadoras de los vendedores se actualizan solas a la versión que se fije acá: al iniciar sesión y cada hora, o a la hora de abajo si la actualización programada está prendida. Vacío es «lo último que se publicó». Con un commit, todas van a ése: es la forma de volver atrás sin tocar ninguna computadora."
    >
      <div className="flex flex-wrap items-end gap-2">
        <Campo
          etiqueta="Commit"
          ayuda="Vacío: lo último publicado. Si no, el sha del commit (7 a 40 dígitos)."
          placeholder="ej. 7912e13"
          value={borrador}
          spellCheck={false}
          className="w-64 font-mono"
          onChange={(evento) => setBorrador(evento.target.value)}
          error={!parece ? "Eso no es un sha de git." : error}
        />
        <Button size="sm" disabled={guardando || !parece || limpio === valor} onClick={() => guardar({ version_agente_esperada: limpio })}>
          Fijar versión
        </Button>
        {valor && (
          <Button size="sm" variant="outline" disabled={guardando} onClick={() => guardar({ version_agente_esperada: "" })}>
            Volver a lo último
          </Button>
        )}
      </div>
    </Fila>
  );
}

/**
 * La actualización programada (D63): una vez por día a esta hora, en vez de
 * cada hora. Las computadoras toman el horario solas en su próximo latido.
 */
function ActualizacionProgramada({ config }: { config: Configuracion }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  const actual = config.actualizacion;
  const [hora, setHora] = useState(actual.hora);
  const valido = HORA.test(hora);

  return (
    <Fila
      titulo={textos.actualizacion.titulo}
      ayuda={actual.activa ? textos.actualizacion.prendida(actual.hora) : textos.actualizacion.apagada}
      queHace={textos.actualizacion.queHace}
      control={
        <Interruptor
          prendido={actual.activa}
          etiqueta={textos.actualizacion.titulo}
          deshabilitado={guardando || (!actual.activa && !valido)}
          onCambiar={(activa) => guardar({ actualizacion: { activa, hora } })}
        />
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <CampoHora valor={hora} onCambiar={setHora} etiqueta="Hora de actualizar (HH:MM)" placeholder="15:00" />
        {hora !== actual.hora && (
          <Button
            size="sm"
            disabled={guardando || !valido}
            onClick={() => guardar({ actualizacion: { activa: actual.activa, hora } })}
          >
            Guardar horario
          </Button>
        )}
      </div>
    </Fila>
  );
}

/** "Actualizar ahora" (D63): para un arreglo urgente, sin esperar la hora. */
function ActualizarAhora() {
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();
  const actualizar = useMutation({
    mutationFn: actualizarAhora,
    onSuccess: () => avisar(textos.actualizacion.avisoAhora),
    onError: () => avisar(textos.actualizacion.avisoFallo, "critico"),
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["configuracion"] }),
  });
  return (
    <Fila
      titulo={textos.actualizacion.ahoraTitulo}
      ayuda={textos.actualizacion.ahoraAyuda}
      control={
        <Button size="sm" variant="outline" disabled={actualizar.isPending} onClick={() => actualizar.mutate()}>
          {textos.actualizacion.ahoraBoton}
        </Button>
      }
    />
  );
}

/** "corré `claude setup-token`" con el comando en monoespaciada. */
function conCodigo(texto: string) {
  return texto.split("`").map((parte, i) =>
    i % 2 === 1 ? (
      <code key={i} className="font-mono text-foreground">
        {parte}
      </code>
    ) : (
      parte
    ),
  );
}

const dia = (iso: string) => new Date(iso).toLocaleDateString("es-AR", { dateStyle: "long" });

/**
 * El token de Claude (D73): se pega una vez y llega solo a todas las máquinas.
 *
 * **El panel nunca lo vuelve a mostrar.** Lo que se ve después de guardarlo es
 * cuándo se cargó, cuándo vence y cuántas máquinas ya lo tienen: el backend no
 * devuelve el valor, y el campo se vacía al guardar para que tampoco quede en
 * la pantalla.
 */
function TokenDeClaude() {
  const tt = textos.tokenClaude;
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();
  const resumen = useQuery({ queryKey: ["token-claude"], queryFn: traerTokenClaude });
  const [token, setToken] = useState("");
  const [borrando, setBorrando] = useState(false);

  const limpio = token.trim();
  // La misma regla gruesa que el backend: lo fino lo decide él (400).
  const parece = limpio === "" || limpio.startsWith("sk-ant-");

  const alTerminar = (nuevo: TokenClaude) => {
    clienteQuery.setQueryData(["token-claude"], nuevo);
    void clienteQuery.invalidateQueries({ queryKey: ["estado"] });
  };

  const guardar = useMutation({
    mutationFn: () => cargarTokenClaude(limpio),
    onSuccess: (nuevo) => {
      setToken("");
      alTerminar(nuevo);
      avisar(tt.guardado);
    },
  });

  const borrar = useMutation({
    mutationFn: borrarTokenClaude,
    onSuccess: (nuevo) => {
      setBorrando(false);
      alTerminar(nuevo);
      avisar(tt.borrado);
    },
    onError: () => avisar(tt.fallo, "critico"),
  });

  const datos = resumen.data;

  return (
    <Fila
      titulo={tt.titulo}
      ayuda={conCodigo(tt.ayuda)}
      queHace={tt.queHace}
      control={
        datos?.cargado ? (
          <Button size="sm" variant="outline" disabled={borrar.isPending} onClick={() => setBorrando(true)}>
            {tt.borrar}
          </Button>
        ) : undefined
      }
    >
      {datos && (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          {datos.cargado && datos.cargado_en ? (
            <>
              <span>
                {tt.cargado(dia(datos.cargado_en))}
                {datos.vence_aprox && `, ${tt.vence(dia(datos.vence_aprox))}`}.
              </span>
              <Pildora nivel={datos.maquinas_al_dia >= datos.maquinas_activas ? "ok" : "atencion"}>
                {tt.maquinas(datos.maquinas_al_dia, datos.maquinas_activas)}
              </Pildora>
            </>
          ) : (
            <span className="text-muted-foreground">{tt.sinCargar}</span>
          )}
        </p>
      )}
      {resumen.isError && <p className="text-sm text-destructive">{resumen.error.message}</p>}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(evento) => {
          evento.preventDefault();
          if (limpio && parece) guardar.mutate();
        }}
      >
        <Campo
          etiqueta={tt.campo}
          ayuda={tt.campoAyuda}
          type="password"
          autoComplete="off"
          spellCheck={false}
          placeholder="sk-ant-…"
          className="w-80 max-w-full font-mono"
          value={token}
          onChange={(evento) => setToken(evento.target.value)}
          error={!parece ? tt.noParece : guardar.isError ? guardar.error.message : null}
        />
        <Button type="submit" size="sm" className="mb-5" disabled={guardar.isPending || !limpio || !parece}>
          {tt.guardar}
        </Button>
      </form>

      <Confirmacion
        abierto={borrando}
        onCerrar={() => setBorrando(false)}
        onConfirmar={() => borrar.mutate()}
        titulo={tt.borrarTitulo}
        confirmar={tt.borrar}
        peligrosa
        ocupado={borrar.isPending}
      >
        <p>{tt.borrarTexto}</p>
      </Confirmacion>
    </Fila>
  );
}

const MAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * La cuenta compartida de Claude (D71): el mail y a quién pedirle el código.
 *
 * El mail viaja sólo a la máquina, para el aviso en su pantalla; el nombre es
 * lo único de la cuenta que ve la página pública. Se guardan juntos, con un
 * botón, porque un mail a medio escribir no es un mail.
 */
function CuentaDeClaude({ config }: { config: Configuracion }) {
  const tc = textos.cuentaClaude;
  const { guardar, guardando, error } = useGuardarConfiguracion();
  const guardadoMail = config.cuenta_claude_mail ?? "";
  const guardadoQuien = config.cuenta_claude_codigo_quien ?? "";
  const [mail, setMail] = useState(guardadoMail);
  const [quien, setQuien] = useState(guardadoQuien);
  const mailLimpio = mail.trim();
  const mailValido = mailLimpio === "" || MAIL.test(mailLimpio);
  const cambio = mailLimpio !== guardadoMail || quien.trim() !== guardadoQuien;

  return (
    <Fila titulo={tc.titulo}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Campo
          etiqueta={tc.mail}
          ayuda={tc.mailAyuda}
          type="email"
          autoComplete="off"
          value={mail}
          onChange={(evento) => setMail(evento.target.value)}
          error={!mailValido ? tc.mailInvalido : null}
        />
        <Campo
          etiqueta={tc.quien}
          ayuda={tc.quienAyuda}
          placeholder={tc.quienPlaceholder}
          maxLength={60}
          value={quien}
          onChange={(evento) => setQuien(evento.target.value)}
        />
      </div>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          disabled={guardando || !cambio || !mailValido}
          onClick={() => guardar({ cuenta_claude_mail: mailLimpio, cuenta_claude_codigo_quien: quien.trim() })}
        >
          {tc.guardar}
        </Button>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    </Fila>
  );
}

/**
 * Vaciar el sistema para entregárselo a alguien (D28).
 *
 * Lo peligroso no es perder las corridas de prueba: es entregar el sistema con
 * los destinos permitidos de otra persona cargados. Por eso restablecer la
 * configuración viene marcado, y por eso hay que escribir la palabra — igual
 * que antes del rediseño: borrar no se deshace.
 */
function EmpezarDeCero() {
  const clienteQuery = useQueryClient();
  const [confirmacion, setConfirmacion] = useState("");
  const [restablecer, setRestablecer] = useState(true);
  const [borrarMaquinas, setBorrarMaquinas] = useState(false);
  const [hecho, setHecho] = useState<string | null>(null);

  const borrar = useMutation({
    mutationFn: () =>
      empezarDeCero({
        confirmacion,
        restablecer_configuracion: restablecer,
        borrar_maquinas: borrarMaquinas,
      }),
    onSuccess: (resultado) => {
      const total = Object.values(resultado.borrados).reduce((a, b) => a + b, 0);
      setHecho(`Listo: se borraron ${total} registros. El sistema quedó como recién instalado.`);
      setConfirmacion("");
      void clienteQuery.invalidateQueries();
    },
  });

  return (
    <Tarjeta titulo="Empezar de cero" bajada="Para entregar el sistema sin los datos de las pruebas." tono="peligro">
      <div className="grid gap-3 py-4 text-sm sm:grid-cols-2">
        <div>
          <p className="font-medium">Se borra</p>
          <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            <li>Las corridas y sus borradores</li>
            <li>Los mensajes enviados y descartados</li>
            <li>Los números que el sistema había averiguado</li>
            <li>El avance del barrido de cada máquina</li>
          </ul>
        </div>
        <div>
          <p className="font-medium">No se borra</p>
          <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            <li>El historial de auditoría: no se puede borrar ni desde acá ni desde la base</li>
            <li>Las máquinas instaladas, salvo que lo pidas abajo</li>
            <li>Nada de WhatsApp: los chats del vendedor no se tocan nunca</li>
          </ul>
        </div>
      </div>

      <Fila
        titulo="Volver la configuración a cero"
        ayuda="Deja la lista de destinos vacía —que significa a nadie— y borra la información de la empresa."
        queHace="Es lo que corresponde al entregar: si no, el cliente hereda los números con los que probaste."
        control={<Interruptor prendido={restablecer} etiqueta="Volver la configuración a cero" onCambiar={setRestablecer} />}
      />
      <Fila
        titulo="Dar de baja las máquinas"
        ayuda="Revoca sus tokens: hay que volver a instalarlas una por una."
        queHace="Sólo si las computadoras de prueba no son las del cliente."
        control={<Interruptor prendido={borrarMaquinas} etiqueta="Dar de baja las máquinas" peligroso onCambiar={setBorrarMaquinas} />}
      />

      <div className="py-4">
        <div className="space-y-2 rounded-lg border border-critico-borde p-3">
          <p className="text-sm">
            Esto no se puede deshacer. Para confirmar, escribí <code className="font-mono">BORRAR</code>.
          </p>
          <div className="flex gap-2">
            <input
              className="h-8 w-32 rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={confirmacion}
              onChange={(evento) => setConfirmacion(evento.target.value)}
              aria-label="Escribí BORRAR para confirmar"
            />
            <Button
              variant="destructive"
              size="sm"
              disabled={confirmacion.trim().toUpperCase() !== "BORRAR" || borrar.isPending}
              onClick={() => borrar.mutate()}
            >
              {borrar.isPending ? "Borrando…" : "Empezar de cero"}
            </Button>
          </div>
          {hecho && <p className="text-sm text-muted-foreground">{hecho}</p>}
          {borrar.error && <p className="text-sm text-destructive">{borrar.error.message}</p>}
        </div>
      </div>
    </Tarjeta>
  );
}
