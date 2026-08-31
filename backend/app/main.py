"""Punto de entrada del backend.

    uv run fastapi dev app/main.py     → http://localhost:8000/docs

Esqueleto: arranca, conecta y responde. No hay modelo de datos ni lógica de
negocio todavía. Los routers de 02-ARQUITECTURA.md §4 se montan en la fase 1.
"""

import asyncio
import contextlib
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

# Cada cuánto corre el mantenimiento de fondo (G2). Corto frente a los 40
# minutos que tarda un job en darse por colgado: lo que importa es que corra,
# no que corra seguido.
INTERVALO_MANTENIMIENTO_S = 5 * 60


async def mantenimiento_periodico(*, intervalo_s: float = INTERVALO_MANTENIMIENTO_S) -> None:
    """El watchdog que APScheduler nunca fue (G2).

    `recuperar_colgados` y `vencer_viejos` existen desde el principio y sus
    docstrings dicen «corre en APScheduler» — pero APScheduler nunca entró al
    proyecto. Sin esto, el job de una máquina apagada queda `tomado` para
    siempre y la corrida no termina nunca: es el «varias máquinas se quedaron
    ahí» del 28/08. Un loop de asyncio dentro del proceso alcanza y no agrega
    dependencia.

    Cada vuelta se protege sola: un hipo de Mongo se loguea y se vuelve a
    intentar en la próxima — el watchdog no puede ser otra cosa que se muere.
    """
    from app.core import cola, mensajes

    while True:
        await asyncio.sleep(intervalo_s)
        try:
            base = db.obtener_base()
            recuperados = await cola.recuperar_colgados(base)
            vencidos = await mensajes.vencer_viejos(base)
            if recuperados or vencidos:
                log.info("mantenimiento_corrido", recuperados=recuperados, vencidos=vencidos)
        except Exception as error:
            log.warning("mantenimiento_fallo", error=str(error), tipo=type(error).__name__)


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

    # G2: el mantenimiento de fondo arranca con el proceso y muere con él.
    vigilante = asyncio.create_task(mantenimiento_periodico())

    log.info("backend_arrancado", entorno=config.entorno)
    try:
        yield
    finally:
        vigilante.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await vigilante
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
