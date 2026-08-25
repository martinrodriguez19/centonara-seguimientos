import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Cada test arranca con el DOM limpio. Sin esto, dos tests que renderizan el
// mismo componente encuentran dos copias y `getByRole` falla con un mensaje que
// no dice nada sobre la causa.
afterEach(() => cleanup());

/**
 * `matchMedia` no existe en jsdom, y el selector de tema lo usa.
 *
 * Devuelve siempre "no oscuro": el tema no es lo que estos tests prueban, y una
 * preferencia que cambia entre corridas haría fallar cosas que no tienen nada
 * que ver.
 */
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});
