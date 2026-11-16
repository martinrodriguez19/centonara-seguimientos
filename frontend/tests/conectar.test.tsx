import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Conectar from "@/app/(publico)/conectar/page";
import { ErrorDeConexiones, pedirReconexion, traerConexiones, type Conexiones } from "@/lib/conectar";

/**
 * La página de conexiones montada (D71): lo que ve el vendedor y lo que pasa
 * al tocar el botón. La lógica fina de los pasos está en `conectar.test.ts`;
 * acá se prueba que la página la use: el pedido llega al servidor, el "¡Listo!"
 * aparece solo, el "vencida" y el 429 se dicen en palabras.
 */
vi.mock("@/lib/conectar", async () => {
  const real = await vi.importActual<typeof import("@/lib/conectar")>("@/lib/conectar");
  return { ...real, traerConexiones: vi.fn(), pedirReconexion: vi.fn() };
});

const traer = vi.mocked(traerConexiones);
const pedir = vi.mocked(pedirReconexion);

const PEDIDA = "2026-11-16T15:00:00Z";

function conexiones(sofia: Partial<Conexiones["maquinas"][number]> = {}): Conexiones {
  return {
    pedir_codigo_a: "Martina",
    maquinas: [
      { maquina: "pc-lautaro", nombre: "Lautaro", estado: "viva", whatsapp: "ok", claude: "ok", reconexion: null },
      { maquina: "pc-sofia", nombre: "Sofía", estado: "viva", whatsapp: "caida", claude: "ok", reconexion: null, ...sofia },
      { maquina: "pc-thomas", nombre: "Thomas", estado: "dormida", whatsapp: "desconocido", claude: "desconocido", reconexion: null },
    ],
  };
}

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <Conectar />
    </QueryClientProvider>,
  );
}

describe("Página de conexiones", () => {
  beforeEach(() => {
    traer.mockReset();
    pedir.mockReset();
  });

  it("una tarjeta por computadora, con el botón sólo donde está caído", async () => {
    traer.mockResolvedValue(conexiones());
    montar();

    const sofia = await screen.findByRole("region", { name: "Sofía" });
    expect(within(sofia).getByText("Desconectado")).toBeInTheDocument();
    expect(within(sofia).getByRole("button", { name: "Volver a conectar WhatsApp" })).toBeInTheDocument();

    const lautaro = screen.getByRole("region", { name: "Lautaro" });
    expect(within(lautaro).getAllByText("Conectado")).toHaveLength(2);
    expect(within(lautaro).queryByRole("button")).not.toBeInTheDocument();

    expect(screen.getByRole("region", { name: "Thomas" })).toHaveTextContent("La computadora está dormida: mové el mouse");
    // El id de la máquina viaja en la URL del pedido, pero no se muestra.
    expect(document.body).not.toHaveTextContent("pc-sofia");
  });

  it("pedido → listo: toca el botón, ve los pasos y el ¡Listo! llega solo", async () => {
    traer.mockResolvedValue(conexiones());
    pedir.mockResolvedValue({ ok: true, reconexion: { tipo: "whatsapp", pedida_en: PEDIDA, hecha: false, vencida: false } });
    montar();

    await userEvent.click(await screen.findByRole("button", { name: "Volver a conectar WhatsApp" }));
    expect(pedir).toHaveBeenCalledWith("pc-sofia", "whatsapp");
    expect(await screen.findByText(/se abrió WhatsApp con un cuadrado/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ya escaneé" })).toBeInTheDocument();

    // La máquina reporta WhatsApp conectado en el refresco siguiente.
    traer.mockResolvedValue(
      conexiones({ whatsapp: "ok", reconexion: { tipo: "whatsapp", pedida_en: PEDIDA, hecha: true, vencida: false } }),
    );
    expect(await screen.findByText("¡Listo! Ya está conectado", {}, { timeout: 7000 })).toBeInTheDocument();
  }, 10_000);

  it("vencida: la computadora no respondió", async () => {
    traer.mockResolvedValue(conexiones());
    pedir.mockResolvedValue({ ok: true, reconexion: { tipo: "whatsapp", pedida_en: PEDIDA, hecha: false, vencida: false } });
    montar();

    traer.mockResolvedValue(conexiones({ reconexion: { tipo: "whatsapp", pedida_en: PEDIDA, hecha: false, vencida: true } }));
    await userEvent.click(await screen.findByRole("button", { name: "Volver a conectar WhatsApp" }));
    expect(
      await screen.findByText("La computadora no respondió: fijate que esté prendida", {}, { timeout: 7000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Probar de nuevo" })).toBeInTheDocument();
  }, 10_000);

  it("429: se muestra el texto del servidor y se siguen los pasos del pedido que ya estaba", async () => {
    traer.mockResolvedValue(conexiones({ whatsapp: "ok", claude: "caida" }));
    pedir.mockRejectedValue(new ErrorDeConexiones(429, "Ya se pidió recién. Probá de nuevo en 80 segundos."));
    montar();

    await userEvent.click(await screen.findByRole("button", { name: "Volver a conectar Claude" }));
    expect(await screen.findByText("Ya se pidió recién. Probá de nuevo en 80 segundos.")).toBeInTheDocument();
    // Los pasos de Claude, con el nombre de a quién pedirle el código.
    expect(screen.getByText(/Pedile el código a Martina/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ya terminé" })).toBeInTheDocument();
  });

  it("Ya terminé: pide verificar y muestra Revisando…", async () => {
    traer.mockResolvedValue(conexiones({ whatsapp: "ok", claude: "caida" }));
    pedir.mockResolvedValueOnce({ ok: true, reconexion: { tipo: "claude", pedida_en: PEDIDA, hecha: false, vencida: false } });
    pedir.mockResolvedValueOnce({
      ok: true,
      reconexion: { tipo: "verificar", pedida_en: "2026-11-16T15:04:00Z", hecha: false, vencida: false },
    });
    montar();

    await userEvent.click(await screen.findByRole("button", { name: "Volver a conectar Claude" }));
    await userEvent.click(await screen.findByRole("button", { name: "Ya terminé" }));
    expect(pedir).toHaveBeenLastCalledWith("pc-sofia", "verificar");
    expect(await screen.findByText("Revisando…")).toBeInTheDocument();
  });

  it("sin red: un aviso simple, sin códigos", async () => {
    traer.mockRejectedValue(new ErrorDeConexiones(0, null));
    montar();
    expect(await screen.findByText(/No se pudo actualizar/)).toBeInTheDocument();
  });
});
