import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SeccionEnvio } from "@/components/config/envio";
import { ProveedorDeAvisos } from "@/components/ui/avisos-flotantes";
import type { Configuracion } from "@/lib/panel";

/**
 * El envío automático como switch (D52, D56).
 *
 * Es el control que hace que un mensaje salga sin que una persona lo mire. El
 * dueño pidió que fuera "tan simple como un switch", y lo es — pero **prender
 * pasa por un diálogo**. Estos tests son lo que impide que alguien lo
 * "simplifique" hasta que un click distraído lo prenda.
 */
const guardar = vi.hoisted(() => vi.fn());

vi.mock("@/lib/panel", async () => {
  const real = await vi.importActual<typeof import("@/lib/panel")>("@/lib/panel");
  return { ...real, guardarConfiguracion: guardar };
});

const CONFIG = {
  envio_automatico: false,
  modo_borrador: "extension",
  destinos_permitidos: ["+5491144405036"],
  ventana: { inicio: "09:00", fin: "19:00", dias: [1, 2, 3, 4, 5] },
  programacion: { activa: false, hora: "17:00", dias: [1, 2, 3, 4, 5] },
  pausa_entre_envios_s: [45, 180],
} as unknown as Configuracion;

function montar(config: Configuracion) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  cliente.setQueryData(["configuracion"], config);
  return render(
    <QueryClientProvider client={cliente}>
      <ProveedorDeAvisos>
        <SeccionEnvio config={config} />
      </ProveedorDeAvisos>
    </QueryClientProvider>,
  );
}

describe("envío automático", () => {
  beforeEach(() => {
    guardar.mockReset();
    guardar.mockImplementation(async (cambios: Partial<Configuracion>) => ({ ...CONFIG, ...cambios }));
  });

  it("prender abre el diálogo y no guarda nada hasta confirmar", async () => {
    montar(CONFIG);
    await userEvent.click(screen.getByRole("switch", { name: /envío automático/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/sin que nadie los revise/i)).toBeInTheDocument();
    expect(guardar).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /^prender$/i }));
    await waitFor(() => expect(guardar).toHaveBeenCalledWith({ envio_automatico: true }));
  });

  it("cancelar el diálogo no prende nada", async () => {
    montar(CONFIG);
    await userEvent.click(screen.getByRole("switch", { name: /envío automático/i }));
    await userEvent.click(screen.getByRole("button", { name: /cancelar/i }));
    expect(guardar).not.toHaveBeenCalled();
  });

  it("apagar no pide nada, y no ofrece deshacer (deshacer sería prender sin diálogo)", async () => {
    montar({ ...CONFIG, envio_automatico: true });
    await userEvent.click(screen.getByRole("switch", { name: /envío automático/i }));

    await waitFor(() => expect(guardar).toHaveBeenCalledWith({ envio_automatico: false }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await screen.findByText(/envío automático apagado/i);
    expect(screen.queryByRole("button", { name: /deshacer/i })).not.toBeInTheDocument();
  });

  it("sin el pase único no se puede prender", () => {
    montar({ ...CONFIG, modo_borrador: "playwright" });
    expect(screen.getByRole("switch", { name: /envío automático/i })).toBeDisabled();
  });

  it("los demás ajustes sí ofrecen deshacer", async () => {
    montar(CONFIG);
    await userEvent.click(screen.getByRole("switch", { name: /corrida automática/i }));
    await waitFor(() =>
      expect(guardar).toHaveBeenCalledWith({ programacion: { activa: true, hora: "17:00", dias: [1, 2, 3, 4, 5] } }),
    );
    await userEvent.click(await screen.findByRole("button", { name: /deshacer/i }));
    await waitFor(() => expect(guardar).toHaveBeenLastCalledWith({ programacion: CONFIG.programacion }));
  });
});
