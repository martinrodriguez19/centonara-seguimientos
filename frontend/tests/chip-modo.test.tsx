import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ChipModo, modoDe } from "@/components/navegacion/chip-modo";

/**
 * El chip de modo, que reemplazó a la banda de todo el ancho (D54).
 *
 * Lo que se prueba no es cómo se ve: es **de qué depende**. La regla R4 dice
 * que a quién puede escribirle el sistema lo gobierna la lista de destinos
 * permitidos y no la variable de entorno, y este chip es donde esa regla se le
 * comunica a una persona. El envío automático (D52) manda sobre todo lo demás.
 *
 * El día que alguien "mejore" esto atándolo a `ENTORNO`, este test se pone en
 * rojo. Ese es todo su trabajo.
 */
describe("modoDe", () => {
  it("lo decide la lista de destinos, y el envío automático manda", () => {
    expect(modoDe(false, false)).toBe("prueba");
    expect(modoDe(true, false)).toBe("real");
    expect(modoDe(false, true)).toBe("automatico");
    expect(modoDe(true, true)).toBe("automatico");
  });
});

describe("ChipModo", () => {
  it("con la lista cerrada dice a cuántos números puede escribir", async () => {
    render(<ChipModo destinosAbiertos={false} envioAutomatico={false} destinosPermitidos={2} />);

    const chip = screen.getByRole("button", { name: /modo del sistema: prueba/i });
    await userEvent.click(chip);
    expect(screen.getByText(/sólo le puede escribir a los 2 números/i)).toBeInTheDocument();
  });

  it("con la lista vacía dice que no le puede escribir a nadie", async () => {
    render(<ChipModo destinosAbiertos={false} envioAutomatico={false} destinosPermitidos={0} />);

    await userEvent.click(screen.getByRole("button", { name: /prueba/i }));
    expect(screen.getByText(/no le puede escribir a nadie/i)).toBeInTheDocument();
  });

  it("con la lista abierta avisa que puede alcanzar a cualquier contacto", async () => {
    render(<ChipModo destinosAbiertos envioAutomatico={false} destinosPermitidos={0} />);

    await userEvent.click(screen.getByRole("button", { name: /modo del sistema: envío real/i }));
    expect(screen.getByText(/cualquier contacto/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /cambiarlo/i })).toHaveAttribute("href", "/config/seguridad");
  });

  it("con el envío automático lo dice, y manda a cambiarlo donde se prende", async () => {
    render(<ChipModo destinosAbiertos={false} envioAutomatico destinosPermitidos={3} />);

    await userEvent.click(screen.getByRole("button", { name: /modo del sistema: envío automático/i }));
    expect(screen.getByText(/sin que nadie los revise/i)).toBeInTheDocument();
    expect(screen.getByText(/sólo a los números de la lista/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /cambiarlo/i })).toHaveAttribute("href", "/config/envio");
  });
});
