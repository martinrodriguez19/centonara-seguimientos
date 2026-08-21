"""T0.3 — `GET /health`.

El criterio de salida del ticket es literal: el cuerpo tiene que ser
`{"ok": true, "mongo": true, "entorno": "local"}`. Se verifica el diccionario
entero, no campo por campo: si mañana alguien agrega una clave de más, el
contrato con el frontend (T0.4) y con Render cambió y hay que enterarse.
"""

from collections.abc import Callable

import pytest
from httpx import AsyncClient

from app import db
from app.config import Configuracion


async def test_health_con_mongo_vivo(
    cliente: AsyncClient,
    configurar: Callable[..., Configuracion],
    mongo_responde: Callable[[bool], None],
) -> None:
    configurar(entorno="local")
    mongo_responde(True)

    r = await cliente.get("/health")

    assert r.status_code == 200
    assert r.json() == {"ok": True, "mongo": True, "entorno": "local"}


async def test_health_con_mongo_caido_no_dice_que_esta_bien(
    cliente: AsyncClient,
    configurar: Callable[..., Configuracion],
    mongo_responde: Callable[[bool], None],
) -> None:
    """Si Mongo no responde, el backend no está sano. Falla cerrado (R3)."""
    configurar(entorno="local")
    mongo_responde(False)

    r = await cliente.get("/health")

    assert r.status_code == 503
    assert r.json() == {"ok": False, "mongo": False, "entorno": "local"}


@pytest.mark.parametrize("entorno", ["local", "produccion"])
async def test_health_reporta_el_entorno_real(
    entorno: str,
    cliente: AsyncClient,
    configurar: Callable[..., Configuracion],
    mongo_responde: Callable[[bool], None],
) -> None:
    """Sirve para saber contra qué se está hablando. En el MVP más de una vez se
    creyó estar en local estando en producción."""
    configurar(entorno=entorno)
    mongo_responde(True)

    r = await cliente.get("/health")

    assert r.json()["entorno"] == entorno


async def test_health_no_pide_autenticacion(
    cliente: AsyncClient,
    configurar: Callable[..., Configuracion],
    mongo_responde: Callable[[bool], None],
) -> None:
    """Lo consulta el balanceador de Render, que no tiene con qué autenticarse."""
    configurar(entorno="local")
    mongo_responde(True)

    r = await cliente.get("/health")

    assert r.status_code == 200


async def test_sin_cliente_de_mongo_la_salud_es_falsa() -> None:
    """Sin conexión no se inventa un `True`: se responde que no y se registra."""
    db.desconectar()

    assert await db.esta_viva() is False


async def test_obtener_base_sin_conectar_es_un_error() -> None:
    db.desconectar()

    with pytest.raises(RuntimeError):
        db.obtener_base()


async def test_el_backend_arranca_aunque_mongo_este_caido(monkeypatch) -> None:
    """Regresión: asegurar el esquema al arrancar no puede impedir el arranque.

    Si el ciclo de vida revienta con Mongo caído, /health nunca llega a contestar
    503 y Render no distingue "Mongo tuvo un hipo" de "el despliegue está roto":
    entra en bucle de reinicio justo cuando alguien necesita leer el chequeo.
    """
    from app.config import obtener_configuracion
    from app.main import app, ciclo_de_vida

    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:59999")
    monkeypatch.setenv("MONGO_TIMEOUT_MS", "300")
    obtener_configuracion.cache_clear()

    try:
        async with ciclo_de_vida(app):
            pass  # llegar acá ES el test
    finally:
        obtener_configuracion.cache_clear()
