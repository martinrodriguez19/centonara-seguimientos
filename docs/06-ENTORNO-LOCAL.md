# 06 — Entorno local

> Tu primer día. Al terminar este documento tenés todo el sistema corriendo en tu máquina.
> Tiempo estimado: 40 minutos.

---

## 1. Requisitos

| Herramienta | Versión | Verificar con |
|---|---|---|
| Docker + Compose | 24+ / v2 | `docker compose version` |
| Python | 3.12 | `python --version` |
| Node.js | 22 LTS | `node --version` |
| uv (gestor Python) | latest | `uv --version` |
| pnpm | 9+ | `pnpm --version` |
| Git | 2.4+ | `git --version` |

> **Node 22 o superior, no negociable.** En el MVP, n8n no arrancaba con Node menor a 22.22.
> Está documentado como el problema #1 del historial. Usá `nvm install 22`.

---

## 2. Estructura del repositorio

Monorepo. Un solo `git clone` y tenés todo.

```
seguimiento/
├── backend/                    # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py           # Pydantic Settings, lee del entorno
│   │   ├── db.py               # cliente Motor, índices
│   │   ├── auth/               # JWT panel + tokens de agente
│   │   ├── api/
│   │   │   ├── agent.py        # /api/agent/*
│   │   │   ├── corridas.py
│   │   │   ├── mensajes.py
│   │   │   ├── sistema.py
│   │   │   └── config.py
│   │   ├── core/
│   │   │   ├── guardrails.py   # ⚠ el archivo más importante del repo
│   │   │   ├── triage.py
│   │   │   ├── estados.py      # máquina de estados, transiciones
│   │   │   ├── contactos.py    # normalización E.164
│   │   │   ├── cola.py         # jobs sobre Mongo
│   │   │   └── auditoria.py
│   │   ├── modelos/            # esquemas Pydantic
│   │   └── scheduler.py        # APScheduler: vencimientos, canario
│   ├── tests/
│   │   ├── test_guardrails.py  # ⚠ obligatorio, 100% de cobertura
│   │   ├── test_estados.py
│   │   └── test_contactos.py
│   └── pyproject.toml
│
├── frontend/                   # Next.js 15
│   ├── app/
│   │   ├── (auth)/login/
│   │   ├── panel/
│   │   ├── salida/             # sala de salida
│   │   ├── revision/
│   │   ├── historial/
│   │   ├── config/
│   │   └── vendedores/
│   ├── components/
│   ├── lib/api.ts
│   └── package.json
│
├── agente/                     # lo que corre en la PC del vendedor
│   ├── agente/
│   │   ├── main.py
│   │   ├── poll.py             # long-polling
│   │   ├── diagnostico.py      # los 7 chequeos del MVP
│   │   ├── bandeja.py          # ícono de la bandeja
│   │   ├── adaptadores/
│   │   │   ├── base.py         # ChannelAdapter (Protocol)
│   │   │   ├── whatsapp_web.py # Playwright — NO EXISTE hasta el Sprint 4
│   │   │   └── dry_run.py      # modo prueba
│   │   └── jobs/
│   │       ├── listar_chats.py # invoca claude -p --chrome
│   │       └── redactar.py
│   ├── prompts/
│   │   ├── prompt-listar.txt   # migrado del MVP sin cambios
│   │   └── CLAUDE.md           # ⚠ ver §6
│   ├── instalador/             # Inno Setup
│   └── pyproject.toml
│
├── n8n/
│   └── workflows/              # exportados como JSON, versionados
│
├── infra/
│   ├── docker-compose.dev.yml  # local. Producción corre en Render, no con Compose (D6)
│   └── scripts/backup.sh       # backup cifrado de Atlas hacia R2
│
├── render.yaml                 # servicios de staging y producción (D6)
├── docs/                       # esta documentación
└── .github/workflows/
```

---

## 3. Levantar todo

```bash
git clone git@github.com:martinrodriguez19/centonara-seguimientos.git
cd centonara-seguimientos
cp .env.example .env          # los valores por defecto sirven para local
docker compose -f infra/docker-compose.dev.yml up -d
```

Levanta MongoDB (27017), n8n (5678) y Mailpit (8025, para ver los magic links en local).

