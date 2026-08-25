"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { altaMaquina, ErrorDeApi } from "@/lib/panel";
import { textos } from "@/lib/textos";

/**
 * Alta de una máquina.
 *
 * La cantidad de máquinas es variable y la administra el cliente: nada de esta
 * pantalla asume un número. Es la propiedad que tenía el n8n del MVP y que hay
 * que conservar.
 */
export function AltaMaquina({ onToken }: { onToken: (token: string, nombre: string) => void }) {
  const [abierto, setAbierto] = useState(false);
  const [maquina, setMaquina] = useState("");
  const [nombre, setNombre] = useState("");
  const [linea, setLinea] = useState("");
  // El backend lo acepta en el alta y el formulario no lo pedía, así que toda
  // máquina nueva nacía con el valor de fábrica y había que corregirlo después.
  const [tope, setTope] = useState("20");
  const clienteQuery = useQueryClient();

  const crear = useMutation({
    mutationFn: () =>
      altaMaquina({
        maquina,
        nombre,
        telefono_linea: linea.trim() || null,
        tope_diario: Number(tope) || 20,
      }),
    onSuccess: (nuevo) => {
      onToken(nuevo.token, nuevo.maquina);
      setMaquina("");
      setNombre("");
      setLinea("");
      setTope("20");
      setAbierto(false);
    },
    onSettled: () => clienteQuery.invalidateQueries({ queryKey: ["estado"] }),
  });

  if (!abierto) {
    return (
      <Button variant="outline" onClick={() => setAbierto(true)}>
        <Plus className="size-4" aria-hidden />
        {textos.alta.titulo}
      </Button>
    );
  }

  // Cualquier fallo tiene que verse. Antes sólo se mostraba el 409, así que un
  // 422 o un 500 dejaban el formulario sin decir nada: el botón se
  // des-deshabilitaba y no pasaba nada, que para quien usa esto es peor que un
  // mensaje feo.
  const problema = mensajeDeError(crear.error);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{textos.alta.titulo}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-3"
          onSubmit={(evento) => {
            evento.preventDefault();
            crear.mutate();
          }}
        >
          <Campo
            etiqueta={textos.alta.identificador}
            ayuda={textos.alta.identificadorAyuda}
            valor={maquina}
            onChange={setMaquina}
            // El mismo patrón que valida el backend. Acá es para que el error
            // aparezca mientras se escribe, no después de mandar.
            pattern="[a-z0-9][a-z0-9-]*"
            placeholder="mac-rocio"
            requerido
          />
          <Campo
            etiqueta={textos.alta.nombre}
            valor={nombre}
            onChange={setNombre}
            placeholder="Rocío Fernández"
            requerido
          />
          <Campo
            etiqueta={textos.alta.linea}
            valor={linea}
            onChange={setLinea}
            placeholder="+54 11 4440-5036"
          />
          <Campo
            etiqueta={textos.alta.tope}
            ayuda={textos.alta.topeAyuda}
            valor={tope}
            onChange={setTope}
            placeholder="20"
          />

          {problema && <p className="text-sm text-destructive">{problema}</p>}

          <p className="text-xs text-muted-foreground">{textos.alta.naceInactiva}</p>

          <div className="flex gap-2">
            <Button type="submit" disabled={crear.isPending}>
              {crear.isPending ? textos.alta.creando : textos.alta.crear}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setAbierto(false)}>
              Cancelar
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

/**
 * El error, dicho para quien usa el panel y no para quien lo programó.
 *
 * Los dos casos que una persona se encuentra de verdad tienen su texto; el
 * resto cae en el mensaje del servidor, que es feo pero es información. Lo que
 * no puede pasar es que no aparezca nada.
 */
function mensajeDeError(error: unknown): string | null {
  if (!error) return null;
  if (!(error instanceof ErrorDeApi)) return textos.alta.errorDesconocido;
  if (error.status === 409) return textos.alta.duplicada;
  if (error.status === 422) return textos.alta.identificadorInvalido;
  return error.message;
}

function Campo({
  etiqueta,
  ayuda,
  valor,
  onChange,
  pattern,
  placeholder,
  requerido,
}: {
  etiqueta: string;
  ayuda?: string;
  valor: string;
  onChange: (valor: string) => void;
  pattern?: string;
  placeholder?: string;
  requerido?: boolean;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium">{etiqueta}</span>
      <input
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        value={valor}
        onChange={(evento) => onChange(evento.target.value)}
        pattern={pattern}
        placeholder={placeholder}
        required={requerido}
      />
      {ayuda && <span className="block text-xs text-muted-foreground">{ayuda}</span>}
    </label>
  );
}

/**
 * El token recién generado.
 *
 * Se muestra una sola vez y no se puede recuperar: está hasheado en la base. La
 * pantalla tiene que dejar eso clarísimo **antes** de que alguien cierre el
 * cartel, no después.
 */
export function TokenReciente({
  token,
  maquina,
  onCerrar,
}: {
  token: string;
  maquina: string;
  onCerrar: () => void;
}) {
  const [copiado, setCopiado] = useState(false);

  return (
    <Card className="border-atencion-borde bg-atencion-suave">
      <CardHeader>
        <CardTitle className="text-base">
          {textos.alta.tokenTitulo} — <span className="font-mono">{maquina}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="font-semibold text-atencion">{textos.alta.tokenAviso}</p>
        <code className="block overflow-x-auto rounded-md border bg-muted p-3 font-mono text-sm">
          {token}
        </code>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void navigator.clipboard.writeText(token);
              setCopiado(true);
            }}
          >
            <Copy className="size-4" aria-hidden />
            {copiado ? "Copiado" : "Copiar"}
          </Button>
          <Button size="sm" onClick={onCerrar}>
            {textos.alta.tokenListo}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
