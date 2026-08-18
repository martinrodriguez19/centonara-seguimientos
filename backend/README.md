# backend — API FastAPI. El único lugar donde vive la lógica de negocio (D8, R1).

## Correr

```bash
uv sync
uv run fastapi dev app/main.py      # → http://localhost:8000/docs
```

Necesita el MongoDB del compose local (`docker compose -f infra/docker-compose.dev.yml up -d`).
La configuración sale del `.env` de la raíz del repo; los valores por defecto de `.env.example`
sirven para local sin tocar nada.

```bash
uv run pytest -q                    # tests
uv run ruff check . && uv run ruff format --check .
```

## Qué hay hoy (Sprint 0, T0.3)

Sólo el esqueleto: arranca, conecta y responde.

| Archivo | Qué hace |
|---|---|
| `app/main.py` | La aplicación y `GET /health` |
| `app/config.py` | Pydantic Settings: todo lo que se lee del entorno |
| `app/db.py` | Cliente Motor, único para el proceso |
| `app/logging.py` | structlog, un solo formato para la app y para uvicorn |

`GET /health` devuelve `{"ok": true, "mongo": true, "entorno": "local"}` con `200`, o `503` si
Mongo no responde.

El modelo de datos, los guardrails y los endpoints de `04-CONTRATOS-API.md` llegan en el Sprint 1.

**No hay código de envío en este repositorio hasta el Sprint 4 (R7).** El job `sin-envio` de CI lo
verifica en cada PR.
