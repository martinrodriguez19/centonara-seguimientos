import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Los tests de componente del panel.
 *
 * **Por qué existen.** El backend tiene 596 tests y el agente 225. El panel
 * tenía cero, y es el que toca el botón de enviar. No es cobertura por la
 * cobertura: lo que se prueba acá son las cuatro cosas que, si se rompen en
 * silencio, terminan en un mensaje que no debía salir o en un operador que no
 * sabe lo que acaba de hacer.
 *
 * `jsdom` y no un navegador de verdad: esto prueba la lógica de las pantallas
 * —qué se habilita, qué se muestra, qué se llama—. Cómo se ven en Safari lo
 * prueba el recorrido de Playwright, que es otra cosa y corre aparte.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["tests/**/*.test.tsx", "tests/**/*.test.ts"],
    // `e2e/` es de Playwright: si Vitest lo levanta, falla con un error que no
    // dice nada sobre lo que en realidad pasa.
    exclude: ["node_modules/**", ".next/**", "e2e/**"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./") },
  },
});
