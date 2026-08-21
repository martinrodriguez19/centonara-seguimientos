"""Piezas comunes de los tests.

Los tests del esqueleto **no necesitan MongoDB**: el chequeo de Mongo entra por
inyección de dependencias y se reemplaza acá. Un test que depende de un servicio
levantado es un test que en CI se marca como `skip`, y un `skip` es un test que
no existe.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app import db
from app.config import Configuracion, obtener_configuracion
from app.core.guardrails import HUSO_COMERCIAL
from app.main import app


def ar(dia: int, hora: int, minuto: int = 0, *, mes: int = 8, anio: int = 2026) -> datetime:
    """Una hora de Argentina, entregada en UTC como la recibe el código.

    Todo el sistema trabaja en UTC, menos la ventana horaria (G6), que describe
    la jornada de una persona y por eso se evalúa en hora local.

    Los tiempos fijos de los tests estaban escritos directamente en UTC con
    nombres que hablaban de la jornada —`MIERCOLES = 11:00 UTC`, leído como
    media mañana— y eso era justo lo que ocultaba que G6 comparaba contra el
    reloj equivocado: los mismos números pasaban el test, y en Argentina
    significaban las ocho de la mañana, fuera de la ventana.

    Escribir la hora que ve la persona y convertir acá hace que un test que
    dice "media mañana" siga queriendo decir eso el día que algo cambie.
    """
    return datetime(anio, mes, dia, hora, minuto, tzinfo=HUSO_COMERCIAL).astimezone(UTC)


_VARIABLES = (
    "ENTORNO",
    "MONGO_URL",
    "MONGO_DB",
    "MONGO_TIMEOUT_MS",
    "JWT_SECRET",
    "AUTH_EMAIL_FROM",
    "SMTP_URL",
    "SENTRY_DSN",
    "LOG_JSON",
)


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Que el resultado no dependa de lo que cada uno tenga exportado."""
    for variable in _VARIABLES:
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def configurar() -> Iterator[Callable[..., Configuracion]]:
    """Fija la configuración de la aplicación para un test.

    `_env_file=None`: nada de leer el `.env` de la máquina de quien corre esto.
    """

    def _configurar(**valores: object) -> Configuracion:
        config = Configuracion(_env_file=None, **valores)
        app.dependency_overrides[obtener_configuracion] = lambda: config
        return config

    yield _configurar
    app.dependency_overrides.clear()


@pytest.fixture
def mongo_responde() -> Iterator[Callable[[bool], None]]:
    """Decide si Mongo contesta el ping, sin Mongo."""

    def _responde(vivo: bool) -> None:
        app.dependency_overrides[db.esta_viva] = lambda: vivo

    yield _responde
    app.dependency_overrides.clear()


@pytest.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    transporte = ASGITransport(app=app)
    async with AsyncClient(transport=transporte, base_url="http://test") as c:
        yield c
