"""structlog: un solo formato de log para todo el agente.

Mismo criterio que en el backend, y por el mismo motivo: cuando alguien pida
soporte va a mandar este log. Que las líneas propias y las de las librerías
(httpx en la fase 1, Playwright en la 3) salgan con el mismo formato es la
diferencia entre leerlo y adivinarlo.

Este archivo no está en la estructura de 06 §2 — la doc no le asigna un lugar a
la configuración de structlog. Va acá porque es infraestructura del proceso, no
dominio.
"""

import logging
import sys
from typing import Any

import structlog

from agente.config import Configuracion

# Ruidosas y sin valor propio. Todavía no están instaladas; fijarles el nivel
# igual es inofensivo y evita tener que acordarse cuando lleguen.
_RUIDOSAS = ("httpx", "httpcore", "urllib3", "asyncio")


def _consola_en_utf8() -> None:
    """Deja la salida en UTF-8 antes de escribir la primera línea.

    En Windows la consola usa cp1252 salvo que se le diga otra cosa, y un
    nombre con acento en un log revienta el proceso con UnicodeEncodeError. Es
    el mismo problema #6 del MVP que obliga a `encoding="utf-8"` en
    `subprocess.run` (07 §5), en la otra punta.

    Sin `except`: si la salida no se puede dejar en UTF-8, es mejor no arrancar
    que arrancar y caerse más tarde con el primer acento (R3).
    """
    for flujo in (sys.stdout, sys.stderr):
        # Empaquetado sin consola, `sys.stdout` es None.
        reconfigurar = getattr(flujo, "reconfigure", None)
        if reconfigurar is not None:
            reconfigurar(encoding="utf-8", errors="replace")


def configurar_logs(config: Configuracion) -> None:
    """Deja structlog y el logging estándar escribiendo el mismo formato.

    Idempotente: llamarla dos veces no duplica handlers.
    """
    _consola_en_utf8()

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
        # Los registros que vienen del logging estándar no pasaron por los
        # procesadores compartidos: se los aplicamos acá.
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

    for nombre in _RUIDOSAS:
        logging.getLogger(nombre).setLevel(logging.WARNING)


def obtener_logger(nombre: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(nombre)
