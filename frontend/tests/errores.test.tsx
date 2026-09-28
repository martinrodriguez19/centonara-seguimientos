import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ListaDeErrores } from "@/components/errores/lista";
import { _olvidarCache } from "@/lib/vistos";

/**
 * La lista de errores y avisos (Panel v2): lo que antes se pintaba entero
 * arriba del inicio. Lo que se prueba es lo que la hace usable: el filtro por
 * máquina (con el campo `maquina` de la alerta, no leyendo el título) y que
 * "Ya lo vi" saque de la vista sin hacer desaparecer.
 */
vi.mock("@/lib/panel", async () => {
  const real = await vi.importActual<typeof import("@/lib/panel")>("@/lib/panel");
  return {
    ...real,
    traerEstado: vi.fn().mockResolvedValue({
      maquinas: [
        { maquina: "mac-rocio", nombre: "Rocío", activo: true, pausada: false, online: true, puede_enviar: true, chequeos_fallando: [], diagnostico: {}, modo_agente: "operativo" },
      ],
    }),
    traerAlertas: vi.fn().mockResolvedValue({
      urgentes: 1,
      alertas: [
        { nivel: "urgente", codigo: "selector_roto", titulo: "WhatsApp Web cambió", detalle: "3 envíos fallaron", accion: "Actualizar selectores", corrida_id: null, maquina: null },
        { nivel: "aviso", codigo: "maquina_degradada", titulo: "Rocío está a medias", detalle: "No pasa: chrome", accion: "Resolver", corrida_id: null, maquina: "mac-rocio" },
      ],
    }),
  };
});

function montar(filtro: string | null = null) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <ListaDeErrores filtro={filtro} />
    </QueryClientProvider>,
  );
}

describe("ListaDeErrores", () => {
  beforeEach(() => {
    localStorage.clear();
    _olvidarCache();
  });

  it("separa lo urgente de lo que se puede mirar después", async () => {
    montar();
    expect(await screen.findByRole("region", { name: "Urgente" })).toHaveTextContent("WhatsApp Web cambió");
    expect(screen.getByRole("region", { name: "Para mirar" })).toHaveTextContent("Rocío está a medias");
  });

  it("filtra por máquina con el campo de la alerta", async () => {
    montar("mac-rocio");
    expect(await screen.findByText("Rocío está a medias")).toBeInTheDocument();
    expect(screen.queryByText("WhatsApp Web cambió")).not.toBeInTheDocument();
  });

  it("'sistema' deja sólo lo que no es de ninguna máquina", async () => {
    montar("sistema");
    expect(await screen.findByText("WhatsApp Web cambió")).toBeInTheDocument();
    expect(screen.queryByText("Rocío está a medias")).not.toBeInTheDocument();
  });

  it("'Ya lo vi' lo pasa a los vistos, no lo hace desaparecer", async () => {
    montar();
    await screen.findByText("WhatsApp Web cambió");
    const [primero] = screen.getAllByRole("button", { name: /ya lo vi/i });
    await userEvent.click(primero);

    expect(screen.queryByRole("region", { name: "Urgente" })).not.toBeInTheDocument();
    expect(screen.getByText(/ya vistos \(1\)/i)).toBeInTheDocument();
  });
});
