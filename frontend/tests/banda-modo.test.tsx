import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BandaModo } from "@/components/banda-modo";

/**
 * La banda de modo.
 *
 * Lo que se prueba acá no es cómo se ve: es **de qué depende**. La regla R4 dice
 * que a quién puede escribirle el sistema lo gobierna la lista de destinos
 * permitidos y no la variable de entorno, y esta banda es donde esa regla se le
 * comunica a una persona. Un servidor de producción con la lista cerrada sigue
 * sin poder alcanzar a nadie, y la pantalla tiene que decir eso.
 *
 * El día que alguien "mejore" esto atándolo a `ENTORNO`, este test se pone en
 * rojo. Ese es todo su trabajo.
 */
describe("BandaModo", () => {
  it("con la lista cerrada dice que no le puede escribir a nadie", () => {
    render(<BandaModo destinosAbiertos={false} />);

    expect(screen.getByText(/modo prueba/i)).toBeInTheDocument();
    // `status` y no `alert`: el modo protegido es el estado normal y no
    // interrumpe a nadie. Un cartel que interrumpe todo el tiempo se ignora.
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("con la lista abierta avisa que puede alcanzar a un cliente real", () => {
    render(<BandaModo destinosAbiertos />);

    expect(screen.getByText(/envío real habilitado/i)).toBeInTheDocument();
    // Éste sí interrumpe: es la única situación del panel en la que hay algo
    // que temer.
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
