"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

export type Tema = "claro" | "oscuro" | "sistema";

const CLAVE = "tema";

/**
 * Aplica un tema al documento y lo recuerda.
 *
 * `sistema` no guarda nada: borra la preferencia y vuelve a mirar el sistema
 * operativo. Es el estado de fábrica, y tiene que poder volverse a él.
 */
function aplicar(tema: Tema) {
  const oscuroDelSistema =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;

  const oscuro = tema === "oscuro" || (tema === "sistema" && oscuroDelSistema);
  document.documentElement.classList.toggle("dark", oscuro);

  try {
    if (tema === "sistema") localStorage.removeItem(CLAVE);
    else localStorage.setItem(CLAVE, tema);
  } catch {
    // Sin localStorage el tema no persiste, y no pasa nada más: la clase ya
    // está aplicada para esta pestaña.
  }
}

function leerGuardado(): Tema {
  try {
    const guardado = localStorage.getItem(CLAVE);
    if (guardado === "claro" || guardado === "oscuro") return guardado;
  } catch {
    /* Sin localStorage, sistema. */
  }
  return "sistema";
}

/**
 * El selector de tema: claro, oscuro, o lo que diga la Mac.
 *
 * Tres estados y no dos. Un interruptor de dos posiciones obliga a elegir uno
 * de los dos para siempre, y en una Mac que cambia sola al atardecer eso se
 * siente como que el panel dejó de seguir al sistema.
 *
 * El tema **ya está aplicado** antes de que esto monte: lo hace el script en
 * línea de `app/layout.tsx`, para que no haya destello. Este componente sólo
 * lo cambia.
 */
export function SelectorDeTema() {
  const [tema, setTema] = useState<Tema>("sistema");
  // Hasta que monte, el servidor y el cliente no saben lo mismo. Dibujar el
  // ícono recién en el cliente evita un desajuste de hidratación.
  const [montado, setMontado] = useState(false);

  useEffect(() => {
    setTema(leerGuardado());
    setMontado(true);
  }, []);

  // Si el tema es "sistema" y la Mac cambia de claro a oscuro sola, el panel
  // tiene que acompañarla sin recargar.
  useEffect(() => {
    if (tema !== "sistema") return;
    const consulta = window.matchMedia("(prefers-color-scheme: dark)");
    const alCambiar = () => aplicar("sistema");
    consulta.addEventListener("change", alCambiar);
    return () => consulta.removeEventListener("change", alCambiar);
  }, [tema]);

  const siguiente: Record<Tema, Tema> = {
    sistema: "claro",
    claro: "oscuro",
    oscuro: "sistema",
  };

  // Con palabra y no con ícono. Un sol, una luna y un monitor obligan a
  // aprender tres símbolos, y quien usa este panel entra al mediodía a mirar
  // una cosa. "Automático" además dice lo que un monitorcito no dice.
  const etiqueta: Record<Tema, string> = {
    sistema: "Automático",
    claro: "Claro",
    oscuro: "Oscuro",
  };

  const ayuda: Record<Tema, string> = {
    sistema: "El tema sigue a la computadora. Tocá para fijarlo en claro.",
    claro: "Tema claro. Tocá para pasar a oscuro.",
    oscuro: "Tema oscuro. Tocá para volver al automático.",
  };

  return (
    <Button
      variant="ghost"
      size="sm"
      title={ayuda[tema]}
      onClick={() => {
        const nuevo = siguiente[tema];
        setTema(nuevo);
        aplicar(nuevo);
      }}
    >
      {/* Hasta que monte, el ancho se reserva para que la barra no salte. */}
      {montado ? etiqueta[tema] : <span className="inline-block w-[5.5em]" />}
    </Button>
  );
}
