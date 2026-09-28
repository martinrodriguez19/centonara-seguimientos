"use client";

import { Fila, Numero, Tarjeta, useGuardarConfiguracion } from "@/components/config/base";
import { Opciones } from "@/components/ui/opciones";
import type { Configuracion } from "@/lib/panel";

/**
 * Qué chats y cuántos: qué se lee en cada corrida y en qué orden.
 *
 * Los textos son los de la pantalla anterior, recortados: la explicación larga
 * de cada modo pasó a "¿Qué hace esto?".
 */
export function SeccionLectura({ config }: { config: Configuracion }) {
  const { guardar, guardando } = useGuardarConfiguracion();
  const modo = config.modo_lectura ?? "recientes";
  const orden = config.orden_recorrido ?? "mas_nuevos_primero";

  return (
    <>
      <Tarjeta titulo="Qué chats se siguen">
        <Fila
          titulo="Cómo se eligen"
          ayuda={
            modo === "barrido"
              ? "Va al fondo del WhatsApp y avanza del chat más viejo hacia hoy, de a tandas."
              : "Los de arriba de la lista, dentro del silencio de abajo."
          }
          queHace={
            <>
              <p>
                <strong>Los más recientes</strong>: los de arriba de la lista, dentro de la ventana de silencio.
              </p>
              <p>
                <strong>Barrido del historial</strong>: va al fondo del WhatsApp y avanza del chat más viejo hacia
                hoy, recuperando a los clientes que quedaron sin recontactar — sin repetir a nadie que ya recibió
                algo. El avance se ve en el detalle de cada máquina. Si las corridas tardan demasiado, bajá «Chats a
                leer por máquina»: la corrida siguiente continúa donde quedó.
              </p>
            </>
          }
          control={
            <Opciones
              etiqueta="Cómo se eligen los chats"
              valor={modo}
              deshabilitado={guardando}
              opciones={[
                { valor: "recientes", texto: "Los más recientes" },
                { valor: "barrido", texto: "Barrido del historial" },
              ]}
              onCambiar={(modo_lectura) => guardar({ modo_lectura })}
            />
          }
        />

        {modo === "recientes" && (
          <>
            <Fila
              titulo="Silencio mínimo"
              ayuda="Un chat más fresco que esto no se toca."
              queHace="Es hasta dónde se acerca a hoy el recorrido. Tres semanas (21) es lo pedido para el pase único."
              control={
                <Numero
                  etiqueta="Silencio mínimo en días"
                  min={0}
                  sufijo="días"
                  valor={config.antiguedad_min_dias ?? 0}
                  guardando={guardando}
                  onGuardar={(antiguedad_min_dias) => guardar({ antiguedad_min_dias })}
                />
              }
            />
            <Fila
              titulo="Silencio máximo"
              ayuda="Más viejo que esto, el contacto se considera perdido y no se le escribe."
              control={
                <Numero
                  etiqueta="Silencio máximo en días"
                  sufijo="días"
                  valor={config.antiguedad_max_dias ?? 90}
                  guardando={guardando}
                  onGuardar={(antiguedad_max_dias) => guardar({ antiguedad_max_dias })}
                />
              }
            />
            <Fila
              titulo="En qué orden se recorren"
              ayuda={
                orden === "mas_viejos_primero"
                  ? "Del extremo viejo de la ventana hacia hoy."
                  : "De arriba hacia abajo, en cada corrida."
              }
              queHace={
                orden === "mas_viejos_primero"
                  ? "Arranca en el extremo viejo de la ventana y avanza hacia hoy, frenando en el silencio mínimo. Cada máquina lleva su cursor entre corridas; se ve y se reinicia en su detalle."
                  : "Arranca arriba de la lista en cada corrida. Sin cursor: lo único que evita repetir a alguien es que ya haya recibido un mensaje hace poco."
              }
              control={
                <Opciones
                  etiqueta="Orden del recorrido"
                  valor={orden}
                  deshabilitado={guardando}
                  opciones={[
                    { valor: "mas_nuevos_primero", texto: "Nuevos primero" },
                    { valor: "mas_viejos_primero", texto: "Viejos primero" },
                  ]}
                  onCambiar={(orden_recorrido) => guardar({ orden_recorrido })}
                />
              }
            />
          </>
        )}
      </Tarjeta>

      <Tarjeta titulo="Cuánto se lee">
        <Fila
          titulo="Chats a leer por máquina"
          ayuda="En cada corrida."
          queHace="En el barrido del historial, cada corrida lee la siguiente tanda de este tamaño. Diez por corrida rinden más que veinte a medio terminar."
          control={
            <Numero
              etiqueta="Chats a leer por máquina"
              max={50}
              valor={config.n_chats_por_defecto}
              guardando={guardando}
              onGuardar={(n_chats_por_defecto) => guardar({ n_chats_por_defecto })}
            />
          }
        />
      </Tarjeta>
    </>
  );
}
