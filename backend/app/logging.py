"""structlog: un solo formato de log para todo el backend.

Los logs de uvicorn pasan por el mismo procesador que los nuestros. Si no, en
Render conviven dos formatos distintos y buscar una corrida en el historial se
vuelve un ejercicio de arqueología.

Este archivo no está en la estructura de 06 §2 — la doc no le asigna un lugar a
la configuración de structlog. Va acá porque es infraestructura del proceso, no
dominio.
"""

import logging
import sys
from typing import Any

import structlog

from app.config import Configuracion

# uvicorn instala sus propios handlers al arrancar. Si no se los sacamos, sus
# líneas salen en un formato y las nuestras en otro.
_AJENAS = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi")

# `uvicorn.access` registra una línea por petición: con el chequeo de salud de
# Render pegándole cada pocos segundos, tapa todo lo demás. Lo que importa de una
# petición lo loguea la aplicación.
_RUIDOSAS = ("uvicorn.access", "pymongo", "asyncio")


def configurar_logs(config: Configuracion) -> None:
    """Deja structlog y el logging estándar escribiendo el mismo formato.

    Idempotente: llamarla dos veces no duplica handlers.
    """
    compartidos: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    render: Any = (
        structlog.processors.JSONRenderer()
        if config.logs_en_json
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            *compartidos,
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formateador = structlog.stdlib.ProcessorFormatter(
        # Los registros que vienen del logging estándar (uvicorn) no pasaron por
        # los procesadores compartidos: se los aplicamos acá.
        foreign_pre_chain=compartidos,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            render,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formateador)

    raiz = logging.getLogger()
    for anterior in list(raiz.handlers):
        raiz.removeHandler(anterior)
    raiz.addHandler(handler)
    raiz.setLevel(logging.INFO)

    for nombre in _AJENAS:
        ajeno = logging.getLogger(nombre)
        ajeno.handlers.clear()
        ajeno.propagate = True

    for nombre in _RUIDOSAS:
        logging.getLogger(nombre).setLevel(logging.WARNING)


def obtener_logger(nombre: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(nombre)
