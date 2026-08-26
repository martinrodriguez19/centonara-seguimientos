"""Que Chrome esté abierto y con el puerto, sin que el vendedor haga nada.

Ninguno de estos tests lanza un navegador: `lanzar` y la detección de procesos
se reemplazan. Lo que se prueba es la decisión —abrir, no abrir, negarse— y los
flags con los que lo abriría.
"""

from __future__ import annotations

import pytest

from agente.adaptadores import navegador
from agente.adaptadores.navegador import Estado, asegurar_chrome


class Lanzador:
    """Anota el comando en vez de ejecutarlo."""

    def __init__(self) -> None:
        self.comando: list[str] = []
        self.veces = 0

    def __call__(self, comando: list[str]) -> None:
        self.veces += 1
        self.comando = comando


@pytest.fixture
def sin_chrome(monkeypatch):
    """Ni puerto abierto ni proceso corriendo: el caso de una Mac recién prendida."""

    async def no_escucha(puerto, **kwargs):
        return False

    monkeypatch.setattr(navegador, "puerto_escucha", no_escucha)
    monkeypatch.setattr(navegador, "_chrome_corriendo", lambda: False)


async def test_si_el_puerto_ya_escucha_no_se_abre_nada(monkeypatch) -> None:
    """Es el caso normal si Chrome arranca al iniciar sesión."""

    async def escucha(puerto, **kwargs):
        return True

    monkeypatch.setattr(navegador, "puerto_escucha", escucha)
    lanzador = Lanzador()

    resultado = await asegurar_chrome(lanzar=lanzador)

    assert resultado.estado is Estado.YA_ESTABA
    assert resultado.utilizable
    assert lanzador.veces == 0


async def test_chrome_abierto_sin_puerto_no_se_le_cierra_al_vendedor(monkeypatch) -> None:
    """⚠️ Es la máquina de alguien que está trabajando.

    Cerrarle las pestañas para mandar un mensaje comercial es exactamente el
    tipo de cosa que hace que una herramienta se desinstale. Se reporta y la
    corrida se frena.
    """

    async def no_escucha(puerto, **kwargs):
        return False

    monkeypatch.setattr(navegador, "puerto_escucha", no_escucha)
    monkeypatch.setattr(navegador, "_chrome_corriendo", lambda: True)
    lanzador = Lanzador()

    resultado = await asegurar_chrome(lanzar=lanzador)

    assert resultado.estado is Estado.SIN_PUERTO
    assert not resultado.utilizable
    assert lanzador.veces == 0, "no se lanza otra instancia: no habilitaría el puerto"
    assert "cerrarlo" in resultado.detalle


async def test_lo_abre_con_los_tres_flags(sin_chrome, monkeypatch, tmp_path) -> None:
    """⚠️ Los tres, y ninguno sobra.

    Sin `--user-data-dir` explícito, Chrome 136+ ignora el puerto en silencio.
    Sin `--profile-directory`, abre `Default`, que en una máquina con varios
    perfiles no es el que tiene la extensión ni la sesión de WhatsApp.
    """
    falso_chrome = tmp_path / "chrome"
    falso_chrome.write_text("")
    lanzador = Lanzador()

    #  El puerto nunca abre: interesa el comando, no la espera.
    await asegurar_chrome(
        chrome_bin=str(falso_chrome),
        perfil="/Users/vendedor/Library/Application Support/Google/Chrome",
        perfil_dir="Profile 3",
        puerto=9222,
        espera_s=0.01,
        lanzar=lanzador,
    )

    assert lanzador.veces == 1
    assert lanzador.comando[0] == str(falso_chrome)
    assert "--remote-debugging-port=9222" in lanzador.comando
    assert any("--user-data-dir=" in a and "Google" in a for a in lanzador.comando)
    assert "--profile-directory=Profile 3" in lanzador.comando


# ---------------------------------------------------------------------------
# El Chrome del vendedor, sin puerto: el que necesita LISTAR
# ---------------------------------------------------------------------------


async def test_si_el_chrome_del_vendedor_ya_esta_abierto_no_se_toca(monkeypatch) -> None:
    monkeypatch.setattr(navegador, "_chrome_corriendo", lambda: True)
    lanzador = Lanzador()

    resultado = await navegador.asegurar_abierto(lanzar=lanzador)

    assert resultado.estado is Estado.YA_ESTABA
    assert resultado.utilizable
    assert lanzador.veces == 0


