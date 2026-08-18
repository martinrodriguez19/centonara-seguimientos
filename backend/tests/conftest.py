"""Piezas comunes de los tests.

Los tests del esqueleto **no necesitan MongoDB**: el chequeo de Mongo entra por
inyección de dependencias y se reemplaza acá. Un test que depende de un servicio
levantado es un test que en CI se marca como `skip`, y un `skip` es un test que
no existe.
"""

from collections.abc import AsyncIterator, Callable, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app import db
from app.config import Configuracion, obtener_configuracion
from app.main import app

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
