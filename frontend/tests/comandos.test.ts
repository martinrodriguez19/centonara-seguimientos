import { describe, expect, it } from "vitest";

import { grupos } from "@/lib/comandos";

/**
 * El catálogo de comandos.
 *
 * No se prueba cómo se ve la página: se prueban los invariantes que hacen que un
 * comando copiado de ahí **funcione al pegarlo**. Todos vienen del mismo lugar:
 * del otro lado de esta pantalla hay alguien parado frente a la Mac de un
 * vendedor, con una Terminal abierta y sin forma de saber si el comando salió
 * mal de acá o lo pegó mal él.
 */
describe("catálogo de comandos", () => {
  const todos = grupos.flatMap((grupo) => grupo.comandos);

  it("no hay dos comandos con el mismo id", () => {
    // Los id son las anclas del índice. Dos iguales y el enlace lleva siempre
    // al primero: el segundo comando queda inalcanzable desde el índice.
    const ids = todos.map((comando) => comando.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("no hay dos grupos con el mismo id", () => {
    const ids = grupos.map((grupo) => grupo.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("ningún comando tiene saltos de línea", () => {
    // Pegar dos líneas en una Terminal ejecuta las dos, y la segunda corre sin
    // que nadie la haya leído. Si un comando necesita dos pasos, son dos
    // entradas del catálogo.
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

  it("ningún grupo está vacío", () => {
    for (const grupo of grupos) {
      expect(grupo.comandos.length, grupo.id).toBeGreaterThan(0);
    }
  });
});
