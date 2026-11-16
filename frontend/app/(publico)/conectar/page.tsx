"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { VistaDePasos } from "@/components/conectar/pasos";
import { TarjetaDeConexion } from "@/components/conectar/tarjeta";
import { Aviso } from "@/components/ui/estado";
import {
  ErrorDeConexiones,
  pedirReconexion,
  traerConexiones,
  type Pedido,
  type TipoDeReconexion,
} from "@/lib/conectar";
import { textos } from "@/lib/textos";

const t = textos.conectar;

/**
 * La página de conexiones (D71): la abre el vendedor en el celular, ve si se le
 * cayó WhatsApp o Claude, y toca un botón.
 *
 * Pública y sin login, así que lo que muestra es exactamente lo que devuelve
 * `GET /api/publico/conexiones` y nada más: ningún dato del panel pasa por
 * acá. El QR y el mail de la cuenta aparecen en la pantalla de la computadora,
 * nunca en esta página.
 *
 * Dos vistas: la lista (una tarjeta por computadora) y, después de tocar
 * "Volver a conectar", los pasos de esa computadora. El pedido en curso vive
 * en el estado de React: si se recarga la página, vuelve a la lista, y el
 * semáforo sigue diciendo la verdad.
 */
export default function Conectar() {
  const conexiones = useQuery({
    queryKey: ["conexiones"],
    queryFn: traerConexiones,
    refetchInterval: 5000,
    // Con el celular sin señal no tiene sentido insistir en el momento: el
    // intervalo ya vuelve a probar en cinco segundos.
    retry: false,
  });
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const pedir = useMutation({
    mutationFn: ({ maquina, tipo }: { maquina: string; tipo: TipoDeReconexion }) =>
      pedirReconexion(maquina, tipo),
    onMutate: () => setAviso(null),
    onSuccess: (respuesta, { maquina, tipo }) => {
      if (tipo === "verificar") {
        setPedido((p) => p && { ...p, verificacionPedida: true, desde: respuesta.reconexion.pedida_en });
      } else {
        setPedido({ maquina, tipo, pedidoEn: Date.now(), desde: respuesta.reconexion.pedida_en, verificacionPedida: false });
      }
      void conexiones.refetch();
    },
    onError: (error, { maquina, tipo }) => {
      // Un 429 es "ya se pidió recién": el pedido que vale es el que ya está
      // en camino, así que igual se pasa a los pasos, con el texto del servidor.
      if (error instanceof ErrorDeConexiones && error.status === 429) {
        setAviso(error.texto ?? t.falloPedido);
        if (tipo === "verificar") {
          setPedido((p) => p && { ...p, verificacionPedida: true, desde: null });
        } else {
          setPedido({ maquina, tipo, pedidoEn: Date.now(), desde: null, verificacionPedida: false });
        }
        return;
      }
      setAviso(t.falloPedido);
    },
  });

  const volver = useCallback(() => {
    setPedido(null);
    setAviso(null);
  }, []);

  const datos = conexiones.data;
  const sinRed = conexiones.isError;

  return (
    <main className="mx-auto w-full max-w-md space-y-5 px-4 py-6">
      <header className="space-y-1">
        <p className="text-sm font-medium tracking-wide text-muted-foreground uppercase">{t.marca}</p>
        <h1 className="text-3xl font-semibold">{t.titulo}</h1>
        {!pedido && <p className="text-lg text-muted-foreground">{t.bajada}</p>}
      </header>

      {/* Sin red se sigue mostrando lo último que se supo: es mejor que una
          pantalla vacía, y el aviso dice que puede estar viejo. */}
      {sinRed && <Aviso nivel="atencion" titulo={t.sinRed} />}

      {pedido ? (
        <VistaDePasos
          pedido={pedido}
          conexion={datos?.maquinas.find((m) => m.maquina === pedido.maquina)}
          pedirCodigoA={datos?.pedir_codigo_a ?? ""}
          aviso={aviso}
          ocupado={pedir.isPending}
          onVerificar={() => pedir.mutate({ maquina: pedido.maquina, tipo: "verificar" })}
          onReintentar={() => pedir.mutate({ maquina: pedido.maquina, tipo: pedido.tipo })}
          onVolver={volver}
        />
      ) : (
        <>
          {aviso && <Aviso nivel="critico" titulo={aviso} />}
          {conexiones.isPending && <p className="text-lg text-muted-foreground">{t.cargando}</p>}
          {datos && datos.maquinas.length === 0 && (
            <p className="text-lg text-muted-foreground">{t.sinComputadoras}</p>
          )}
          {datos?.maquinas.map((conexion) => (
            <TarjetaDeConexion
              key={conexion.maquina}
              conexion={conexion}
              ocupado={pedir.isPending && pedir.variables?.maquina === conexion.maquina}
              onReconectar={(tipo) => pedir.mutate({ maquina: conexion.maquina, tipo })}
            />
          ))}
        </>
      )}
    </main>
  );
}
