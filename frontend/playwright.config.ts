import { defineConfig, devices } from "@playwright/test";

/**
 * El recorrido de punta a punta, contra el panel y el backend levantados.
 *
 * **Uno solo, y es el de la demostración**: entrar, dar de alta una máquina,
 * generar, revisar, enviar en ensayo. Tenerlo automatizado significa que el día
 * que alguien rompa un eslabón, el CI lo dice — y no se descubre delante del
 * cliente.
 *
 * ⚠️ Necesita el backend corriendo en `BACKEND_URL` con su Mongo. No corre en
 * el CI junto con el resto: se dispara aparte, porque levantar la pila entera
 * en cada push cuesta minutos y este recorrido no cambia todos los días.
 *
 * Webkit además de Chromium: el parque es Mac, y Safari es el que más se aparta
 * en formularios y en `backdrop-filter`, que el panel usa en dos barras fijas.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",

  use: {
    baseURL: process.env.PANEL_URL ?? "http://localhost:3000",
    // Sólo cuando algo falla: una traza por corrida verde es un archivo que
    // nadie abre y que ocupa lugar en el artefacto del CI.
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    locale: "es-AR",
    timezoneId: "America/Argentina/Buenos_Aires",
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],

  webServer: process.env.PANEL_URL
    ? undefined
    : {
        command: "pnpm dev",
        url: "http://localhost:3000/healthz",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
