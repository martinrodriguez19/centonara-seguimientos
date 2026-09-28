import { redirect } from "next/navigation";

/** `/config` lleva a la primera sección, que es la que más se busca. */
export default function Config() {
  redirect("/config/envio");
}
