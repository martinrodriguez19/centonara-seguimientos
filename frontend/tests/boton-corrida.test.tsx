import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BotonCorrida } from "@/components/boton-corrida";

/**
 * El botón que arranca el sistema.
 *
 * ⚠️ **El primer test es una regresión de un bug real.** El panel tenía un solo
 * botón y llamaba siempre a `dispararCorrida("diagnostico")`. El texto "Generar
 * seguimientos" estaba escrito en `lib/textos.ts` y no lo referenciaba ningún
 * componente. Resultado: el producto —generar borradores— no se podía pedir
 * desde el panel, y el instructivo de instalación le prometía al cliente que
 * apretando ese botón aparecían los borradores.
 *
 * Nada rompía, nada estaba en rojo, y nadie lo veía. De ahí el test.
 */
const disparar = vi.hoisted(() => vi.fn());
const cancelar = vi.hoisted(() => vi.fn());

vi.mock("@/lib/panel", async () => {
  const real = await vi.importActual<typeof import("@/lib/panel")>("@/lib/panel");
  return {
    ...real,
    dispararCorrida: disparar,
    cancelarCorrida: cancelar,
    traerConfiguracion: vi.fn().mockResolvedValue({ n_chats_por_defecto: 20 }),
  };
});

function envolver(nodo: React.ReactNode) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={cliente}>{nodo}</QueryClientProvider>;
}

const base = { maquinas: 2, pausado: false, enCurso: null, ultima: null };

describe("BotonCorrida", () => {
  beforeEach(() => {
    disparar.mockReset().mockResolvedValue({ id: "abc", maquinas: ["mac-1"], jobs: 1 });
    cancelar.mockReset();
  });

  it("ofrece generar seguimientos, que es lo que hace el producto", () => {
    render(envolver(<BotonCorrida {...base} />));
    expect(screen.getByRole("button", { name: /generar seguimientos/i })).toBeInTheDocument();
  });

  it("generar confirma primero, y recién ahí dispara una generación", async () => {
    render(envolver(<BotonCorrida {...base} />));

    await userEvent.click(screen.getByRole("button", { name: /generar seguimientos/i }));
    // Todavía no salió nada: primero hay que leer cuánto trabajo se está
    // pidiendo, porque se paga por chat leído.
    expect(disparar).not.toHaveBeenCalled();
    expect(screen.getByText(/vas a generar seguimientos/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^generar$/i }));
    expect(disparar).toHaveBeenCalledWith("generacion");
  });

  it("el diagnóstico sale sin fricción, porque es gratis y no toca ningún chat", async () => {
    render(envolver(<BotonCorrida {...base} />));

    await userEvent.click(screen.getByRole("button", { name: /correr diagnóstico/i }));
    expect(disparar).toHaveBeenCalledWith("diagnostico");
  });

  it("sin máquinas activas no se puede disparar nada, y dice por qué", () => {
    render(envolver(<BotonCorrida {...base} maquinas={0} />));

    expect(screen.getByRole("button", { name: /generar seguimientos/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /correr diagnóstico/i })).toBeDisabled();
    expect(screen.getByText(/no hay ninguna máquina activa/i)).toBeInTheDocument();
  });

  it("con el kill switch puesto tampoco", () => {
    render(envolver(<BotonCorrida {...base} pausado />));
    expect(screen.getByRole("button", { name: /generar seguimientos/i })).toBeDisabled();
  });
});
