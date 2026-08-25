import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Enviar } from "@/components/enviar";

/**
 * El botón de enviar, que es el control más peligroso del panel.
 *
 * Estos cuatro tests cubren los cuatro modos de falla que importan, y los
 * cuatro ya existieron o casi existieron:
 *
 * 1. Que el modo quede escrito a mano en el código. Es el bug que tenía el
 *    panel: `enviarCorrida(corrida, "prueba")` fijo, así que enviar de verdad
 *    no se podía hacer desde ninguna pantalla.
 * 2. Que la fricción se pueda saltear. Escribir la cantidad no es decoración:
 *    es lo único que separa un click distraído de veinte mensajes a clientes.
 * 3. Que se ofrezca enviar de verdad con la lista de destinos vacía, que por
 *    R4 significa "a nadie". Apretar y que no pase nada es peor que no poder.
 * 4. Que un ensayo pida fricción. Si la pide, se usa menos — y el ensayo es
 *    justamente lo que uno quiere que se use mucho.
 */
describe("Enviar", () => {
  const props = {
    cuantos: 3,
    destinosPermitidos: 2,
    enviando: false,
  };

  it("el ensayo sale con un solo click y en modo prueba", async () => {
    const onEnviar = vi.fn();
    render(<Enviar {...props} onEnviar={onEnviar} />);

    await userEvent.click(screen.getByRole("button", { name: /ensayo/i }));

    expect(onEnviar).toHaveBeenCalledTimes(1);
    expect(onEnviar).toHaveBeenCalledWith("prueba");
  });

  it("enviar de verdad no manda nada hasta que se escribe la cantidad", async () => {
    const onEnviar = vi.fn();
    render(<Enviar {...props} onEnviar={onEnviar} />);

    await userEvent.click(screen.getByRole("button", { name: /enviar de verdad/i }));

    const confirmar = screen.getByRole("button", { name: /3 mensajes de verdad/i });
    expect(confirmar).toBeDisabled();

    // Un número que no es el correcto tampoco alcanza.
    await userEvent.type(screen.getByRole("textbox"), "2");
    expect(confirmar).toBeDisabled();
    expect(onEnviar).not.toHaveBeenCalled();
  });

  it("con la cantidad correcta, envía en modo real", async () => {
    const onEnviar = vi.fn();
    render(<Enviar {...props} onEnviar={onEnviar} />);

    await userEvent.click(screen.getByRole("button", { name: /enviar de verdad/i }));
    await userEvent.type(screen.getByRole("textbox"), "3");
    await userEvent.click(screen.getByRole("button", { name: /3 mensajes de verdad/i }));

    expect(onEnviar).toHaveBeenCalledWith("real");
  });

  it("sin destinos permitidos no se puede enviar de verdad, y dice por qué", () => {
    render(<Enviar {...props} destinosPermitidos={0} onEnviar={vi.fn()} />);

    expect(screen.getByRole("button", { name: /enviar de verdad/i })).toBeDisabled();
    expect(screen.getByText(/lista de destinos permitidos está vacía/i)).toBeInTheDocument();
    // El ensayo sigue disponible: no alcanza a nadie, así que no hay nada que
    // proteger.
    expect(screen.getByRole("button", { name: /ensayo/i })).toBeEnabled();
  });
});