async def test_con_chrome_cerrado_lo_abre_y_sin_flags_de_puerto(monkeypatch, tmp_path) -> None:
    """⚠️ Sin `--remote-debugging-port` ni `--user-data-dir`: eso era del diseño
    de CDP que Chrome mató (D24). Acá sólo hace falta la ventana abierta, con el
    perfil que tiene la extensión."""
    falso_chrome = tmp_path / "chrome"
    falso_chrome.write_text("")
    vivo = {"si": False}
    lanzador = Lanzador()

    def lanzar_y_revivir(comando):
        lanzador(comando)
        vivo["si"] = True

    monkeypatch.setattr(navegador, "_chrome_corriendo", lambda: vivo["si"])
    monkeypatch.setattr(navegador, "ESPERA_EXTENSION_S", 0.0)

    resultado = await navegador.asegurar_abierto(
        chrome_bin=str(falso_chrome), perfil_dir="Profile 1", lanzar=lanzar_y_revivir
    )

    assert resultado.estado is Estado.ABIERTO
    assert resultado.utilizable
    assert lanzador.comando == [str(falso_chrome), "--profile-directory=Profile 1"]
    assert not any("remote-debugging-port" in argumento for argumento in lanzador.comando)


async def test_si_el_chrome_del_vendedor_no_arranca_lo_dice(monkeypatch, tmp_path) -> None:
    falso_chrome = tmp_path / "chrome"
    falso_chrome.write_text("")
    monkeypatch.setattr(navegador, "_chrome_corriendo", lambda: False)

    resultado = await navegador.asegurar_abierto(
        chrome_bin=str(falso_chrome), espera_s=0.05, lanzar=Lanzador()
    )

    assert resultado.estado is Estado.NO_SE_PUDO
    assert not resultado.utilizable


async def test_sin_ejecutable_lo_dice_y_no_lanza_nada(sin_chrome, monkeypatch) -> None:
    monkeypatch.setattr(navegador, "encontrar_chrome", lambda: None)
    lanzador = Lanzador()

    resultado = await asegurar_chrome(lanzar=lanzador)

    assert resultado.estado is Estado.NO_SE_PUDO
    assert lanzador.veces == 0
    assert "no se encontró" in resultado.detalle


async def test_si_lanza_pero_el_puerto_no_abre_lo_reporta(sin_chrome, tmp_path) -> None:
    """El modo de falla de Chrome 136: arranca, acepta el flag, y no abre nada."""
    falso = tmp_path / "chrome"
    falso.write_text("")

    resultado = await asegurar_chrome(chrome_bin=str(falso), espera_s=0.05, lanzar=Lanzador())

    assert resultado.estado is Estado.NO_SE_PUDO
    assert not resultado.utilizable
    assert "--user-data-dir" in resultado.detalle


async def test_un_ejecutable_que_no_existe_no_se_intenta(sin_chrome) -> None:
    lanzador = Lanzador()

    resultado = await asegurar_chrome(chrome_bin="/no/existe/chrome", lanzar=lanzador)

    assert resultado.estado is Estado.NO_SE_PUDO
    assert lanzador.veces == 0


def test_las_rutas_por_defecto_son_del_sistema_en_el_que_corre() -> None:
    """En macOS son otras que en Windows, y el instalador no las pasa."""
    import sys

    rutas = [str(r) for r in navegador.rutas_probables()]
    perfil = str(navegador.perfil_por_defecto())

    if sys.platform == "darwin":
        assert any("Google Chrome.app" in r for r in rutas)
        assert "Library/Application Support" in perfil
    elif sys.platform == "win32":
        assert any("chrome.exe" in r for r in rutas)
        assert "User Data" in perfil


def test_el_puerto_sincronico_y_el_async_contestan_lo_mismo() -> None:
    """El diagnóstico usa el sincrónico; el motor, el async. No pueden discrepar."""
    import asyncio

    #  Un puerto que casi seguro no tiene nada.
    puerto = 59_237
    assert navegador.puerto_escucha_sync(puerto, timeout=0.3) is False
    assert asyncio.run(navegador.puerto_escucha(puerto, timeout=0.3)) is False
