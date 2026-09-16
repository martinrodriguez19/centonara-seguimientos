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


# ---------------------------------------------------------------------------
# El token de GitHub y "desde cuándo no se sabe" (D53)
# ---------------------------------------------------------------------------


# El resolvedor real, guardado al importar: el `conftest` lo reemplaza en cada
# test por uno de mentira, y los tests del token necesitan el de verdad (con el
# cliente HTTP falseado abajo, así que ninguno toca la red).
RESOLVER_REAL = versiones._resolver_en_github


def resolvedor_real_falso(monkeypatch, *, contesta: str = "1234567890ab"):
    """El resolvedor real con el cliente HTTP falseado: captura los headers que irían a GitHub."""
    import httpx

    monkeypatch.setattr(versiones, "_resolver_en_github", RESOLVER_REAL)
    visto: dict = {}

    class _Respuesta:
        text = contesta

        def raise_for_status(self) -> None:
            return None

    class _Cliente:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, url: str, headers: dict):
            visto["url"] = url
            visto["headers"] = headers
            return _Respuesta()

    monkeypatch.setattr(httpx, "AsyncClient", _Cliente)
    return visto


async def test_con_token_va_en_el_header_y_no_en_el_log(monkeypatch, caplog) -> None:
    visto = resolvedor_real_falso(monkeypatch)
    esperada = await versiones.esperada({}, repo=REPO, rama="main", token="ghp_secreto")
    assert esperada.sha == "1234567890ab"
    assert visto["headers"]["Authorization"] == "Bearer ghp_secreto"
    assert "ghp_secreto" not in caplog.text


async def test_sin_token_no_se_manda_authorization(monkeypatch) -> None:
    visto = resolvedor_real_falso(monkeypatch)
    await versiones.esperada({}, repo=REPO, rama="main")
    assert "Authorization" not in visto["headers"]
    assert visto["headers"]["Accept"] == "application/vnd.github.sha"


async def test_el_token_no_aparece_en_el_log_cuando_github_falla(monkeypatch, caplog) -> None:
    import httpx

    class _Cliente:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, url: str, headers: dict):
            raise OSError("sin red")

    monkeypatch.setattr(httpx, "AsyncClient", _Cliente)
    monkeypatch.setattr(versiones, "_resolver_en_github", RESOLVER_REAL)
    esperada = await versiones.esperada({}, repo=REPO, rama="main", token="ghp_secreto")
    assert esperada.sha == ""
    assert "ghp_secreto" not in caplog.text


async def test_desconocida_desde_se_anota_la_primera_vez_que_falla() -> None:
    async def _roto(repo: str, rama: str) -> str:
        raise OSError("sin red")

    assert versiones.desconocida_desde() is None
    await versiones.esperada({}, repo=REPO, rama="main", resolver=_roto, ahora=100.0)
    assert versiones.desconocida_desde() == 100.0
    #  La segunda falla no mueve la marca: lo que interesa es cuánto lleva así.
    await versiones.esperada({}, repo=REPO, rama="main", resolver=_roto, ahora=500.0)
    assert versiones.desconocida_desde() == 100.0


async def test_desconocida_desde_se_anota_aunque_valga_la_cache_vieja() -> None:
    """Con caché vencida y GitHub caído, las máquinas siguen con lo viejo: un push no llega."""
    resolver, _ = contar("1234567890ab")
    await versiones.esperada({}, repo=REPO, rama="main", resolver=resolver, ahora=0.0)

    async def _roto(repo: str, rama: str) -> str:
        raise OSError("sin red")

    momento = versiones.TTL_S * 10.0
    esperada = await versiones.esperada({}, repo=REPO, rama="main", resolver=_roto, ahora=momento)
    assert esperada.sha == "1234567890ab"
    assert versiones.desconocida_desde() == momento


async def test_desconocida_desde_se_limpia_al_resolver() -> None:
    async def _roto(repo: str, rama: str) -> str:
        raise OSError("sin red")

    await versiones.esperada({}, repo=REPO, rama="main", resolver=_roto, ahora=100.0)
    resolver, _ = contar()
    await versiones.esperada({}, repo=REPO, rama="main", resolver=resolver, ahora=200.0)
    assert versiones.desconocida_desde() is None


async def test_la_version_fijada_no_toca_la_marca() -> None:
    async def _roto(repo: str, rama: str) -> str:
        raise OSError("sin red")

    await versiones.esperada({}, repo=REPO, rama="main", resolver=_roto, ahora=100.0)
    await versiones.esperada(
        {"version_agente_esperada": "4decc8c"}, repo=REPO, rama="main", resolver=_roto
    )
    assert versiones.desconocida_desde() == 100.0
