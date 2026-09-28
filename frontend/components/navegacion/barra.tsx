"use client";

import { useMutation } from "@tanstack/react-query";
import { ChevronDown, LogOut, Menu, UserRound, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { DropdownMenu } from "radix-ui";
import { useEffect, useState } from "react";

import { KillSwitch } from "@/components/kill-switch";
import { ChipModo } from "@/components/navegacion/chip-modo";
import { Button } from "@/components/ui/button";
import { useEstado, useProblemas } from "@/lib/consultas";
import { esActual, grupoActual, grupos, type Destino, type Grupo } from "@/lib/navegacion";
import { ErrorDeApi, salir } from "@/lib/panel";
import { textos } from "@/lib/textos";
import { cn } from "@/lib/utils";

/**
 * La barra de arriba, la misma en todas las pantallas (D54).
 *
 * Tres menús (Operación, Análisis, Ajustes) y a la derecha sólo tres cosas: el
 * chip de modo, el freno y la cuenta. **El freno se queda a la vista**: no es
 * una alerta sino un control de seguridad, y un freno al que hay que ir a
 * buscar no es un freno.
 *
 * Lo que se fue: la banda roja de todo el ancho (ahora es el chip), el
 * selector de tema (el panel es sólo claro, D55) y los cuatro links sueltos.
 * Los errores ya no se pintan acá: se cuentan, con un número chico en
 * "Análisis", y se miran en su página.
 */
export function Barra() {
  const ruta = usePathname();
  const router = useRouter();
  const estado = useEstado();
  const problemas = useProblemas();
  const [menuAbierto, setMenuAbierto] = useState(false);

  // La cookie dura una jornada. Si venció con la pestaña abierta, el
  // reintento automático devolvería 401 para siempre: mejor mandar al login
  // que dejar una pantalla congelada sin explicación. Vive acá porque la barra
  // está en todas las páginas.
  useEffect(() => {
    if (estado.error instanceof ErrorDeApi && estado.error.esSesionVencida) {
      router.push("/login");
    }
  }, [estado.error, router]);

  // Al navegar, el menú de celular se cierra solo.
  useEffect(() => setMenuAbierto(false), [ruta]);

  const cerrarSesion = useMutation({
    mutationFn: salir,
    onSuccess: () => {
      router.push("/login");
      router.refresh();
    },
  });

  const datos = estado.data;
  const lista = grupos(datos?.ultima_corrida?.id ?? null);
  const actual = grupoActual(lista, ruta);
  const pendientes = problemas.nuevos.length;

  return (
    <header className="sticky top-0 z-40 border-b bg-card/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:px-6">
        <Link
          href="/panel"
          className="mr-2 flex items-center gap-2 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="grid size-7 place-items-center rounded-lg bg-foreground" aria-hidden>
            <span className="size-2.5 rounded-sm bg-accion" />
          </span>
          <span className="text-sm font-semibold tracking-tight">{textos.navegacion.marca}</span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Principal">
          {lista.map((grupo) => (
            <MenuDeGrupo
              key={grupo.clave}
              grupo={grupo}
              ruta={ruta}
              activo={actual === grupo.clave}
              pendientes={pendientes}
              urgentes={problemas.urgentes}
            />
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {datos && (
            <>
              <ChipModo
                destinosAbiertos={datos.destinos_abiertos}
                envioAutomatico={datos.envio_automatico}
                destinosPermitidos={datos.destinos_permitidos}
              />
              <KillSwitch pausado={datos.pausa_global} />
            </>
          )}

          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button variant="ghost" size="icon" aria-label={textos.navegacion.cuenta} className="hidden md:inline-flex">
                <UserRound className="size-4" aria-hidden />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="end" sideOffset={8} className={CAJA_MENU}>
                <DropdownMenu.Item
                  className={ITEM_MENU}
                  disabled={cerrarSesion.isPending}
                  onSelect={() => cerrarSesion.mutate()}
                >
                  <LogOut className="size-4 text-muted-foreground" aria-hidden />
                  {textos.navegacion.salir}
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>

          <Button
            variant="ghost"
            size="icon"
            className="relative md:hidden"
            aria-expanded={menuAbierto}
            aria-label={menuAbierto ? textos.navegacion.cerrarMenu : textos.navegacion.menu}
            onClick={() => setMenuAbierto((abierto) => !abierto)}
          >
            {menuAbierto ? <X className="size-5" aria-hidden /> : <Menu className="size-5" aria-hidden />}
            {!menuAbierto && pendientes > 0 && (
              <Contador cuantos={pendientes} urgente={problemas.urgentes > 0} className="absolute -top-0.5 -right-0.5" />
            )}
          </Button>
        </div>
      </div>

      {menuAbierto && (
        <nav className="max-h-[calc(100svh-3.5rem)] overflow-y-auto border-t bg-card md:hidden" aria-label="Principal">
          <div className="mx-auto max-w-6xl space-y-4 px-4 py-4">
            {lista.map((grupo) => (
              <div key={grupo.clave} className="space-y-1">
                <p className="px-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                  {grupo.titulo}
                </p>
                {grupo.destinos.map((destino) => (
                  <EnlaceDeDestino
                    key={destino.href}
                    destino={destino}
                    actual={esActual(destino, ruta)}
                    pendientes={pendientes}
                    urgentes={problemas.urgentes}
                  />
                ))}
              </div>
            ))}
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-sm hover:bg-muted"
              disabled={cerrarSesion.isPending}
              onClick={() => cerrarSesion.mutate()}
            >
              <LogOut className="size-4 text-muted-foreground" aria-hidden />
              {textos.navegacion.salir}
            </button>
          </div>
        </nav>
      )}
    </header>
  );
}

const CAJA_MENU =
  "z-50 min-w-64 rounded-xl border bg-popover p-1.5 text-popover-foreground shadow-lg outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95";

const ITEM_MENU =
  "flex cursor-default items-center gap-3 rounded-lg px-2.5 py-2 text-sm outline-none select-none data-[disabled]:opacity-50 data-[highlighted]:bg-muted";

function MenuDeGrupo({
  grupo,
  ruta,
  activo,
  pendientes,
  urgentes,
}: {
  grupo: Grupo;
  ruta: string;
  activo: boolean;
  pendientes: number;
  urgentes: number;
}) {
  const conContador = grupo.destinos.some((d) => d.contador === "errores") && pendientes > 0;
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger
        className={cn(
          "relative inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-muted",
          activo ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {grupo.titulo}
        {conContador && <Contador cuantos={pendientes} urgente={urgentes > 0} />}
        <ChevronDown className="size-3.5 opacity-60" aria-hidden />
        {activo && <span className="absolute inset-x-3 -bottom-[11px] h-0.5 rounded-full bg-accion" aria-hidden />}
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="start" sideOffset={8} className={cn(CAJA_MENU, "w-80")}>
          {grupo.destinos.map((destino) => {
            const Icono = destino.icono;
            const esEste = esActual(destino, ruta);
            return (
              <DropdownMenu.Item key={destino.href} asChild className={ITEM_MENU}>
                <Link href={destino.href} aria-current={esEste ? "page" : undefined}>
                  <span
                    className={cn(
                      "grid size-8 shrink-0 place-items-center rounded-lg border",
                      esEste ? "border-accion/40 bg-accion-suave text-accion-tinta" : "bg-card text-muted-foreground",
                    )}
                  >
                    <Icono className="size-4" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2 font-medium">
                      {destino.titulo}
                      {destino.contador === "errores" && pendientes > 0 && (
                        <Contador cuantos={pendientes} urgente={urgentes > 0} />
                      )}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">{destino.ayuda}</span>
                  </span>
                </Link>
              </DropdownMenu.Item>
            );
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function EnlaceDeDestino({
  destino,
  actual,
  pendientes,
  urgentes,
}: {
  destino: Destino;
  actual: boolean;
  pendientes: number;
  urgentes: number;
}) {
  const Icono = destino.icono;
  return (
    <Link
      href={destino.href}
      aria-current={actual ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-lg px-2 py-2 text-sm",
        actual ? "bg-accion-suave font-medium text-accion-tinta" : "hover:bg-muted",
      )}
    >
      <Icono className="size-4 shrink-0" aria-hidden />
      <span className="flex-1">{destino.titulo}</span>
      {destino.contador === "errores" && pendientes > 0 && <Contador cuantos={pendientes} urgente={urgentes > 0} />}
    </Link>
  );
}

/**
 * El número chico de "Errores y avisos".
 *
 * Neutro si todo es para mirar después; rojo si hay algo urgente. Nada más: el
 * detalle está en la página, no en la barra.
 */
function Contador({ cuantos, urgente, className }: { cuantos: number; urgente: boolean; className?: string }) {
  return (
    <span
      aria-label={textos.navegacion.pendientes(cuantos)}
      className={cn(
        "inline-grid h-4 min-w-4 place-items-center rounded-full px-1 font-mono text-[10px] leading-none font-semibold tabular-nums",
        urgente ? "bg-critico text-primary-foreground" : "bg-muted-foreground/15 text-foreground",
        className,
      )}
    >
      {cuantos > 99 ? "99+" : cuantos}
    </span>
  );
}
