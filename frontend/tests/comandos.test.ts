import { describe, expect, it } from "vitest";

import { sistemas, todosLosComandos } from "@/lib/guia";

/**
 * La guía de instalación y reparación.
 *
 * No se prueba cómo se ve la página: se prueban los invariantes que hacen que un
 * comando copiado de ahí **funcione al pegarlo**. Del otro lado de esta pantalla
 * hay alguien parado frente a la computadora de un vendedor, con una Terminal o
 * una PowerShell abierta y sin forma de saber si el comando salió mal de acá o
 * lo pegó mal él.
 */
describe("la guía", () => {
  const todos = todosLosComandos();
  const computadoras = sistemas.filter((s) => s.id !== "panel");

  it("no hay dos comandos con el mismo id", () => {
    // Los id son las anclas del índice. Dos iguales y el enlace lleva siempre
    // al primero: el segundo comando queda inalcanzable.
    const ids = todos.map((comando) => comando.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("no hay dos pasos con el mismo id dentro de un sistema", () => {
    for (const sistema of sistemas) {
      const ids = sistema.pasos.map((p) => p.id);
      expect(new Set(ids).size, sistema.id).toBe(ids.length);
    }
  });

  it("ningún comando tiene saltos de línea", () => {
    // Pegar dos líneas en una Terminal ejecuta las dos, y la segunda corre sin
    // que nadie la haya leído. Si un comando necesita dos pasos, son dos
    // entradas de la guía.
    for (const comando of todos) {
      expect(comando.comando, comando.id).not.toContain("\n");
    }
  });

  it("todo comando con un hueco lo declara", () => {
    // Un `+549XXXXXXXXXX` pegado tal cual falla, y eso está bien. Lo que no
    // puede pasar es que la página no avise que hay algo que reemplazar.
    for (const comando of todos) {
      if (/XXX/.test(comando.comando)) {
        expect(comando.hueco, `${comando.id} tiene un hueco sin declarar`).toBeTruthy();
      }
    }
  });

  it("las tres computadoras tienen los mismos pasos, en el mismo orden", () => {
    // Quien ya instaló una Mac tiene que saber dónde buscar en Windows.
    const orden = ["antes", "chrome", "instalar", "vincular", "comprobar", "reinstalar", "vence", "actualizar"];
    for (const sistema of computadoras) {
      const ids = sistema.pasos.map((p) => p.id);
      expect(ids.slice(0, orden.length), sistema.id).toEqual(orden);
      expect(sistema.problemas?.length, `${sistema.id} sin tabla de problemas`).toBeGreaterThan(0);
    }
  });

  it("cada computadora tiene cómo instalar y cómo reinstalar desde cero", () => {
    for (const sistema of computadoras) {
      const instalar = sistema.pasos.find((p) => p.id === "instalar")!;
      const reinstalar = sistema.pasos.find((p) => p.id === "reinstalar")!;
      expect(instalar.comandos?.some((c) => /instalar\.(sh|ps1)/.test(c.comando)), sistema.id).toBe(true);
      expect(reinstalar.comandos?.some((c) => /desinstalar\.(sh|ps1)/.test(c.comando)), sistema.id).toBe(true);
      expect(reinstalar.comandos?.some((c) => /[^s]instalar\.(sh|ps1)/.test(c.comando)), sistema.id).toBe(true);
    }
  });

  it("ningún comando de Windows pasa por «irm | iex»", () => {
    // El 25/09/2026 ninguno de los comandos de Windows de la documentación
    // funcionó: `iex` cierra la ventana en el primer `exit`, no acepta opciones
    // y el BOM del archivo le rompe el `param()`. Se baja a archivo y se corre
    // con -File. Si alguien lo "simplifica" de vuelta, esto se pone en rojo.
    const windows = sistemas.find((s) => s.id === "windows")!;
    for (const comando of windows.pasos.flatMap((p) => p.comandos ?? [])) {
      expect(comando.comando, comando.id).not.toMatch(/\|\s*iex\b/);
      expect(comando.comando, comando.id).not.toMatch(/Invoke-Expression/);
      if (/\.ps1/.test(comando.comando)) {
        expect(comando.comando, comando.id).toMatch(/-ExecutionPolicy Bypass -File/);
      }
    }
  });

  it("los comandos de Mac que bajan algo llevan --http1.1", () => {
    // En macOS 10.15 el curl del sistema contesta 503 a GitHub sin él, y el
    // error parece de la red.
    for (const sistema of computadoras.filter((s) => s.id !== "windows")) {
      for (const comando of sistema.pasos.flatMap((p) => p.comandos ?? [])) {
        if (/curl .*github\.com/.test(comando.comando)) {
          expect(comando.comando, comando.id).toContain("--http1.1");
        }
      }
    }
  });
});
