"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Stethoscope } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAvisos } from "@/components/ui/avisos-flotantes";
import { Button } from "@/components/ui/button";
import { iconoDeSeccion, SECCIONES_CONFIG } from "@/lib/navegacion";
import { dispararCorrida } from "@/lib/panel";
import { textos } from "@/lib/textos";
import { cn } from "@/lib/utils";

/**
 * El menú de las secciones de Ajustes (D56): a la izquierda en pantalla
 * ancha, arriba y deslizable en el celular.
 */
export function MenuDeAjustes() {
  const ruta = usePathname();
  return (
    <nav aria-label={textos.config.titulo} className="-mx-4 overflow-x-auto px-4 lg:mx-0 lg:overflow-visible lg:px-0">
      <ul className="flex gap-1 lg:flex-col">
        {SECCIONES_CONFIG.map((seccion) => {
          const Icono = iconoDeSeccion(seccion);
          const href = `/config/${seccion}`;
          const actual = ruta === href;
          return (
            <li key={seccion}>
              <Link
                href={href}
                aria-current={actual ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm whitespace-nowrap transition-colors lg:items-start lg:whitespace-normal",
                  actual ? "bg-card font-medium text-foreground ring-1 ring-border sombra-suave" : "text-muted-foreground hover:bg-card hover:text-foreground",
                )}
              >
                <Icono className={cn("size-4 shrink-0 lg:mt-0.5", actual && "text-accion-tinta")} aria-hidden />
                <span className="min-w-0 lg:flex lg:flex-col">
                  {textos.config.secciones[seccion].titulo}
                  <span className="hidden text-xs font-normal text-muted-foreground lg:block">
                    {textos.config.secciones[seccion].ayuda}
                  </span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/**
 * Probar las máquinas desde Ajustes: el mismo diagnóstico del botón del inicio.
 * Es gratis y no toca ningún chat, así que no confirma nada.
 */
export function ProbarMaquinas() {
  const clienteQuery = useQueryClient();
  const { avisar } = useAvisos();
  const probar = useMutation({
    mutationFn: () => dispararCorrida("diagnostico"),
    onSuccess: () => avisar(textos.config.avisoProbando),
    onError: (error) => avisar(`${textos.config.falloAccion} ${error.message}`, "critico"),
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["estado"] }),
  });
  return (
    <Button variant="outline" size="sm" disabled={probar.isPending} onClick={() => probar.mutate()} title={textos.boton.diagnosticoAyuda}>
      <Stethoscope className="size-4" aria-hidden />
      {textos.config.probarMaquinas}
    </Button>
  );
}
