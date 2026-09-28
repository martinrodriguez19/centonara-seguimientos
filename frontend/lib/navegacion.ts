import {
  Activity,
  AlertTriangle,
  BarChart3,
  Cpu,
  FileCheck2,
  History,
  Home,
  MessageSquareText,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Terminal,
  type LucideIcon,
} from "lucide-react";

import { textos } from "@/lib/textos";

/**
 * Lo que hay en la barra de arriba (D54): tres grupos, y nada más.
 *
 * Antes eran cuatro links sueltos, el freno, el tema y salir, todos al mismo
 * nivel, y las páginas que existían sin link (una corrida, una revisión) sólo
 * se alcanzaban desde otra pantalla. Agrupar deja ver de un vistazo qué hay sin
 * leer ocho palabras.
 *
 * Vive en un archivo aparte de la barra para que el menú de celular, la barra
 * y el test lean la misma lista.
 */
export type Destino = {
  href: string;
  titulo: string;
  ayuda: string;
  icono: LucideIcon;
  /** Se marca como actual también en sus subrutas (`/maquinas/mac-rocio`). */
  prefijo?: string;
  /** El contador de "Errores y avisos". */
  contador?: "errores";
};

export type Grupo = {
  clave: "operacion" | "analisis" | "ajustes";
  titulo: string;
  destinos: Destino[];
};

export const SECCIONES_CONFIG = ["envio", "lectura", "mensajes", "seguridad", "sistema"] as const;
export type SeccionConfig = (typeof SECCIONES_CONFIG)[number];

const ICONOS_CONFIG: Record<SeccionConfig, LucideIcon> = {
  envio: Send,
  lectura: Search,
  mensajes: MessageSquareText,
  seguridad: ShieldCheck,
  sistema: Settings2,
};

/** `ultimaCorrida` es opcional: sin ninguna corrida, "Revisar la última" no aparece. */
export function grupos(ultimaCorrida: string | null = null): Grupo[] {
  const operacion: Destino[] = [
    { href: "/panel", titulo: textos.navegacion.inicio, ayuda: textos.navegacion.inicioAyuda, icono: Home },
    {
      href: "/maquinas",
      prefijo: "/maquinas",
      titulo: textos.navegacion.maquinas,
      ayuda: textos.navegacion.maquinasAyuda,
      icono: Cpu,
    },
    {
      href: "/corridas",
      prefijo: "/corrida",
      titulo: textos.navegacion.corridas,
      ayuda: textos.navegacion.corridasAyuda,
      icono: Activity,
    },
  ];
  if (ultimaCorrida) {
    operacion.push({
      href: `/revision/${ultimaCorrida}`,
      prefijo: "/revision",
      titulo: textos.navegacion.revision,
      ayuda: textos.navegacion.revisionAyuda,
      icono: FileCheck2,
    });
  }

  return [
    { clave: "operacion", titulo: textos.navegacion.operacion, destinos: operacion },
    {
      clave: "analisis",
      titulo: textos.navegacion.analisis,
      destinos: [
        {
          href: "/estadisticas",
          titulo: textos.navegacion.estadisticas,
          ayuda: textos.navegacion.estadisticasAyuda,
          icono: BarChart3,
        },
        {
          href: "/errores",
          titulo: textos.navegacion.errores,
          ayuda: textos.navegacion.erroresAyuda,
          icono: AlertTriangle,
          contador: "errores",
        },
        {
          href: "/historial",
          titulo: textos.navegacion.historial,
          ayuda: textos.navegacion.historialAyuda,
          icono: History,
        },
      ],
    },
    {
      clave: "ajustes",
      titulo: textos.navegacion.ajustes,
      destinos: [
        ...SECCIONES_CONFIG.map((seccion) => ({
          href: `/config/${seccion}`,
          titulo: textos.config.secciones[seccion].titulo,
          ayuda: textos.config.secciones[seccion].ayuda,
          icono: ICONOS_CONFIG[seccion],
        })),
        {
          href: "/comandos",
          titulo: textos.navegacion.comandos,
          ayuda: textos.navegacion.comandosAyuda,
          icono: Terminal,
        },
      ],
    },
  ];
}

export const iconoDeSeccion = (seccion: SeccionConfig) => ICONOS_CONFIG[seccion];

/** Si `ruta` es este destino o una subruta suya. */
export function esActual(destino: Destino, ruta: string): boolean {
  if (ruta === destino.href) return true;
  const prefijo = destino.prefijo;
  return prefijo ? ruta === prefijo || ruta.startsWith(`${prefijo}/`) : false;
}

/** El grupo al que pertenece la página actual, para marcarlo en la barra. */
export function grupoActual(lista: Grupo[], ruta: string): Grupo["clave"] | null {
  if (ruta.startsWith("/config")) return "ajustes";
  return lista.find((g) => g.destinos.some((d) => esActual(d, ruta)))?.clave ?? null;
}
