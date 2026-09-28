"use client";

import { notFound } from "next/navigation";
import { use } from "react";

import { SeccionEnvio } from "@/components/config/envio";
import { SeccionLectura } from "@/components/config/lectura";
import { SeccionMensajes } from "@/components/config/mensajes";
import { SeccionSeguridad } from "@/components/config/seguridad";
import { SeccionSistema } from "@/components/config/sistema";
import { ErrorDeCarga } from "@/components/error-de-carga";
import { EsqueletoDeLista } from "@/components/ui/esqueleto";
import { useConfiguracion } from "@/lib/consultas";
import { SECCIONES_CONFIG, type SeccionConfig } from "@/lib/navegacion";
import type { Configuracion } from "@/lib/panel";

const SECCIONES: Record<SeccionConfig, (props: { config: Configuracion }) => React.ReactNode> = {
  envio: SeccionEnvio,
  lectura: SeccionLectura,
  mensajes: SeccionMensajes,
  seguridad: SeccionSeguridad,
  sistema: SeccionSistema,
};

/** Una sección de Ajustes. Todas leen la misma `GET /configuracion`. */
export default function SeccionDeAjustes({ params }: { params: Promise<{ seccion: string }> }) {
  const { seccion } = use(params);
  const config = useConfiguracion();

  if (!(SECCIONES_CONFIG as readonly string[]).includes(seccion)) notFound();
  const Seccion = SECCIONES[seccion as SeccionConfig];

  if (config.isPending) return <EsqueletoDeLista filas={3} />;
  if (config.isError) return <ErrorDeCarga error={config.error} onReintentar={() => void config.refetch()} />;
  return <Seccion config={config.data} />;
}
