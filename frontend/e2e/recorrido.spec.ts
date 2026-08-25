import { expect, test } from "@playwright/test";

/**
 * El recorrido de la demostración, de punta a punta.
 *
 * Entrar → dar de alta una máquina → ver el panel → llegar a las corridas.
 *
 * **No dispara una generación real** y no es una omisión: generar abre WhatsApp
 * en una máquina de verdad, tarda minutos y cuesta dinero por chat leído. Lo que
 * este recorrido prueba es que las pantallas están enganchadas entre sí, que es
 * exactamente lo que estaba roto.
 *
 * ⚠️ Y **nunca envía en modo real**, ni siquiera con la lista de destinos
 * abierta. Un test que le puede escribir a alguien es un test que algún día le
 * escribe a alguien.
 *
 * Necesita `PANEL_PASSWORD` en el entorno, con la contraseña del panel contra
 * el que corre.
 */
const CLAVE = process.env.PANEL_PASSWORD ?? "";

test.skip(!CLAVE, "necesita PANEL_PASSWORD para entrar al panel");

test.describe("el recorrido del panel", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/contraseña/i).fill(CLAVE);
    await page.getByRole("button", { name: /entrar/i }).click();
    await expect(page).toHaveURL(/\/panel/);
  });

  test("el panel dice en qué modo está antes que cualquier otra cosa", async ({ page }) => {
    // La banda de modo es lo primero de la pantalla, y tiene que decir una de
    // las dos cosas. Que no diga ninguna es el peor resultado posible.
    const banda = page.getByText(/modo prueba|envío real habilitado/i).first();
    await expect(banda).toBeVisible();
  });

  test("se puede pedir una generación, y confirma antes de arrancar", async ({ page }) => {
    const generar = page.getByRole("button", { name: /generar seguimientos/i });
    await expect(generar).toBeVisible();

    // Si hay máquinas activas, el botón confirma. Si no, dice por qué no.
    if (await generar.isEnabled()) {
      await generar.click();
      await expect(page.getByText(/vas a generar seguimientos/i)).toBeVisible();
      // Se cancela: este recorrido no gasta dinero.
      await page.getByRole("button", { name: /^cancelar$/i }).click();
      await expect(page.getByText(/vas a generar seguimientos/i)).toBeHidden();
    } else {
      await expect(page.getByText(/no hay ninguna máquina activa/i)).toBeVisible();
    }
  });

  test("el kill switch pide confirmación y se puede desistir", async ({ page }) => {
    const frenar = page.getByRole("button", { name: /frenar todo/i });
    // Si ya está frenado, el botón dice "Reanudar" y no hay nada que probar.
    test.skip(!(await frenar.isVisible()), "el sistema ya está frenado");

    await frenar.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByText(/dejar de recibir trabajo/i)).toBeVisible();

    // Escape cierra sin frenar nada. Que la salida exista importa tanto como
    // que el freno funcione.
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(frenar).toBeVisible();
  });

  test("se llega a las corridas, la configuración y el historial", async ({ page }) => {
    await page.getByRole("link", { name: /^corridas$/i }).click();
    await expect(page.getByRole("heading", { name: /corridas/i })).toBeVisible();

    await page.goto("/config");
    await expect(page.getByRole("heading", { name: /configuración/i })).toBeVisible();
    // Lo que no se edita pero hay que poder mirar.
    await expect(page.getByText(/cuándo y a qué ritmo sale/i)).toBeVisible();

    await page.goto("/historial");
    await expect(page.getByRole("heading", { name: /historial/i })).toBeVisible();
  });

  test("una dirección que no existe no deja la pantalla en blanco", async ({ page }) => {
    await page.goto("/corrida/no-es-un-id");
    // O el 404 propio, o el error de carga del panel. Lo que no puede pasar es
    // una pantalla vacía o el error en inglés de Next.
    await expect(
      page.getByText(/no existe|no se pudieron traer los datos|el servidor no responde/i).first(),
    ).toBeVisible();
  });
});
