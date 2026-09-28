"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * "Ya lo vi": los errores que alguien sacó de la vista.
 *
 * **Es sólo visual y sólo de este navegador.** Las alertas no se guardan en
 * ningún lado —el backend las calcula al preguntar y desaparecen solas cuando
 * se resuelve la causa—, así que no hay nada que marcar del lado del servidor.
 * Lo que se recuerda es la *firma* (código + máquina + detalle): si la misma
 * alerta vuelve con otro detalle, es otra y se vuelve a ver.
 *
 * `useSyncExternalStore` y no un `useState` por componente: la barra de arriba
 * cuenta los no vistos y la página de errores los marca, y los dos tienen que
 * enterarse en el mismo instante.
 */

const CLAVE = "errores-vistos";
const oyentes = new Set<() => void>();
const VACIO: string[] = [];
let cache: string[] | null = null;

function leer(): string[] {
  if (cache) return cache;
  try {
    const crudo = localStorage.getItem(CLAVE);
    const lista = crudo ? JSON.parse(crudo) : [];
    cache = Array.isArray(lista) ? lista.filter((x) => typeof x === "string") : [];
  } catch {
    // Sin localStorage (modo privado, permisos) nada queda visto: se muestra
    // todo, que es el lado seguro.
    cache = [];
  }
  return cache!;
}

function escribir(lista: string[]) {
  cache = lista;
  try {
    localStorage.setItem(CLAVE, JSON.stringify(lista));
  } catch {
    /* Sin localStorage vale para esta pestaña y nada más. */
  }
  oyentes.forEach((avisar) => avisar());
}

function suscribir(avisar: () => void) {
  oyentes.add(avisar);
  return () => oyentes.delete(avisar);
}

export function useVistos() {
  const vistos = useSyncExternalStore(suscribir, leer, () => VACIO);

  const marcar = useCallback((firma: string) => {
    const actual = leer();
    if (!actual.includes(firma)) escribir([...actual, firma]);
  }, []);

  const desmarcar = useCallback((firma: string) => {
    escribir(leer().filter((f) => f !== firma));
  }, []);

  /** Olvida las firmas que ya no están: sin esto la lista crece para siempre. */
  const podar = useCallback((vigentes: string[]) => {
    const actual = leer();
    const quedan = actual.filter((f) => vigentes.includes(f));
    if (quedan.length !== actual.length) escribir(quedan);
  }, []);

  return { vistos, marcar, desmarcar, podar };
}

/** Sólo para los tests: vuelve a leer de `localStorage`. */
export function _olvidarCache() {
  cache = null;
}
