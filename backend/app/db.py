"""Conexión a MongoDB con Motor.

El cliente es único para todo el proceso: lo abre el ciclo de vida de la
aplicación y lo cierra al apagar. Motor maneja su propio pool, así que abrir uno
por petición sería, además de lento, una forma de quedarse sin conexiones.

Los índices y las colecciones llegan con el modelo de datos (Sprint 1). Acá sólo
hay conexión.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from app.config import Configuracion
from app.logging import obtener_logger

log = obtener_logger(__name__)

_cliente: AsyncIOMotorClient | None = None
_base: AsyncIOMotorDatabase | None = None


def conectar(config: Configuracion) -> None:
    """Crea el cliente. No abre el socket todavía: Motor conecta perezosamente."""
    global _cliente, _base
    if _cliente is not None:
        return
    _cliente = AsyncIOMotorClient(
        config.mongo_url,
        serverSelectionTimeoutMS=config.mongo_timeout_ms,
        connectTimeoutMS=config.mongo_timeout_ms,
        tz_aware=True,
    )
    _base = _cliente[config.mongo_db]
    log.info("mongo_cliente_creado", base=config.mongo_db)


def desconectar() -> None:
    global _cliente, _base
    if _cliente is not None:
        _cliente.close()
        log.info("mongo_cliente_cerrado")
    _cliente = None
    _base = None


def obtener_base() -> AsyncIOMotorDatabase:
    """La base. Revienta si nadie llamó a `conectar()`: preferimos el error
    ruidoso al arrancar antes que un `None` viajando por el código."""
    if _base is None:
        raise RuntimeError("MongoDB no está conectado: falta conectar() en el ciclo de vida")
    return _base


async def esta_viva() -> bool:
    """¿Responde Mongo? Un `ping` al admin, con el timeout de la configuración.

    Devuelve False ante cualquier error del driver, pero **lo registra**. No es
    un `except: pass`: el resultado es explícito y queda la traza de por qué
    (08 §2, R3).
    """
    if _cliente is None:
        log.warning("mongo_sin_cliente")
        return False
    try:
        await _cliente.admin.command("ping")
    except PyMongoError as e:
        log.warning("mongo_ping_fallido", error=str(e), tipo=type(e).__name__)
        return False
    return True
