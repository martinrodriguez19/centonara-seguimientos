# tests — los tests de componente del panel

Corren en el CI (`pnpm test`, entre `Tipos` y `Compila`).

```bash
pnpm test                                   # Vitest, jsdom
pnpm exec playwright install chromium webkit
PANEL_PASSWORD=… pnpm e2e                   # contra un panel y un backend levantados
```

Durante un tiempo estuvieron escritos pero sin poder correr: sus dependencias no
estaban en el lockfile, porque se escribieron desde una máquina cuya red
bloqueaba `registry.npmjs.org`. **La lección sigue valiendo:** una dependencia se
agrega junto con su lockfile, en el mismo commit — el CI y Render instalan con
`--frozen-lockfile`, y un `package.json` que no coincide deja el panel sin
desplegar.

## Qué prueban

No es cobertura por la cobertura. Son las cuatro cosas que, si se rompen en
silencio, terminan en un mensaje que no debía salir o en un operador que no sabe
lo que acaba de hacer:

| Archivo | Qué agarra |
|---|---|
| `enviar.test.tsx` | Que el modo no vuelva a quedar escrito a mano, que la fricción de escribir la cantidad no se pueda saltear, y que no se ofrezca enviar de verdad con la lista de destinos vacía |
| `boton-corrida.test.tsx` | Que el botón dispare una **generación** y no un diagnóstico. Es la regresión del bug que tenía el panel: un solo botón, atado a `dispararCorrida("diagnostico")`, con el producto inalcanzable desde la pantalla |
| `chip-modo.test.tsx` | Que el modo dependa de la lista de destinos (regla R4) y del envío automático (D52), **no** de la variable de entorno. Reemplazó al de la banda (D54) |
| `envio-automatico.test.tsx` | Que prender el envío automático pase por el diálogo y no guarde nada antes; que apagarlo no pida nada ni ofrezca "Deshacer" (sería prenderlo sin diálogo) |
| `errores.test.tsx` | Que la lista de errores separe urgentes de avisos, filtre por el campo `maquina` de la alerta y que "Ya lo vi" saque de la vista sin hacer desaparecer |
| `derivados.test.ts` | Las cuentas que hace el panel y no el backend: el "hoy" en hora argentina, los borradores por máquina y por día, y que una Mac apagada sin trabajo no cuente como problema |
| `navegacion.test.ts` | Que la barra de tres grupos llegue a todas las pantallas y marque el grupo correcto en las subrutas |
| `comandos.test.ts` | El catálogo de comandos para copiar |

El recorrido de `e2e/` es el de la demostración: entrar, ver el modo, llegar a
los errores, pedir una generación (y cancelarla), el freno, las corridas, las
estadísticas, los ajustes y el detalle de una máquina. **Nunca envía en modo real**, ni siquiera con la lista
abierta: un test que le puede escribir a alguien es un test que algún día le
escribe a alguien.
