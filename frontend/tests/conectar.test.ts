import { describe, expect, it } from "vitest";

import { pasoDeReconexion, type ConexionPublica, type Pedido } from "@/lib/conectar";

/**
 * Los pasos de la página de conexiones (D71), sin montar la página.
 *
 * Lo que se prueba es lo que, si se rompe, deja a un vendedor mirando una
 * pantalla que miente: un "¡Listo!" que no llega, un "vencida" de un pedido
 * anterior, o un "no se completó" en el flujo de Claude, que espera a que otra
 * persona pase un código.
 */

const PEDIDO_EN = Date.parse("2026-11-16T15:00:00Z");
const DESDE = "2026-11-16T15:00:01Z";

const pedido = (cambios: Partial<Pedido> = {}): Pedido => ({
  maquina: "pc-sofia",
  tipo: "whatsapp",
  pedidoEn: PEDIDO_EN,
  desde: DESDE,
  verificacionPedida: false,
  ...cambios,
});

const sofia = (cambios: Partial<ConexionPublica> = {}): ConexionPublica => ({
  maquina: "pc-sofia",
  nombre: "Sofía",
  estado: "viva",
  whatsapp: "caida",
  claude: "ok",
  reconexion: { tipo: "whatsapp", pedida_en: DESDE, hecha: false, vencida: false },
  ...cambios,
});

const minutos = (n: number) => PEDIDO_EN + n * 60_000;

describe("pasoDeReconexion", () => {
  it("pedido: muestra los pasos mientras WhatsApp sigue caído", () => {
    expect(pasoDeReconexion(pedido(), sofia(), minutos(1))).toBe("esperando");
  });

  it("pedido → listo: cuando WhatsApp pasa a conectado", () => {
    expect(pasoDeReconexion(pedido(), sofia({ whatsapp: "ok" }), minutos(1))).toBe("listo");
  });

  it("conectado gana aunque la reconexión diga vencida o hayan pasado los cinco minutos", () => {
    const vencida = { tipo: "whatsapp" as const, pedida_en: DESDE, hecha: false, vencida: true };
    expect(pasoDeReconexion(pedido(), sofia({ whatsapp: "ok", reconexion: vencida }), minutos(9))).toBe("listo");
  });

  it("vencida: la computadora no tomó el pedido", () => {
    const reconexion = { tipo: "whatsapp" as const, pedida_en: DESDE, hecha: false, vencida: true };
    expect(pasoDeReconexion(pedido(), sofia({ reconexion }), minutos(1))).toBe("vencida");
  });

  it("una reconexión vencida de antes del pedido no cuenta (probar de nuevo no muestra vencida otra vez)", () => {
    const vieja = { tipo: "whatsapp" as const, pedida_en: "2026-11-16T14:40:00Z", hecha: false, vencida: true };
    expect(pasoDeReconexion(pedido(), sofia({ reconexion: vieja }), minutos(1))).toBe("esperando");
  });

  it("con un 429 (desde = null) vale la reconexión que ya estaba", () => {
    const reconexion = { tipo: "whatsapp" as const, pedida_en: "2026-11-16T14:59:00Z", hecha: false, vencida: true };
    expect(pasoDeReconexion(pedido({ desde: null }), sofia({ reconexion }), minutos(1))).toBe("vencida");
  });

  it("a los cinco minutos sin conectarse: no se completó", () => {
    expect(pasoDeReconexion(pedido(), sofia(), minutos(4.9))).toBe("esperando");
    expect(pasoDeReconexion(pedido(), sofia(), minutos(5))).toBe("no_se_completo");
  });

  it("Claude no tiene reloj: espera a que alguien pase el código", () => {
    const claude = pedido({ tipo: "claude" });
    const reconexion = { tipo: "claude" as const, pedida_en: DESDE, hecha: true, vencida: false };
    expect(pasoDeReconexion(claude, sofia({ claude: "caida", reconexion }), minutos(30))).toBe("esperando");
  });

  it("Ya terminé: revisando mientras la máquina no verificó, y listo cuando Claude pasa a conectado", () => {
    const claude = pedido({ tipo: "claude", verificacionPedida: true, desde: "2026-11-16T15:03:00Z" });
    const verificando = { tipo: "verificar" as const, pedida_en: "2026-11-16T15:03:00Z", hecha: false, vencida: false };
    expect(pasoDeReconexion(claude, sofia({ claude: "caida", reconexion: verificando }), minutos(4))).toBe("revisando");
    expect(pasoDeReconexion(claude, sofia({ claude: "ok", reconexion: verificando }), minutos(4))).toBe("listo");
  });

  it("Ya terminé: si el servidor todavía muestra la reconexión anterior, sigue revisando", () => {
    const claude = pedido({ tipo: "claude", verificacionPedida: true, desde: "2026-11-16T15:03:00Z" });
    const anterior = { tipo: "claude" as const, pedida_en: DESDE, hecha: true, vencida: false };
    expect(pasoDeReconexion(claude, sofia({ claude: "caida", reconexion: anterior }), minutos(4))).toBe("revisando");
  });

  it("la máquina verificó y sigue sin conectarse: todavía no", () => {
    const claude = pedido({ tipo: "claude", verificacionPedida: true, desde: "2026-11-16T15:03:00Z" });
    const hecha = { tipo: "verificar" as const, pedida_en: "2026-11-16T15:03:00Z", hecha: true, vencida: false };
    expect(pasoDeReconexion(claude, sofia({ claude: "caida", reconexion: hecha }), minutos(4))).toBe("todavia_no");
  });

  it("una verificación vencida es vencida", () => {
    const wa = pedido({ verificacionPedida: true, desde: "2026-11-16T15:03:00Z" });
    const vencida = { tipo: "verificar" as const, pedida_en: "2026-11-16T15:03:00Z", hecha: false, vencida: true };
    expect(pasoDeReconexion(wa, sofia({ reconexion: vencida }), minutos(4))).toBe("vencida");
  });
});
