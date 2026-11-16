import { Button } from "@/components/ui/button";
import { Punto, type Nivel } from "@/components/ui/estado";
import type { ConexionPublica, Semaforo } from "@/lib/conectar";
import { textos } from "@/lib/textos";
import { cn } from "@/lib/utils";

const t = textos.conectar;

/**
 * Una computadora en la página de conexiones (D71): el nombre y dos renglones.
 *
 * Dos y no cuatro: al vendedor no le importa cuál de las dos sesiones de
 * Claude se cayó, le importa si tiene que hacer algo. Y si la computadora está
 * dormida o apagada, los renglones no se muestran: lo que diga la última vez
 * que habló puede ser viejo, y lo único que el vendedor puede hacer es ir a
 * despertarla.
 */
export function TarjetaDeConexion({
  conexion,
  ocupado,
  onReconectar,
}: {
  conexion: ConexionPublica;
  ocupado: boolean;
  onReconectar: (tipo: "whatsapp" | "claude") => void;
}) {
  return (
    <section
      aria-label={conexion.nombre}
      className="space-y-3 rounded-2xl border bg-card p-5 sombra-suave"
    >
      <h2 className="text-2xl font-semibold">{conexion.nombre}</h2>
      {conexion.estado === "viva" ? (
        <div className="divide-y">
          <Renglon
            nombre={t.whatsapp}
            semaforo={conexion.whatsapp}
            ocupado={ocupado}
            onReconectar={() => onReconectar("whatsapp")}
          />
          <Renglon
            nombre={t.claude}
            semaforo={conexion.claude}
            ocupado={ocupado}
            onReconectar={() => onReconectar("claude")}
          />
        </div>
      ) : (
        <p className="text-lg text-muted-foreground">
          {conexion.estado === "dormida" ? t.dormida : t.apagada}
        </p>
      )}
    </section>
  );
}

const NIVEL: Record<Semaforo, Nivel> = { ok: "ok", caida: "critico", desconocido: "neutro" };
const TEXTO: Record<Semaforo, string> = {
  ok: t.conectado,
  caida: t.desconectado,
  desconocido: t.noSeSabe,
};

function Renglon({
  nombre,
  semaforo,
  ocupado,
  onReconectar,
}: {
  nombre: string;
  semaforo: Semaforo;
  ocupado: boolean;
  onReconectar: () => void;
}) {
  return (
    <div className="space-y-3 py-3">
      <div className="flex items-center justify-between gap-3 text-lg">
        <span className="font-medium">{nombre}</span>
        <span
          className={cn(
            "inline-flex items-center gap-2",
            semaforo === "ok" && "text-ok",
            semaforo === "caida" && "font-semibold text-critico",
            semaforo === "desconocido" && "text-muted-foreground",
          )}
        >
          <Punto nivel={NIVEL[semaforo]} className="size-3.5 [&>span]:size-3.5" />
          {TEXTO[semaforo]}
        </span>
      </div>
      {semaforo === "caida" && (
        <BotonGrande
          disabled={ocupado}
          onClick={onReconectar}
          aria-label={`${t.volverAConectar} ${nombre}`}
        >
          {ocupado ? t.pidiendo : t.volverAConectar}
        </BotonGrande>
      )}
    </div>
  );
}

/**
 * El botón de esta página: alto, a todo el ancho y con letra grande, para un
 * dedo y no para un mouse. Es el `Button` de siempre con otras medidas.
 */
export function BotonGrande({
  className,
  variant = "default",
  ...resto
}: React.ComponentProps<typeof Button>) {
  return (
    <Button
      variant={variant}
      className={cn("h-14 w-full rounded-xl text-lg", className)}
      {...resto}
    />
  );
}
