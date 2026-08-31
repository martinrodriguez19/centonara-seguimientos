"""El motor de contingencias: orden, rastro y falla contenida.

Lo que se asevera acá es el contrato del que cuelga todo el plan de cascadas:
la primera estrategia que sirve gana y las de atrás NO corren; un escalón que
revienta no tira la cascada; y el registro dice siempre qué se intentó y qué
ganó — porque ese registro es lo que viaja a Mongo y decide qué escalón se
promueve después de ver producción.
"""

from __future__ import annotations

import pytest

from agente.adaptadores.cascada import en_cascada


def exitosa(valor="abierto"):
    async def estrategia():
        return valor

    return estrategia


def fallida():
    async def estrategia():
        return False

    return estrategia


def rota():
    async def estrategia():
        raise RuntimeError("se rompió a mitad de camino")

    return estrategia


async def test_la_primera_que_sirve_gana_y_las_demas_no_corren() -> None:
    corridas: list[str] = []

    def espia(nombre: str, resultado):
        async def estrategia():
            corridas.append(nombre)
            return resultado

        return estrategia

    registro: dict = {}
    resultado = await en_cascada(
        "abrir_chat",
        [
            ("A1", espia("A1", False)),
            ("A2", espia("A2", True)),
            ("A3", espia("A3", True)),
        ],
        registro=registro,
    )

    assert resultado is True
    assert corridas == ["A1", "A2"]
    assert registro["abrir_chat"] == {"gano": "A2", "intentadas": ["A1", "A2"]}


async def test_un_escalon_que_revienta_no_tira_la_cascada() -> None:
    registro: dict = {}
    resultado = await en_cascada(
        "abrir_chat",
        [("A1", rota()), ("A2", exitosa())],
        registro=registro,
    )

    assert resultado == "abierto"
    assert registro["abrir_chat"]["gano"] == "A2"
    assert registro["abrir_chat"]["intentadas"] == ["A1", "A2"]


async def test_agotada_devuelve_none_y_lo_registra() -> None:
    registro: dict = {}
    resultado = await en_cascada(
        "abrir_chat",
        [("A1", fallida()), ("A2", rota()), ("A3", fallida())],
        registro=registro,
    )

    assert resultado is None
    assert registro["abrir_chat"] == {"gano": None, "intentadas": ["A1", "A2", "A3"]}


async def test_devuelve_el_valor_de_la_estrategia_no_un_bool() -> None:
    """Las cascadas que abren el navegador devuelven una página, no True."""
    pagina = object()
    registro: dict = {}

    resultado = await en_cascada("abrir_navegador", [("D1", exitosa(pagina))], registro=registro)
    assert resultado is pagina


async def test_sin_estrategias_es_agotada_no_un_error() -> None:
    registro: dict = {}

    assert await en_cascada("vacia", [], registro=registro) is None
    assert registro["vacia"] == {"gano": None, "intentadas": []}


async def test_las_asincronicas_de_verdad_tambien_cortan_en_la_ganadora() -> None:
    """Regresión barata contra un `await` olvidado en el motor."""
    import asyncio

    async def lenta_y_buena():
        await asyncio.sleep(0)
        return "gané"

    nunca = pytest.fail  # si la tercera corre, el test muere acá

    async def no_debe_correr():
        nunca("la cascada siguió después de la ganadora")

    registro: dict = {}
    resultado = await en_cascada(
        "x",
        [("uno", fallida()), ("dos", lenta_y_buena), ("tres", no_debe_correr)],
        registro=registro,
    )
    assert resultado == "gané"
