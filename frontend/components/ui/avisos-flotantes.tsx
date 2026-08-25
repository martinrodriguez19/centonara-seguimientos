"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { type Nivel } from "@/components/ui/estado";
import { cn } from "@/lib/utils";

/**
 * Los avisos que aparecen después de una acción y se van solos.
 *
 * **Por qué.** Guardar en la pantalla de configuración no decía nada: el campo
 * se quedaba igual y no había forma de saber si el cambio había entrado. Lo
 * mismo con activar una máquina o rotar un token. Una acción que no confirma
 * nada obliga a recargar para saber si pasó, y eso hace que la gente apriete
 * dos veces — que en este panel es exactamente lo que no queremos.
 *
 * **Los errores no se van solos.** Un aviso que desaparece es aceptable para
 * "guardado"; para "no se pudo guardar" no, porque quien estaba mirando a otro
 * lado se queda creyendo que guardó. Los de nivel crítico se quedan hasta que
 * alguien los cierra.
 */
type AvisoFlotante = {
  id: number;
  nivel: Nivel;
  texto: string;
};

type Contexto = {
  avisar: (texto: string, nivel?: Nivel) => void;
};

const ContextoAvisos = createContext<Contexto | null>(null);

const SEGUNDOS_VISIBLE = 4000;

const COLOR: Record<Nivel, string> = {
  ok: "border-ok-borde bg-ok-suave text-ok",
  atencion: "border-atencion-borde bg-atencion-suave text-atencion",
  critico: "border-critico-borde bg-critico-suave text-critico",
  neutro: "border-border bg-card text-foreground",
};

export function ProveedorDeAvisos({ children }: { children: React.ReactNode }) {
  const [avisos, setAvisos] = useState<AvisoFlotante[]>([]);

  const cerrar = useCallback((id: number) => {
    setAvisos((previos) => previos.filter((a) => a.id !== id));
  }, []);

  const avisar = useCallback(
    (texto: string, nivel: Nivel = "ok") => {
      // Contador monótono y no `Date.now()`: dos avisos en el mismo
      // milisegundo compartirían clave y React reusaría el nodo del anterior.
      const id = siguienteId++;
      setAvisos((previos) => [...previos, { id, nivel, texto }]);
      if (nivel !== "critico") {
        setTimeout(() => cerrar(id), SEGUNDOS_VISIBLE);
      }
    },
    [cerrar],
  );

  const valor = useMemo(() => ({ avisar }), [avisar]);

  return (
    <ContextoAvisos.Provider value={valor}>
      {children}
      {/* Abajo a la derecha y por encima de todo, pero sin tapar la barra fija
          de envío, que vive abajo a la izquierda del contenido. */}
      <div
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:items-end"
        role="region"
        aria-label="Avisos"
      >
        {avisos.map((aviso) => (
          <div
            key={aviso.id}
            role={aviso.nivel === "critico" ? "alert" : "status"}
            className={cn(
              "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border p-3 text-sm shadow-lg",
              COLOR[aviso.nivel],
            )}
          >
            <span className="min-w-0 flex-1">{aviso.texto}</span>
            <button
              type="button"
              aria-label="Cerrar aviso"
              className="shrink-0 rounded px-1 opacity-70 outline-none hover:opacity-100 focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => cerrar(aviso.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ContextoAvisos.Provider>
  );
}

let siguienteId = 1;

/**
 * `avisar("Guardado")` desde cualquier componente.
 *
 * Fuera del proveedor no rompe: devuelve una función que no hace nada. Un aviso
 * que falta es un detalle; una pantalla que revienta porque el proveedor no
 * estaba montado, no.
 */
export function useAvisos(): Contexto {
  const contexto = useContext(ContextoAvisos);
  return contexto ?? { avisar: () => {} };
}
