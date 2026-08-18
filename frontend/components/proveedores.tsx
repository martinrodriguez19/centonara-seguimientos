"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

/**
 * Proveedores de cliente de toda la app.
 *
 * TanStack Query es el estado de servidor del panel (08 §3): nada de
 * `useEffect` con `fetch`. Se monta desde el Sprint 0 para que el Sprint 3 no
 * tenga que refactorizar el layout.
 */
export function Proveedores({ children }: { children: React.ReactNode }) {
  // `useState` y no una constante de módulo: en el servidor, una constante de
  // módulo se comparte entre peticiones de usuarios distintos. Cuando haya
  // datos con sesión eso sería una fuga de una cuenta a otra.
  const [cliente] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // El panel muestra cosas que cambian solas (corridas, cuentas
            // regresivas). Un dato viejo mostrado como actual es el peor
            // resultado posible acá, así que nada se considera fresco.
            staleTime: 0,
            retry: 1,
            refetchOnWindowFocus: true,
          },
        },
      }),
  );

  return <QueryClientProvider client={cliente}>{children}</QueryClientProvider>;
}
