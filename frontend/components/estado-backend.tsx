"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { EstadoBackend } from "@/lib/api";
import { textos } from "@/lib/textos";

const t = textos.diagnostico;

/** Los tres estados que la pantalla distingue. Ver `t.detalle`. */
type Semaforo = "operativo" | "degradado" | "inalcanzable";

function clasificar(estado: EstadoBackend): Semaforo {
  if (!estado.alcanzable) return "inalcanzable";
  return estado.salud.ok ? "operativo" : "degradado";
}

// Clases explícitas y no armadas con plantillas: Tailwind hace análisis
// estático del código fuente y una clase construida en tiempo de ejecución no
// termina en el CSS.
const ESTILO: Record<Semaforo, { punto: string; badge: string }> = {
  operativo: {
    punto: "bg-emerald-500",
    badge: "border-emerald-600/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  degradado: {
    punto: "bg-amber-500",
    badge: "border-amber-600/30 bg-amber-500/10 text-amber-700 dark:text-amber-500",
  },
  inalcanzable: {
    punto: "bg-red-500",
    badge: "border-red-600/30 bg-red-500/10 text-red-700 dark:text-red-400",
  },
};

async function pedirEstado(): Promise<EstadoBackend> {
  // La ruta interna contesta 200 siempre (ver app/api/estado-backend/route.ts).
  // Un no-2xx acá es un problema del frontend, no del backend, y sí es un error.
  const respuesta = await fetch("/api/estado-backend", { cache: "no-store" });
  if (!respuesta.ok) {
    throw new Error(`La ruta interna contestó ${respuesta.status}`);
  }
  return (await respuesta.json()) as EstadoBackend;
}

export function EstadoDelBackend({ inicial }: { inicial: EstadoBackend }) {
  const { data, dataUpdatedAt, isFetching, refetch } = useQuery({
    queryKey: ["estado-backend"],
    queryFn: pedirEstado,
    // El servidor ya consultó al renderizar la página: la primera pintura
    // muestra el estado real y no un esqueleto vacío.
    initialData: inicial,
    refetchInterval: 5000,
    // TanStack pausa el intervalo cuando la pestaña no está visible. Acá lo
    // desactivamos: esta pantalla se deja abierta en un segundo monitor, y una
    // pantalla congelada que dice "operativo" es peor que no tener pantalla.
    // Mismo criterio va a valer para la cuenta regresiva de la sala de salida.
    refetchIntervalInBackground: true,
  });

  const semaforo = clasificar(data);
  const estilo = ESTILO[semaforo];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle>{t.backend.titulo}</CardTitle>
            <CardDescription>{t.backend.descripcion}</CardDescription>
          </div>
          <Badge variant="outline" className={estilo.badge}>
            <span className={`mr-1.5 size-2 rounded-full ${estilo.punto}`} aria-hidden />
            {t.estado[semaforo]}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t.detalle[semaforo]}</p>

        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
          {data.alcanzable ? (
            <>
              <Dato etiqueta={t.campos.ok} valor={booleano(data.salud.ok)} />
              <Dato etiqueta={t.campos.mongo} valor={booleano(data.salud.mongo)} />
              <Dato
                etiqueta={t.campos.entorno}
                valor={textos.entornos[data.salud.entorno]}
              />
              <Dato etiqueta={t.campos.httpStatus} valor={String(data.httpStatus)} />
            </>
          ) : (
            <Dato etiqueta="Motivo" valor={data.motivo} />
          )}
          <Dato etiqueta={t.campos.url} valor={data.url} />
          <Dato etiqueta={t.campos.actualizado} valor={<Hora ms={dataUpdatedAt} />} />
        </dl>

        <div className="flex items-center gap-3 pt-1">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? t.acciones.consultando : t.acciones.reconsultar}
          </Button>
          <span className="text-xs text-muted-foreground">{t.autorefresco}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function booleano(valor: boolean): string {
  return valor ? textos.diagnostico.valores.si : textos.diagnostico.valores.no;
}

function Dato({ etiqueta, valor }: { etiqueta: string; valor: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{etiqueta}</dt>
      <dd className="font-mono text-xs break-all sm:text-sm">{valor}</dd>
    </>
  );
}

/**
 * La hora, sólo después de montar.
 *
 * En el servidor no sabemos la zona horaria del navegador, así que renderizarla
 * ahí y otra vez en el cliente da textos distintos y React avisa de una
 * discrepancia de hidratación. El guion es el marcador de "todavía no".
 */
function Hora({ ms }: { ms: number }) {
  const [montado, setMontado] = useState(false);
  useEffect(() => setMontado(true), []);
  if (!montado) return <>—</>;
  return <>{new Date(ms).toLocaleTimeString("es-AR")}</>;
}
