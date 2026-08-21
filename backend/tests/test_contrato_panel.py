"""Que los tipos del panel describan lo que el backend devuelve de verdad.

`docs/RETOMAR.md` anotaba el riesgo con todas las letras: *"el panel se escribió
contra los tipos del cliente de API, no contra respuestas reales"*. Casi tres mil
líneas de TypeScript compiladas contra tipos escritos a mano, y ningún test que
comparara esos tipos con un `dict` real.

Compilar no ayuda acá. Los endpoints del panel devuelven `dict[str, Any]`, así
que el esquema de OpenAPI sale como `{"type": "object"}` y `tsc` valida los
tipos del panel **contra sí mismos**. Un campo que el backend deja de mandar, o
uno nuevo que nadie llevó a la pantalla, pasan los dos en verde.

Este test lee `frontend/lib/panel.ts`, saca los campos de cada `export type`, y
los compara con la respuesta real. Encontró que `/configuracion` devolvía
`palabras_comerciales` —la lista que decide si un chat parece de trabajo, y la
que mueve la tasa de retención que la pantalla de métricas manda calibrar— sin
que la pantalla de configuración pudiera tocarla.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

import pytest

from app import db
from app.api import panel
from app.api.panel import AltaMaquina, CambioMaquina, NuevaCorrida
from app.core.esquema import inicializar

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

PANEL_TS = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "panel.ts"

# Campos que el tipo declara y la respuesta puede no traer. `actualizado_en`
# aparece recién con el primer cambio guardado.
OPCIONALES = {"Configuracion": {"actualizado_en"}}

SECRETO = "secreto-de-prueba-largo"


def campos_declarados() -> dict[str, set[str]]:
    """Los campos de cada `export type X = { ... }` de `panel.ts`.

    Deliberadamente tonto: un parser de TypeScript acá sería más frágil que la
    convención de que los tipos del panel se escriben planos, uno por línea.
    """
    texto = PANEL_TS.read_text(encoding="utf-8")
    tipos: dict[str, set[str]] = {}
    for bloque in re.finditer(r"export type (\w+) = \{(.*?)\n\};", texto, re.S):
        cuerpo = re.sub(r"/\*.*?\*/", "", bloque.group(2), flags=re.S)
        tipos[bloque.group(1)] = set(re.findall(r"^\s*(\w+)\??:", cuerpo, re.M))
    return tipos


def comparar(tipo: str, respuesta: dict) -> None:
    """Los dos lados, no uno.

    Que falte un campo rompe la pantalla. Que sobre es más silencioso y por eso
    peor: es una capacidad del backend que nadie puede usar, y nadie se entera.
    """
    declarados = campos_declarados()[tipo]
    devueltos = set(respuesta)
    faltan = declarados - devueltos - OPCIONALES.get(tipo, set())
    sobran = devueltos - declarados
    assert not faltan, f"{tipo}: el panel espera y el backend no devuelve {sorted(faltan)}"
    assert not sobran, f"{tipo}: el backend devuelve y el panel ignora {sorted(sobran)}"


@pytest.fixture(autouse=True)
def configurar(monkeypatch):
    """El mismo secreto para la cookie y para quien la verifica.

    Sin esto el resultado depende de si quien corre los tests tiene un `.env`.
    """
    from app.config import obtener_configuracion

    monkeypatch.setenv("SESION_SECRET", SECRETO)
    obtener_configuracion.cache_clear()
    yield
    obtener_configuracion.cache_clear()


@pytest.fixture
async def base(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    db_prueba = cliente[nombre]
    await inicializar(db_prueba)
    monkeypatch.setattr(db, "obtener_base", lambda: db_prueba)
    try:
        yield db_prueba
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


@sin_mongo
async def test_el_panel_ts_declara_los_tipos_que_se_comparan() -> None:
    """Si el parser deja de encontrarlos, los demás tests pasarían vacíos."""
    tipos = campos_declarados()
    for nombre in ("Estado", "Maquina", "Corrida", "Configuracion", "Metricas", "Revision"):
        assert tipos.get(nombre), f"no se pudo leer el tipo {nombre} de panel.ts"


@sin_mongo
async def test_estado_vacio_coincide(base) -> None:
    """Sin datos: es lo primero que ve el panel la primera vez que se abre."""
    comparar("Estado", await panel.estado(None))


@sin_mongo
async def test_configuracion_coincide(base) -> None:
    comparar("Configuracion", await panel.ver_configuracion(None))


@sin_mongo
async def test_metricas_coinciden(base) -> None:
    comparar("Metricas", await panel.ver_metricas(None))


@sin_mongo
async def test_maquina_coincide(base) -> None:
    await panel.alta_maquina(AltaMaquina(maquina="pc-1", nombre="Prueba"), None)
    estado = await panel.estado(None)
    comparar("Maquina", estado["maquinas"][0])


@sin_mongo
async def test_corrida_y_revision_coinciden(base) -> None:
    """Dar de alta no alcanza: hay que activar. Es la regla de F5.8."""
    await panel.alta_maquina(AltaMaquina(maquina="pc-1", nombre="Prueba"), None)
    await panel.editar_maquina("pc-1", CambioMaquina(activo=True, acepto_condiciones=True), None)

    disparo = await panel.disparar_corrida(NuevaCorrida(tipo="diagnostico"), None)
    comparar("Corrida", await panel.ver_corrida(disparo["id"], None))
    comparar("Revision", await panel.mensajes_de_la_corrida(disparo["id"], None))


# ---------------------------------------------------------------------------
# El camino de error, que es por donde se coló el primero
# ---------------------------------------------------------------------------


@sin_mongo
async def test_un_error_de_validacion_trae_detail_como_lista(base) -> None:
    """⚠️ `detail` tiene DOS formas, y el panel recibe las dos.

    En un error nuestro es una cadena —`"no hay nada que cambiar"`—, pero en un
    error de validación FastAPI manda una **lista de objetos**, uno por campo:

        {"detail": [{"loc": ["body", "maquina"], "msg": "String should ..."}]}

    El cliente del panel lo tenía tipado como `string` a secas, así que esa
    lista terminaba en `ErrorDeApi.message` y la pantalla mostraba
    `[object Object]`. Lo encontró alguien dando de alta una máquina llamada
    "PC Principal".

    Este test fija la forma: si FastAPI la cambia, o si alguien saca la
    restricción del identificador, `leerDetalle()` en `frontend/lib/panel.ts`
    deja de servir y hay que enterarse acá.
    """
    from httpx import ASGITransport, AsyncClient

    from app.core import sesion
    from app.main import app

    # El secreto se fija acá y no se lee del entorno. Con `config.sesion_secret`
    # el test pasaba en una máquina con `.env` —la cookie y el endpoint usaban
    # el mismo valor— y en CI, donde no hay `.env`, el secreto era vacío, la
    # cookie no validaba y llegaba un 401 antes de mirar el cuerpo.
    cookie = sesion.emitir(SECRETO)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://prueba",
        cookies={sesion.NOMBRE_COOKIE: cookie},
    ) as http:
        respuesta = await http.post(
            "/api/vendedores", json={"maquina": "PC Principal", "nombre": "Prueba"}
        )

    assert respuesta.status_code == 422
    detail = respuesta.json()["detail"]
    assert isinstance(detail, list), "el panel espera una lista acá"

    problema = detail[0]
    assert set(problema) >= {"loc", "msg"}, "leerDetalle() usa `loc` y `msg`"
    assert problema["loc"][-1] == "maquina"
    assert isinstance(problema["msg"], str)


@sin_mongo
async def test_el_identificador_de_maquina_sigue_siendo_un_slug(base) -> None:
    """El texto de ayuda del panel promete esto, palabra por palabra."""
    from app.api.panel import AltaMaquina

    for bueno in ("mac-rocio", "pc-1", "pc-principal"):
        AltaMaquina(maquina=bueno, nombre="x")

    for malo in ("PC Principal", "pc principal", "-pc", "PC", "pc_principal"):
        with pytest.raises(ValueError):
            AltaMaquina(maquina=malo, nombre="x")
