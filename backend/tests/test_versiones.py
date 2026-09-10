"""La versión esperada del agente (D45): la fija el panel, o la rama con caché."""

from __future__ import annotations

import pytest

from app.core import versiones

REPO = "alguien/repo"


@pytest.fixture(autouse=True)
def cache_limpia() -> None:
    versiones.olvidar_cache()


def contar(sha: str = "1234567890ab"):
    """Un resolvedor que devuelve siempre lo mismo y cuenta cuántas veces lo llamaron."""
    llamadas: list[str] = []

    async def _resolver(repo: str, rama: str) -> str:
        llamadas.append(rama)
        return sha

    return _resolver, llamadas


# ---------------------------------------------------------------------------
# normalizar / coincide: funciones puras
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("7912e13", "7912e13"),
        ("  7912E13 ", "7912e13"),
        ("7912e13c5d3fa2b1c4d5e6f7a8b9c0d1e2f3a4b5", "7912e13c5d3fa2b1c4d5e6f7a8b9c0d1e2f3a4b5"),
        ("main", ""),
        ("791", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_normalizar_acepta_un_sha_y_nada_mas(valor, esperado) -> None:
    assert versiones.normalizar(valor) == esperado


def test_coincide_compara_el_sha_reportado_con_el_esperado() -> None:
    assert versiones.coincide("7912e13 2026-09-09", "7912e13c5d3fa2b1") is True
    assert versiones.coincide("7912e13c5d3f", "7912e13") is True
    assert versiones.coincide("4decc8c 2026-09-09", "7912e13c5d3fa2b1") is False


def test_coincide_no_afirma_nada_sin_un_sha_de_cada_lado() -> None:
    """`0.1.0` no está "desactualizada": nunca se instaló con el actualizador."""
    assert versiones.coincide("0.1.0", "7912e13") is None
    assert versiones.coincide("0.1.0-dev", "7912e13") is None
    assert versiones.coincide(None, "7912e13") is None
    assert versiones.coincide("7912e13", "") is None


# ---------------------------------------------------------------------------
# esperada: el panel manda, la rama se cachea, no saber no es "lo último"
# ---------------------------------------------------------------------------


async def test_la_version_fijada_en_el_panel_manda_sin_preguntar_a_nadie() -> None:
    resolver, llamadas = contar()
    esperada = await versiones.esperada(
        {"version_agente_esperada": "4DECC8C"}, repo=REPO, rama="main", resolver=resolver
    )
    assert esperada == versiones.Esperada("4decc8c", "panel")
    assert llamadas == []


async def test_sin_version_fijada_se_resuelve_la_rama_una_vez_y_se_cachea() -> None:
    resolver, llamadas = contar()
    primera = await versiones.esperada({}, repo=REPO, rama="main", resolver=resolver, ahora=0.0)
    segunda = await versiones.esperada(
        {}, repo=REPO, rama="main", resolver=resolver, ahora=versiones.TTL_S - 1
    )
    assert primera == segunda == versiones.Esperada("1234567890ab", "rama")
    assert llamadas == ["main"]


async def test_pasado_el_ttl_se_vuelve_a_preguntar() -> None:
    resolver, llamadas = contar()
    await versiones.esperada({}, repo=REPO, rama="main", resolver=resolver, ahora=0.0)
    await versiones.esperada(
        {}, repo=REPO, rama="main", resolver=resolver, ahora=versiones.TTL_S + 1
    )
    assert llamadas == ["main", "main"]


async def test_si_github_no_contesta_y_no_hay_cache_no_se_sabe() -> None:
    """Las máquinas no se actualizan a "no sé": seguir con lo que hay es mejor."""

    async def _roto(repo: str, rama: str) -> str:
        raise OSError("sin red")

    esperada = await versiones.esperada({}, repo=REPO, rama="main", resolver=_roto)
    assert esperada == versiones.Esperada("", "desconocida")


async def test_si_github_no_contesta_pero_hubo_respuesta_antes_vale_la_vieja() -> None:
    resolver, _ = contar("1234567890ab")
    await versiones.esperada({}, repo=REPO, rama="main", resolver=resolver, ahora=0.0)

    async def _roto(repo: str, rama: str) -> str:
        raise OSError("sin red")

    esperada = await versiones.esperada(
        {}, repo=REPO, rama="main", resolver=_roto, ahora=versiones.TTL_S * 10
    )
    assert esperada == versiones.Esperada("1234567890ab", "rama")


async def test_una_respuesta_que_no_es_un_sha_no_se_toma() -> None:
    async def _raro(repo: str, rama: str) -> str:
        return "<html>Rate limit exceeded</html>"

    esperada = await versiones.esperada({}, repo=REPO, rama="main", resolver=_raro)
    assert esperada.sha == ""
