"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { AltaMaquina, TokenReciente } from "@/components/alta-maquina";
import { ErrorDeCarga } from "@/components/error-de-carga";
import { GrillaDeMaquinas } from "@/components/maquinas/grilla";
import { Pagina } from "@/components/navegacion/pagina";
import { EsqueletoDelPanel } from "@/components/ui/esqueleto";
import { useEstado } from "@/lib/consultas";
import { textos } from "@/lib/textos";

/**
 * Las máquinas: todas las tarjetas, y el alta (que antes estaba en el inicio).
 */
export default function Maquinas() {
  const estado = useEstado();
  const clienteQuery = useQueryClient();
  const [tokenNuevo, setTokenNuevo] = useState<{ token: string; maquina: string } | null>(null);
  const alToken = (token: string, maquina: string) => {
    setTokenNuevo({ token, maquina });
    void clienteQuery.invalidateQueries({ queryKey: ["estado"] });
  };

  const maquinas = estado.data?.maquinas ?? [];
  const activas = maquinas.filter((m) => m.activo);
  const conectadas = activas.filter((m) => m.online).length;

  return (
    <Pagina
      titulo={textos.maquinas.titulo}
      bajada={estado.data ? `${textos.maquinas.bajada} ${textos.maquinas.conectadas(conectadas, activas.length)}.` : textos.maquinas.bajada}
      acciones={<AltaMaquina onToken={alToken} />}
    >
      {tokenNuevo && (
        <TokenReciente token={tokenNuevo.token} maquina={tokenNuevo.maquina} onCerrar={() => setTokenNuevo(null)} />
      )}
      {estado.isPending && <EsqueletoDelPanel />}
      {estado.isError && <ErrorDeCarga error={estado.error} onReintentar={() => void estado.refetch()} />}
      {estado.data && <GrillaDeMaquinas maquinas={maquinas} onToken={alToken} />}
    </Pagina>
  );
}
