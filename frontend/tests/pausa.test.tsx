import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MenuDeAcciones, useAccionesDeMaquina } from "@/components/maquinas/acciones";
import { ProveedorDeAvisos } from "@/components/ui/avisos-flotantes";
import type { Maquina } from "@/lib/panel";

/**
 * "Pausar por hoy" y "Quitar la pausa".
 *
 * El backend ignora los campos en `null` del PATCH y contesta 400 "no hay nada
 * que cambiar": mandar `pausado_hasta: null` para quitar la pausa nunca
 * funcionó (30/09/2026). Quitar la pausa es mandar una fecha **pasada**. Este
 * test es lo que impide volver al `null`.
 */
const editar = vi.hoisted(() => vi.fn());

vi.mock("@/lib/panel", async () => {
  const real = await vi.importActual<typeof import("@/lib/panel")>("@/lib/panel");
  return { ...real, editarMaquina: editar };
});

const MAQUINA: Maquina = {
  maquina: "mac-lautaro",
  nombre: "Lautaro",
  activo: true,
  pausada: true,
  online: true,
  ultimo_latido: new Date().toISOString(),
  puede_enviar: true,
  chequeos_fallando: [],
  diagnostico: {},
  version_agente: null,
  version_esperada: null,
  actualizada: null,
  modo_agente: "operativo",
  tope_diario: 20,
};

function Menu({ maquina }: { maquina: Maquina }) {
  const acciones = useAccionesDeMaquina(maquina);
  return <MenuDeAcciones maquina={maquina} acciones={acciones} />;
}

function montar(maquina: Maquina) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <ProveedorDeAvisos>
        <Menu maquina={maquina} />
      </ProveedorDeAvisos>
    </QueryClientProvider>,
  );
}

describe("la pausa de una máquina", () => {
  beforeEach(() => {
    editar.mockReset();
    editar.mockResolvedValue({ ok: true });
  });

  it("quitar la pausa manda una fecha pasada, nunca null", async () => {
    montar(MAQUINA);
    await userEvent.click(screen.getByRole("button", { name: /acciones/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /quitar la pausa/i }));

    await waitFor(() => expect(editar).toHaveBeenCalledTimes(1));
    const [, cambios] = editar.mock.calls[0];
    expect(cambios.pausado_hasta).not.toBeNull();
    expect(new Date(cambios.pausado_hasta).getTime()).toBeLessThan(Date.now());
    await screen.findByText(/pausa quitada/i);
  });

  it("pausar por hoy manda el fin del día", async () => {
    montar({ ...MAQUINA, pausada: false });
    await userEvent.click(screen.getByRole("button", { name: /acciones/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /pausar por hoy/i }));

    await waitFor(() => expect(editar).toHaveBeenCalledTimes(1));
    const hasta = new Date(editar.mock.calls[0][1].pausado_hasta);
    expect(hasta.getTime()).toBeGreaterThan(Date.now());
    expect(hasta.getHours()).toBe(23);
  });
});