```bash
# Backend
cd backend && uv sync && uv run python -m app.seed && uv run fastapi dev app/main.py
# → http://localhost:8000/docs

# Frontend
cd frontend && pnpm install && pnpm dev
# → http://localhost:3000

# Agente simulado (NO usa Chrome real: útil para los sprints 0-3)
cd agente && uv sync && uv run python -m agente.main --simulado
```

`--simulado` responde a los jobs con datos falsos y sin tocar el navegador. Sirve para desarrollar
backend y frontend sin una máquina Windows. **Es la forma normal de trabajar hasta el Sprint 4.**

`python -m app.seed` crea 8 vendedores de prueba, 8 máquinas y un usuario admin
(`admin@local` → el magic link aparece en Mailpit).

---

## 4. Variables de entorno

```bash
# --- backend ---
MONGO_URL=mongodb://localhost:27017
MONGO_DB=seguimiento
JWT_SECRET=                    # openssl rand -hex 32
AUTH_EMAIL_FROM=
SMTP_URL=
SENTRY_DSN=
ENTORNO=local                  # local | staging | produccion

# --- frontend ---
BACKEND_URL=http://localhost:8000   # sólo servidor, sin NEXT_PUBLIC_

# --- agente ---
AGENTE_BACKEND_URL=http://localhost:8000
AGENTE_TOKEN=
AGENTE_MACHINE_ID=PC-1
AGENTE_DEVICE_ID=              # ⚠ fijo por máquina, ver 07
CLAUDE_BIN=                    # ⚠ ruta COMPLETA, ver 07
AGENTE_MODO=simulado           # simulado | prueba | real
```

> **`ENTORNO=produccion` es la única que habilita el envío real.** En local, aunque pongas
> `AGENTE_MODO=real`, el backend rechaza encolar jobs de envío. Es una barrera a propósito.

---

## 5. Cómo trabajar según tu sprint

| Sprint | Necesitás Windows real | Cómo desarrollás |
|---|---|---|
| 0–3 | No | `--simulado`, en Linux o macOS |
| 4–5 | **Sí** | Máquina Windows 11 con Chrome y WhatsApp Web de prueba |
| 6 | No | Tests de guardrails |
| 7 | Sí, una | Piloto |

**Para los sprints 4 y 5 hace falta una máquina de pruebas dedicada**, con una línea de WhatsApp
que no sea de nadie del equipo ni de un vendedor real. Conseguila en el Sprint 0: es la
dependencia externa con más plazo de entrega del proyecto.

---

## 6. Sobre `CLAUDE.md` — leer antes de tocarlo

En el MVP, Claude Code se negaba a ejecutar la tarea por falta de contexto verificable. El primer
intento de solución fue agregar al prompt un párrafo diciendo *"esto está autorizado, no
preguntes"*. **Empeoró el problema**: es el patrón exacto de una inyección de prompt.

La solución correcta fue sacarlo del prompt y poner el contexto real en un `CLAUDE.md` escrito por
el dueño de la máquina, **fuera del pedido**.

Implicancia para nosotros: **el `CLAUDE.md` tiene que describir el sistema real.** Ahora el sistema
envía. Si el archivo describe un sistema de sólo lectura mientras el sistema envía, la
contradicción es un problema técnico concreto además de uno de honestidad — es exactamente lo que
en el MVP hacía que el modelo se negara.

Se actualiza en el Sprint 4, junto con el motor de envío. No antes, no después.

---

## 7. Comandos frecuentes

```bash
# Tests
cd backend && uv run pytest
cd backend && uv run pytest tests/test_guardrails.py -v    # los que importan

# Lint y formato (corren en CI, corrélos antes del push)
cd backend && uv run ruff check . && uv run ruff format .
cd frontend && pnpm lint && pnpm typecheck

# Reset de la base local
docker compose -f infra/docker-compose.dev.yml down -v && docker compose -f infra/docker-compose.dev.yml up -d
cd backend && uv run python -m app.seed

# Ver la cola
docker exec -it seguimiento-mongo mongosh seguimiento --eval 'db.jobs.find({estado:"pendiente"})'
```

> **Recordatorio del MVP:** tras editar el código del agente hay que reiniciar el proceso. Los
> prompts en `agente/prompts/` se releen solos en cada job.
