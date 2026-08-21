"""Punto de entrada del backend.

    uv run fastapi dev app/main.py     → http://localhost:8000/docs

Esqueleto: arranca, conecta y responde. No hay modelo de datos ni lógica de
negocio todavía. Los routers de 02-ARQUITECTURA.md §4 se montan en la fase 1.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from app import db
from app.api import agente, panel
from app.config import Configuracion, Entorno, obtener_configuracion
from app.core.esquema import inicializar
from app.logging import configurar_logs, obtener_logger

log = obtener_logger(__name__)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    config = obtener_configuracion()
    configurar_logs(config)
    db.conectar(config)

    # Asegurar el esquema al arrancar evita el modo de falla más tonto:
    # desplegar y que la primera consulta falle porque nadie corrió el script.
    # Es idempotente, así que no cuesta nada.
    #
    # Pero NO puede impedir el arranque. Si Mongo no responde, el proceso tiene
    # que levantar igual para que /health conteste 503 y Render saque la
    # instancia de rotación. Reventar acá es peor: Render no distingue "Mongo
    # tuvo un hipo" de "el despliegue está roto", y entra en bucle de reinicio
    # justo cuando alguien necesita leer el chequeo de salud.
    try:
        await inicializar(db.obtener_base())
    except PyMongoError as error:
        log.error("esquema_no_asegurado", error=str(error), tipo=type(error).__name__)

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

app.include_router(agente.router)
app.include_router(panel.router)


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
