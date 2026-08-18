"""Punto de entrada del backend.

    uv run fastapi dev app/main.py     → http://localhost:8000/docs

Esqueleto del Sprint 0 (T0.3): arranca, conecta y responde. No hay modelo de
datos, no hay lógica de negocio y **no hay código de envío** (R7). Los routers
de 04-CONTRATOS-API.md se montan a partir del Sprint 1.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel

from app import db
from app.config import Configuracion, Entorno, obtener_configuracion
from app.logging import configurar_logs, obtener_logger

log = obtener_logger(__name__)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    config = obtener_configuracion()
    configurar_logs(config)
    db.conectar(config)
    log.info("backend_arrancado", entorno=config.entorno)
    try:
        yield
    finally:
        db.desconectar()
        log.info("backend_apagado")


app = FastAPI(
    title="Sistema de Seguimiento Comercial v2",
    version="0.1.0",
    lifespan=ciclo_de_vida,
)


# Dependencias, con nombre. `Annotated` en vez de `= Depends(...)`: es la forma
# recomendada por FastAPI y evita que el valor por defecto sea una llamada.
MongoVivo = Annotated[bool, Depends(db.esta_viva)]
ConfigActual = Annotated[Configuracion, Depends(obtener_configuracion)]


class SaludRespuesta(BaseModel):
    ok: bool
    mongo: bool
    entorno: Entorno


@app.get("/health", response_model=SaludRespuesta, tags=["sistema"])
async def health(
    respuesta: Response,
    mongo: MongoVivo,
    config: ConfigActual,
) -> SaludRespuesta:
    """Estado del proceso, para el balanceador y para el panel.

    Devuelve 200 si todo está bien y **503 si Mongo no responde**: un chequeo de
    salud que contesta 200 con `ok: false` no lo lee nadie, y Render necesita el
    código de estado para sacar la instancia de rotación.

    No confundir con `GET /api/salud` (04 §3.5), que es el estado de las ocho
    máquinas y llega más adelante. Éste es del proceso, no del negocio: sin
    autenticación y fuera de `/api`.
    """
    ok = mongo
    if not ok:
        respuesta.status_code = 503
        log.warning("health_degradado", mongo=mongo)
    return SaludRespuesta(ok=ok, mongo=mongo, entorno=config.entorno)
