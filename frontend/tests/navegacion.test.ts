import { describe, expect, it } from "vitest";

import { esActual, grupoActual, grupos } from "@/lib/navegacion";

/**
 * La barra de tres grupos (D54). Lo que se prueba es que ninguna pantalla
 * quede sin camino desde la barra, y que la marca de "estás acá" caiga en el
 * grupo correcto también en las subrutas.
 */
describe("navegación", () => {
  it("son tres grupos, y llegan a todas las pantallas del panel", () => {
    const lista = grupos("abc");
    expect(lista.map((g) => g.clave)).toEqual(["operacion", "analisis", "ajustes"]);
    const destinos = lista.flatMap((g) => g.destinos.map((d) => d.href));
    for (const ruta of ["/panel", "/maquinas", "/corridas", "/revision/abc", "/estadisticas", "/errores", "/historial", "/config/envio", "/comandos"]) {
      expect(destinos).toContain(ruta);
    }
  });

  it("sin ninguna corrida, no ofrece revisar la última", () => {
    const destinos = grupos(null).flatMap((g) => g.destinos.map((d) => d.href));
    expect(destinos.some((d) => d.startsWith("/revision"))).toBe(false);
  });

  it("marca el grupo también en las subrutas", () => {
    const lista = grupos(null);
    expect(grupoActual(lista, "/maquinas/mac-rocio")).toBe("operacion");
    expect(grupoActual(lista, "/corrida/123")).toBe("operacion");
    expect(grupoActual(lista, "/errores")).toBe("analisis");
    expect(grupoActual(lista, "/config/seguridad")).toBe("ajustes");
  });

  it("un prefijo no se confunde con otra ruta que empieza igual", () => {
    const corridas = grupos(null)[0].destinos.find((d) => d.href === "/corridas")!;
    expect(esActual(corridas, "/corrida/1")).toBe(true);
    expect(esActual(corridas, "/corridasx")).toBe(false);
  });
});
