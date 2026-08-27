"""Piezas comunes de los tests del agente.

Ninguno de estos tests abre una conexión, lanza un proceso ni toca el
navegador: el esqueleto no sabe hacer nada de eso, y cuando sepa (fase 3) va
a probarse con `DryRunAdapter` (08 §4).
"""

import pytest

from agente.config import Configuracion, obtener_configuracion

_VARIABLES = (
    "ENTORNO",
    "LOG_JSON",
    "CLAUDE_BIN",
    "AGENTE_MODO",
    "AGENTE_BACKEND_URL",
    "AGENTE_TOKEN",
    "AGENTE_MACHINE_ID",
    "AGENTE_DEVICE_ID",
    "PLAYWRIGHT_NODEJS_PATH",
    "NODE_OPTIONS",
)


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Que el resultado no dependa de lo que cada uno tenga exportado."""
    for variable in _VARIABLES:
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture(autouse=True)
def sin_configuracion_cacheada() -> None:
    """`obtener_configuracion` cachea a propósito; entre tests, no."""
    obtener_configuracion.cache_clear()


@pytest.fixture(autouse=True)
def sin_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nada de leer el `.env` de la máquina de quien corre esto.

    Vale también para los tests que llaman a `main()`, que construye la
    configuración por su cuenta y no recibe el `_env_file` por parámetro.
    """
    monkeypatch.setitem(Configuracion.model_config, "env_file", None)
