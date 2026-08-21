import { redirect } from "next/navigation";

/**
 * La raíz manda al panel.
 *
 * Quien entra al dominio quiere el panel; el middleware lo manda al login si no
 * tiene sesión. Una página de bienvenida entre el dominio y lo único que la
 * aplicación hace sería un click de más, todos los días.
 */
export default function Inicio() {
  redirect("/panel");
}
