/**
 * Reenvía al backend todo lo que el navegador pide bajo `/api/`.
 *
 * ¿Por qué un intermediario en vez de que el navegador llame al backend
 * directo? Por dos cosas que se pagarían caras después:
 *
 * 1. `BACKEND_URL` no lleva prefijo `NEXT_PUBLIC_`, así que no viaja al
 *    navegador. La URL del backend no queda escrita en el HTML de nadie.
 * 2. El backend no necesita CORS. Todas las peticiones le llegan del servidor
 *    de Next, del mismo origen, y no hay que mantener una lista de orígenes
 *    permitidos que alguien va a aflojar un día apurado.
 *
 * La cookie de sesión viaja en las dos direcciones: entra en el pedido y el
 * `Set-Cookie` de la respuesta se devuelve tal cual, así que el login funciona
 * sin que este archivo sepa nada de sesiones.
 */

import { NextRequest, NextResponse } from "next/server";

import { urlBackend } from "@/lib/api";

/** Los que el backend puede recibir. Cualquier otro no llega ni a salir de acá. */
const METODOS = ["GET", "POST", "PATCH", "DELETE"] as const;

/**
 * Encabezados que NO se reenvían.
 *
 * `host` es el del servidor de Next y confundiría al backend; los de longitud y
 * codificación los recalcula `fetch` y mandarlos viejos rompe el cuerpo.
 */
const NO_REENVIAR = new Set(["host", "connection", "content-length", "content-encoding"]);

async function reenviar(pedido: NextRequest, ruta: string[]): Promise<NextResponse> {
  const destino = new URL(`/api/${ruta.join("/")}`, urlBackend());
  destino.search = pedido.nextUrl.search;

  const encabezados = new Headers();
  pedido.headers.forEach((valor, nombre) => {
    if (!NO_REENVIAR.has(nombre.toLowerCase())) encabezados.set(nombre, valor);
  });

  const cuerpo = pedido.method === "GET" ? undefined : await pedido.text();

  let respuesta: Response;
  try {
    respuesta = await fetch(destino, {
      method: pedido.method,
      headers: encabezados,
      body: cuerpo,
      cache: "no-store",
      // El agente consulta cada 10 s y el backend contesta enseguida: nada de
      // acá tarda. Un timeout corto evita que una pantalla quede colgada
      // esperando a un backend que no está.
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    // El backend caído no es un error del panel: es un dato que la pantalla
    // tiene que poder mostrar. 502 y un cuerpo con la misma forma que usa el
    // backend para sus errores, así el cliente no necesita dos caminos.
    return NextResponse.json(
      { error: "BACKEND_NO_DISPONIBLE", detalle: "El backend no respondió" },
      { status: 502 },
    );
  }

  // 204 no lleva cuerpo, y construir un NextResponse con uno vacío pero con
  // content-type hace que algunos clientes intenten parsearlo.
  if (respuesta.status === 204) {
    return new NextResponse(null, { status: 204 });
  }

  const salida = new NextResponse(await respuesta.text(), {
    status: respuesta.status,
    headers: { "content-type": respuesta.headers.get("content-type") ?? "application/json" },
  });

  // `getSetCookie` y no `get`: puede venir más de una y `get` las concatena en
  // un solo string, que el navegador después no sabe separar.
  for (const cookie of respuesta.headers.getSetCookie()) {
    salida.headers.append("set-cookie", cookie);
  }
  return salida;
}

type Contexto = { params: Promise<{ ruta: string[] }> };

async function manejar(pedido: NextRequest, contexto: Contexto): Promise<NextResponse> {
  if (!METODOS.includes(pedido.method as (typeof METODOS)[number])) {
    return NextResponse.json({ error: "METODO_NO_PERMITIDO" }, { status: 405 });
  }
  const { ruta } = await contexto.params;
  return reenviar(pedido, ruta);
}

export const GET = manejar;
export const POST = manejar;
export const PATCH = manejar;
export const DELETE = manejar;
