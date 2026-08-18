# Sistema de Seguimiento Comercial v2

Monorepo. Un solo `git clone` y tenés todo.

## Arrancar

Requisitos y paso a paso completo en [`docs/06-ENTORNO-LOCAL.md`](docs/06-ENTORNO-LOCAL.md).
Objetivo: de cero a todo corriendo en **40 minutos**.

```bash
cp .env.example .env
docker compose -f infra/docker-compose.dev.yml up -d
```

> **Node 22 o superior, no negociable.** Es el problema #1 del historial del MVP.

## Qué hay acá

| Carpeta | Qué va |
|---|---|
| `backend/` | API FastAPI. La lógica de negocio vive acá y en ningún otro lado |
| `frontend/` | Panel Next.js 15 |
| `agente/` | Lo que corre en la PC del vendedor |
| `n8n/` | Workflows exportados como JSON |
| `infra/` | Compose local y despliegue |
| `docs/` | Documentación viva del proyecto |

## Antes de escribir la primera línea

Leé [`docs/05-REGLAS-INVIOLABLES.md`](docs/05-REGLAS-INVIOLABLES.md). No describe buenas
prácticas: describe los límites que el sistema no puede cruzar.

**Del Sprint 0 al 3 no existe código de envío en este repositorio (R7).** No es un olvido.
Mientras se construyen las fundaciones queremos que sea técnicamente imposible que salga un
mensaje.
