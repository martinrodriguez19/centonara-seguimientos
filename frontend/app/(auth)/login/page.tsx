"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorDeApi, ingresar } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Login. Una contraseña, y nada más.
 *
 * Sin usuario: hay una sola contraseña para el panel (D22). Pedir un usuario que
 * siempre es el mismo es un campo que alguien tiene que completar sin que sirva
 * para nada.
 */
export default function Login() {
  const router = useRouter();
  const [clave, setClave] = useState("");

  const entrar = useMutation({
    mutationFn: () => ingresar(clave),
    onSuccess: () => {
      router.push("/panel");
      // La cookie es `httponly`, así que el estado de sesión no vive en React:
      // vive en el navegador. Refrescar hace que el servidor la vea.
      router.refresh();
    },
  });

  const incorrecta = entrar.error instanceof ErrorDeApi && entrar.error.status === 401;
  const sinBackend = entrar.error instanceof ErrorDeApi && entrar.error.status >= 500;

  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{textos.login.titulo}</CardTitle>
          <p className="text-sm text-muted-foreground">{textos.login.subtitulo}</p>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(evento) => {
              evento.preventDefault();
              entrar.mutate();
            }}
          >
            <label className="block space-y-1">
              <span className="text-sm font-medium">{textos.login.clave}</span>
              <input
                type="password"
                autoComplete="current-password"
                autoFocus
                required
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={clave}
                onChange={(evento) => setClave(evento.target.value)}
              />
            </label>

            {incorrecta && <p className="text-sm text-destructive">{textos.login.incorrecta}</p>}
            {sinBackend && <p className="text-sm text-destructive">{textos.login.sinBackend}</p>}

            <Button type="submit" className="w-full" disabled={entrar.isPending}>
              {entrar.isPending ? textos.login.entrando : textos.login.entrar}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
