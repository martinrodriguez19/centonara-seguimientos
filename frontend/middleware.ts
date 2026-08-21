/**
 * Manda al login a quien no tenga cookie de sesión.
 *
 * ⚠️ **Esto no es la autorización.** Sólo mira que la cookie EXISTA: no verifica
 * la firma, porque el secreto vive en el backend y no acá. Alguien puede
 * fabricarse una cookie con cualquier contenido y pasar de largo — y va a
 * recibir 401 en la primera consulta, porque el backend sí la verifica.
 *
 * Lo que hace esto es evitar el parpadeo: entrar al panel, ver la pantalla
 * armarse y que a los 200 ms te expulse. La autorización de verdad está en
 * `app/api/panel.py`, y ahí es donde tiene que estar.
 */

import { NextResponse, type NextRequest } from "next/server";

const COOKIE = "sesion";
const PUBLICAS = ["/login", "/healthz"];

export function middleware(pedido: NextRequest) {
  const { pathname } = pedido.nextUrl;

  if (PUBLICAS.some((ruta) => pathname.startsWith(ruta))) {
    return NextResponse.next();
  }

  if (pedido.cookies.has(COOKIE)) {
    return NextResponse.next();
  }

  const login = new URL("/login", pedido.url);
  return NextResponse.redirect(login);
}

export const config = {
  // `/api` queda afuera: lo protege el backend, y el propio login es un POST a
  // /api/sesion que por definición todavía no tiene cookie.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
