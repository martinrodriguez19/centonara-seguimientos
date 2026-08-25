# tests — los tests de componente del panel. **Todavía no corren en el CI.**

Están escritos y son once, pero **sus dependencias no están en el lockfile**, así
que hoy no se pueden instalar ni ejecutar. Este archivo explica por qué y cómo
se destraba.

## Por qué quedaron a medio enganchar

Se escribieron desde una máquina Windows cuya red bloquea `registry.npmjs.org`
—falla hasta un `curl`—. Ahí se puede escribir un `package.json`, pero **no se
puede regenerar `pnpm-lock.yaml`**: pnpm necesita resolver versiones y hashes
contra el registro.

Se intentó igual, y el resultado fue el que tenía que ser: el despliegue de
Render falló en el primer paso, porque tanto Render como el CI instalan con
`--frozen-lockfile` y un `package.json` que no coincide con el lockfile es
exactamente lo que ese flag existe para rechazar.

    specifiers in the lockfile (...) don't match specs in package.json (...)

Producción no se cayó —Render conserva el despliegue anterior cuando la
compilación falla— pero quedó sin poder desplegar hasta revertirlo.

**La lección, que vale más que los tests:** una dependencia se agrega junto con
su lockfile, en el mismo commit, desde una máquina que pueda producir los dos.
No hay forma de partirlo en dos pasos sin dejar el repositorio sin desplegar en
el medio.

## Cómo se destraba, desde una máquina con acceso a npm

Un solo comando instala y lockea las siete:

```bash
pnpm add -D vitest @vitejs/plugin-react jsdom \
  @testing-library/react @testing-library/jest-dom @testing-library/user-event \
  @playwright/test
```

Después, en orden:

1. `pnpm test` — tienen que pasar los once.
2. `pnpm exec playwright install chromium webkit` — el recorrido de punta a punta
   corre en los dos, porque el parque es Mac y Safari es el que más se aparta.
3. Sacar `tests` y `e2e` del `exclude` de `tsconfig.json` y de los `ignores` de
   `eslint.config.mjs`. Están ahí sólo mientras las dependencias no existan: sin
   eso, `next build` falla por módulos que no se pueden instalar.
4. Reponer el paso de tests en `.github/workflows/ci.yml`, entre `Tipos` y
   `Compila`:

   ```yaml
   - name: Tests
     run: pnpm test
   ```

5. **Commitear `pnpm-lock.yaml` junto con todo lo anterior**, en un solo commit.

## Qué prueban

No es cobertura por la cobertura. Son las cuatro cosas que, si se rompen en
silencio, terminan en un mensaje que no debía salir o en un operador que no sabe
lo que acaba de hacer:

| Archivo | Qué agarra |
|---|---|
| `enviar.test.tsx` | Que el modo no vuelva a quedar escrito a mano, que la fricción de escribir la cantidad no se pueda saltear, y que no se ofrezca enviar de verdad con la lista de destinos vacía |
| `boton-corrida.test.tsx` | Que el botón dispare una **generación** y no un diagnóstico. Es la regresión del bug que tenía el panel: un solo botón, atado a `dispararCorrida("diagnostico")`, con el producto inalcanzable desde la pantalla |
| `banda-modo.test.tsx` | Que el modo dependa de la lista de destinos (regla R4) y **no** de la variable de entorno |

El recorrido de `e2e/` es el de la demostración: entrar, generar, revisar,
llegar a las corridas. **Nunca envía en modo real**, ni siquiera con la lista
abierta: un test que le puede escribir a alguien es un test que algún día le
escribe a alguien.
