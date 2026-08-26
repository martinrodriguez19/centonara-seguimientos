"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { guardarConfiguracion, traerConfiguracion, type Configuracion } from "@/lib/panel";

const TODOS = "*";

/**
 * Configuración: topes, palabras del rubro y destinos permitidos.
 *
 * El cliente tiene que poder cambiar un tope sin pedirnos nada y sin un
 * despliegue. Por eso vive en la base y no en variables de entorno — y por eso
 * cada cambio queda en la auditoría, con quién y cuándo.
 */
export default function Config() {
  const clienteQuery = useQueryClient();
  const config = useQuery({ queryKey: ["configuracion"], queryFn: traerConfiguracion });

  const guardar = useMutation({
    mutationFn: (cambios: Partial<Configuracion>) => guardarConfiguracion(cambios),
    onSuccess: (nueva) => {
      clienteQuery.setQueryData(["configuracion"], nueva);
      void clienteQuery.invalidateQueries({ queryKey: ["estado"] });
    },
  });

  if (config.isPending) return <p className="p-8 text-sm text-muted-foreground">Cargando…</p>;
  if (config.isError) {
    return <p className="p-8 text-sm text-destructive">{config.error.message}</p>;
  }

  const datos = config.data;

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Configuración</h1>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/panel">Volver al panel</Link>
        </Button>
      </div>

      <DestinosPermitidos
        destinos={datos.destinos_permitidos}
        guardando={guardar.isPending}
        onGuardar={(destinos_permitidos) => guardar.mutate({ destinos_permitidos })}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Qué chats se siguen</CardTitle>
          <p className="text-sm text-muted-foreground">
            Dos formas de elegir. <strong>Los más recientes</strong>: los de arriba de la lista,
            dentro de la ventana de silencio de abajo. <strong>Barrido del historial</strong>: va
            al fondo del WhatsApp y avanza del chat más viejo hacia hoy, de a tandas, recuperando
            a los clientes que quedaron sin recontactar — sin repetir a nadie que ya recibió algo.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant={(datos.modo_lectura ?? "recientes") === "recientes" ? "default" : "outline"}
              disabled={guardar.isPending}
              onClick={() => guardar.mutate({ modo_lectura: "recientes" })}
            >
              Los más recientes
            </Button>
            <Button
              size="sm"
              variant={datos.modo_lectura === "barrido" ? "default" : "outline"}
              disabled={guardar.isPending}
              onClick={() => guardar.mutate({ modo_lectura: "barrido" })}
            >
              Barrido del historial
            </Button>
          </div>
          {datos.modo_lectura === "barrido" ? (
            <p className="text-xs text-muted-foreground">
              Cada corrida lee la siguiente tanda de «Chats a leer por máquina» (abajo). El avance
              se ve en la tarjeta de cada máquina. La ventana de silencio no aplica en este modo.
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <Numero
                etiqueta="Silencio mínimo (días)"
                ayuda="Un chat más fresco que esto no necesita seguimiento todavía."
                valor={datos.antiguedad_min_dias ?? 0}
                onGuardar={(antiguedad_min_dias) => guardar.mutate({ antiguedad_min_dias })}
              />
              <Numero
                etiqueta="Silencio máximo (días)"
                ayuda="Más viejo que esto, el contacto se considera perdido y no se le escribe."
                valor={datos.antiguedad_max_dias ?? 90}
                onGuardar={(antiguedad_max_dias) => guardar.mutate({ antiguedad_max_dias })}
              />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sobre la empresa</CardTitle>
          <p className="text-sm text-muted-foreground">
            Todo lo que el redactor tiene que saber para escribir con conocimiento real: qué vende
            la empresa, productos y servicios, promociones vigentes, cómo le habla a sus clientes,
            con qué conviene recaptar. Cuanto más concreto, más fuertes salen los mensajes. Se
            puede cambiar cuando quieras — cada redacción usa la versión del momento.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <ContextoEmpresa
            valor={datos.contexto_empresa ?? ""}
            guardando={guardar.isPending}
            onGuardar={(contexto_empresa) => guardar.mutate({ contexto_empresa })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Topes</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Numero
            etiqueta="Chats a leer por máquina"
            valor={datos.n_chats_por_defecto}
            onGuardar={(n_chats_por_defecto) => guardar.mutate({ n_chats_por_defecto })}
          />
          <Numero
            etiqueta="Mensajes por máquina por día"
            ayuda="Es lo que protege la línea del vendedor."
            valor={datos.tope_diario_maquina}
            onGuardar={(tope_diario_maquina) => guardar.mutate({ tope_diario_maquina })}
          />
          <Numero
            etiqueta="Mensajes por corrida"
            valor={datos.tope_por_corrida}
            onGuardar={(tope_por_corrida) => guardar.mutate({ tope_por_corrida })}
          />
          <Numero
            etiqueta="Largo máximo del mensaje"
            valor={datos.largo_maximo}
            onGuardar={(largo_maximo) => guardar.mutate({ largo_maximo })}
          />
          <Numero
            etiqueta="Días sin repetirle a un contacto"
            valor={datos.dias_anti_duplicado}
            onGuardar={(dias_anti_duplicado) => guardar.mutate({ dias_anti_duplicado })}
          />
        </CardContent>
      </Card>

      <Palabras
        titulo="Palabras que apartan un mensaje"
        ayuda="Si el resumen del chat contiene alguna, el borrador se aparta para que lo mires antes de enviarlo. Agregá los términos de tu rubro."
        palabras={datos.palabras_conflicto}
        onGuardar={(palabras_conflicto) => guardar.mutate({ palabras_conflicto })}
      />

      <Palabras
        titulo="Palabras que hacen que un chat parezca de trabajo"
        ayuda="Si el resumen no contiene ninguna, el chat se considera no comercial y el borrador se retiene. Es la perilla que mueve la tasa de retención: si en métricas se te va del 10 al 20%, se calibra acá."
        palabras={datos.palabras_comerciales}
        onGuardar={(palabras_comerciales) => guardar.mutate({ palabras_comerciales })}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cuándo y a qué ritmo sale</CardTitle>
          <p className="text-sm text-muted-foreground">
            El horario lo manejás vos (se evalúa en hora argentina). Hoy:{" "}
            <span className="tabular-nums">
              {datos.ventana.inicio} a {datos.ventana.fin}
            </span>
            , {diasDeLaVentana(datos.ventana.dias)}.
          </p>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <VentanaDeEnvio
            ventana={datos.ventana}
            guardando={guardar.isPending}
            onGuardar={(ventana) => guardar.mutate({ ventana })}
          />
          <div>
            <p className="text-sm font-medium">Espera entre mensajes</p>
            <p className="text-sm tabular-nums text-muted-foreground">
              entre {datos.pausa_entre_envios_s[0]} y {datos.pausa_entre_envios_s[1]} segundos
            </p>
            <p className="text-xs text-muted-foreground">
              Al azar dentro de ese rango. Es lo que evita que la línea parezca un robot. Esto sí
              es fijo.
            </p>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}

/**
 * A quién puede escribirle el sistema (regla R4).
 *
 * Es el control más peligroso de todo el panel: abrirlo es lo que hace que una
 * corrida pueda alcanzar a un cliente real. Por eso el cambio a "todos" pide
 * escribir la palabra — no un click, no un `confirm()` que se acepta sin leer.
 */
function DestinosPermitidos({
  destinos,
  guardando,
  onGuardar,
}: {
  destinos: string[];
  guardando: boolean;
  onGuardar: (destinos: string[]) => void;
}) {
  const abierto = destinos.includes(TODOS);
  const [lista, setLista] = useState(destinos.filter((d) => d !== TODOS).join("\n"));
  const [confirmacion, setConfirmacion] = useState("");

  const numeros = () => lista.split("\n").map((l) => l.trim()).filter(Boolean);

  return (
    <Card className={abierto ? "border-critico-borde bg-critico-suave" : "border-atencion-borde"}>
      <CardHeader>
        <CardTitle className="text-base">Destinos permitidos</CardTitle>
        <p className="text-sm text-muted-foreground">
          El sistema sólo le escribe a estos números. Una lista vacía significa <strong>a
          nadie</strong>.
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        {abierto ? (
          <div className="flex items-start gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-3">
            <AlertTriangle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
            <div className="space-y-2">
              <p className="font-semibold text-destructive">Abierto a todos los contactos</p>
              <p className="text-sm text-muted-foreground">
                Cualquier chat que el sistema lea puede recibir un mensaje.
              </p>
              <Button
                variant="outline"
                size="sm"
                disabled={guardando}
                onClick={() => onGuardar(numeros())}
              >
                Volver a la lista acotada
              </Button>
            </div>
          </div>
        ) : (
          <>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Números, uno por línea</span>
              <textarea
                rows={4}
                className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="+5491144405036"
                value={lista}
                onChange={(evento) => setLista(evento.target.value)}
              />
            </label>
            <Button size="sm" disabled={guardando} onClick={() => onGuardar(numeros())}>
              Guardar lista
            </Button>

            <div className="space-y-2 rounded-md border border-destructive/40 p-3">
              <p className="text-sm font-semibold text-destructive">
                Abrir a todos los contactos
              </p>
              <p className="text-sm text-muted-foreground">
                A partir de ese momento el sistema puede escribirle a cualquier chat que lea. Para
                confirmar, escribí <code className="font-mono">ABRIR</code>.
              </p>
              <div className="flex gap-2">
                <input
                  className="w-32 rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={confirmacion}
                  onChange={(evento) => setConfirmacion(evento.target.value)}
                  aria-label="Escribí ABRIR para confirmar"
                />
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={confirmacion !== "ABRIR" || guardando}
                  onClick={() => {
                    onGuardar([TODOS]);
                    setConfirmacion("");
                  }}
                >
                  Abrir
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Numero({
  etiqueta,
  ayuda,
  valor,
  onGuardar,
}: {
  etiqueta: string;
  ayuda?: string;
  valor: number;
  onGuardar: (valor: number) => void;
}) {
  const [borrador, setBorrador] = useState(String(valor));
  const cambiado = borrador !== String(valor);

  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium">{etiqueta}</span>
      <div className="flex gap-2">
        <input
          type="number"
          min={1}
          className="w-24 rounded-md border border-input bg-background px-3 py-2 text-sm tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={borrador}
          onChange={(evento) => setBorrador(evento.target.value)}
        />
        {cambiado && (
          <Button size="sm" onClick={() => onGuardar(Number(borrador))}>
            Guardar
          </Button>
        )}
      </div>
      {ayuda && <span className="block text-xs text-muted-foreground">{ayuda}</span>}
    </label>
  );
}

/**
 * Una lista de palabras, editable como texto.
 *
 * Sirve a las dos del triage, que son la misma perilla por los dos lados:
 * `palabras_conflicto` aparta un borrador, y `palabras_comerciales` decide si
 * el chat parece de trabajo. Por eso el título y la ayuda vienen de afuera.
 */
function Palabras({
  titulo,
  ayuda,
  palabras,
  onGuardar,
}: {
  titulo: string;
  ayuda: string;
  palabras: string[];
  onGuardar: (palabras: string[]) => void;
}) {
  const [borrador, setBorrador] = useState(palabras.join("\n"));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{titulo}</CardTitle>
        <p className="text-sm text-muted-foreground">{ayuda}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <textarea
          rows={8}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={borrador}
          onChange={(evento) => setBorrador(evento.target.value)}
        />
        <Button
          size="sm"
          onClick={() =>
            onGuardar(borrador.split("\n").map((p) => p.trim()).filter(Boolean))
          }
        >
          Guardar palabras
        </Button>
      </CardContent>
    </Card>
  );
}

/**
 * Los días de la ventana, en palabras.
 *
 * El backend los manda como números de ISO (1 es lunes). "1,2,3,4,5" no le dice
 * nada a nadie, y el caso normal —de lunes a viernes— merece decirse así y no
 * como una enumeración de cinco días.
 */
/**
 * El texto libre del dueño sobre su empresa (D27). Viaja a cada redacción como
 * referencia; el prompt de la máquina lo enmarca como dato, no instrucciones.
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
  const LIMITE = 6000;

  return (
    <>
      <textarea
        rows={10}
        maxLength={LIMITE}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        placeholder={
          "Ejemplo:\nSomos E-Ticketpro, vendemos entradas y gestión de eventos.\n" +
          "Productos: ticketera online, control de accesos, cashless.\n" +
          "Promo vigente: 20% de descuento en la primera fecha.\n" +
          "Tono: cercano y profesional, tuteo rioplatense."
        }
        value={borrador}
        onChange={(evento) => setBorrador(evento.target.value)}
      />
      <div className="flex items-center justify-between">
        <Button size="sm" disabled={guardando || borrador === valor} onClick={() => onGuardar(borrador)}>
          Guardar información
        </Button>
        <span className="text-xs tabular-nums text-muted-foreground">
          {borrador.length} / {LIMITE}
        </span>
      </div>
    </>
  );
}

/**
 * El horario de envío, editable (D26): lo maneja el responsable del panel.
 *
 * `24:00` como fin significa "hasta el final del día". El atajo de un click
 * deja la ventana sin efecto práctico — sigue existiendo como mecanismo y el
 * cambio queda en la auditoría, pero no frena nada.
 */
function VentanaDeEnvio({
  ventana,
  guardando,
  onGuardar,
}: {
  ventana: { inicio: string; fin: string; dias: number[] };
  guardando: boolean;
  onGuardar: (ventana: { inicio: string; fin: string; dias: number[] }) => void;
}) {
  const [inicio, setInicio] = useState(ventana.inicio);
  const [fin, setFin] = useState(ventana.fin);
  const [dias, setDias] = useState<number[]>([...ventana.dias].sort((a, b) => a - b));
  const NOMBRES = ["", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

  const alternar = (dia: number) =>
    setDias((antes) =>
      antes.includes(dia) ? antes.filter((d) => d !== dia) : [...antes, dia].sort((a, b) => a - b),
    );

  const sinRestriccion =
    ventana.inicio === "00:00" && ventana.fin === "24:00" && ventana.dias.length === 7;

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">Horario de envío</p>
      <div className="flex items-center gap-2">
        <input
          className="w-20 rounded-md border border-input bg-background px-2 py-1.5 text-center font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={inicio}
          onChange={(evento) => setInicio(evento.target.value)}
          placeholder="09:00"
          aria-label="Desde (HH:MM)"
        />
        <span className="text-sm text-muted-foreground">a</span>
        <input
          className="w-20 rounded-md border border-input bg-background px-2 py-1.5 text-center font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={fin}
          onChange={(evento) => setFin(evento.target.value)}
          placeholder="19:00"
          aria-label="Hasta (HH:MM, 24:00 = fin del día)"
        />
      </div>
      <div className="flex flex-wrap gap-1">
        {[1, 2, 3, 4, 5, 6, 7].map((dia) => (
          <Button
            key={dia}
            type="button"
            size="sm"
            variant={dias.includes(dia) ? "default" : "outline"}
            onClick={() => alternar(dia)}
          >
            {NOMBRES[dia]}
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={guardando || dias.length === 0}
          onClick={() => onGuardar({ inicio, fin, dias })}
        >
          Guardar horario
        </Button>
        {!sinRestriccion && (
          <Button
            size="sm"
            variant="outline"
            disabled={guardando}
            onClick={() => onGuardar({ inicio: "00:00", fin: "24:00", dias: [1, 2, 3, 4, 5, 6, 7] })}
          >
            Sin restricción (24/7)
          </Button>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Formato HH:MM; 24:00 vale como fin del día. Fuera de la ventana, el botón de enviar
        contesta que no es horario.
      </p>
    </div>
  );
}

function diasDeLaVentana(dias: number[]): string {
  const NOMBRES = ["", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
  const ordenados = [...dias].sort((a, b) => a - b);

  if (ordenados.length === 0) return "ningún día";
  if (ordenados.length === 7) return "todos los días";

  // Un rango corrido se dice como rango. Lunes a viernes es el caso de fábrica.
  const corrido = ordenados.every((dia, i) => i === 0 || dia === ordenados[i - 1] + 1);
  if (corrido && ordenados.length > 2) {
    return `de ${NOMBRES[ordenados[0]]} a ${NOMBRES[ordenados[ordenados.length - 1]]}`;
  }
  return ordenados.map((dia) => NOMBRES[dia]).join(", ");
}
