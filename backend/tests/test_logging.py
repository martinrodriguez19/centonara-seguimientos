"""structlog: que quede configurado y que no se duplique."""

import logging

import pytest
import structlog

from app.config import Configuracion
from app.logging import configurar_logs, obtener_logger


def test_configurar_dos_veces_no_duplica_handlers() -> None:
    """El ciclo de vida corre una vez, pero los tests y el recargador de
    `fastapi dev` no: si duplicara handlers, cada línea saldría dos veces."""
    config = Configuracion(_env_file=None)

    configurar_logs(config)
    primera = len(logging.getLogger().handlers)
    configurar_logs(config)

    assert len(logging.getLogger().handlers) == primera == 1


def test_los_eventos_salen_con_sus_campos(capsys: pytest.CaptureFixture[str]) -> None:
    configurar_logs(Configuracion(_env_file=None, entorno="staging", log_json=True))

    obtener_logger("prueba").info("corrida_creada", corrida_id="c-1")

    salida = capsys.readouterr().out
    assert '"event": "corrida_creada"' in salida
    assert '"corrida_id": "c-1"' in salida
    assert '"logger": "prueba"' in salida


def test_el_logger_es_el_de_structlog() -> None:
    """structlog devuelve un proxy perezoso; `bind()` lo resuelve. Lo que se
    verifica es que al resolverse quede el `BoundLogger` de la biblioteca
    estándar, que es el que sabe hablar con los handlers de uvicorn."""
    configurar_logs(Configuracion(_env_file=None))

    assert isinstance(obtener_logger(__name__).bind(), structlog.stdlib.BoundLogger)
