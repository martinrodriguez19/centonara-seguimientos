# Sistema de Seguimiento Comercial

Un botón que hace que Claude lea los chats recientes de WhatsApp Web en las Macs de los
vendedores, redacte un seguimiento para cada uno, y los envíe desde la línea de cada vendedor.

Monorepo. Un solo `git clone` y tenés todo.

## Arrancar

```bash
cp .env.example .env
docker compose -f infra/docker-compose.dev.yml up -d
```

Paso a paso completo en [`docs/04-AGENTE.md`](docs/04-AGENTE.md) §11.

> **Node 22 o superior, no negociable.** Es el problema #1 del historial del MVP.

## Qué hay acá

| Carpeta | Qué va |
|---|---|
| `backend/` | API FastAPI. La lógica de negocio vive acá y en ningún otro lado |
| `frontend/` | El panel, en Next.js 15 |
| `agente/` | Lo que corre en la Mac del vendedor |
| `infra/` | Compose local y despliegue |
| `docs/` | Documentación del proyecto |
| `referencia/` | El MVP fase 1, congelado. **No se importa nada desde ahí** |

## Antes de escribir la primera línea

Leé [`docs/03-REGLAS.md`](docs/03-REGLAS.md). Es corto, y describe los límites que el sistema no
puede cruzar. Después, [`docs/00-INDICE.md`](docs/00-INDICE.md) te dice en qué orden leer el resto.

## A quién le puede escribir el sistema

A los números que estén en `configuracion.destinos_permitidos`, y a nadie más. Se verifica en el
backend al encolar y otra vez en el agente antes de escribir.

**Mientras esa lista tenga sólo los números de prueba, es técnicamente imposible que un cliente
real reciba un mensaje.** Abrirla es un acto deliberado que queda registrado en auditoría. Es la
regla R4, y reemplaza a la regla anterior de que el código de envío no existiera en el repositorio.
