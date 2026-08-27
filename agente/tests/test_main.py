"""El esqueleto: qué modo corre, qué modo se niega a correr, y cómo se apaga.

Estos tests son la verificación de T0.5 —"corre en Linux, macOS y Windows sin
cambios de código"— y por eso el CI los corre en los tres.
"""

import os
import signal
import threading

import pytest

from agente import main as main_mod
from agente.config import Configuracion
from agente.main import (
    SALIDA_CONFIGURACION,
    SALIDA_OK,
    atender_apagado,
    ejecutar_simulado,
    main,
    resolver_modo,
)

RAPIDO = 0.01


def test_sin_la_opcion_simulado_el_agente_es_operativo() -> None:
    """D32: no hay variable de entorno que decida esto. Simular hay que
    pedirlo en la línea de comandos, cada vez."""
    assert resolver_modo(forzar_simulado=True) == "simulado"
    assert resolver_modo(forzar_simulado=False) == "operativo"


@pytest.mark.parametrize("modo_viejo", ["simulado", "prueba", "real"])
def test_un_agente_modo_viejo_no_molesta(modo_viejo: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Las Macs instaladas antes de D32 tienen AGENTE_MODO en su `.env`: se
    ignora, sea cual sea su valor, y el agente arranca igual."""
    monkeypatch.setenv("AGENTE_MODO", modo_viejo)
    monkeypatch.setattr(
        "agente.main.ejecutar_simulado",
        lambda config, **kwargs: 0,
    )
    assert main(["--simulado"]) == SALIDA_OK


def test_una_variable_invalida_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTORNO", "producción")
    assert main(["--simulado"]) == SALIDA_CONFIGURACION


def test_late_una_vez_por_ciclo() -> None:
    config = Configuracion()
    assert ejecutar_simulado(config, intervalo_segundos=RAPIDO, ciclos=3) == 3


def test_parar_corta_el_bucle() -> None:
    """El apagado no espera a que termine el intervalo."""
    config = Configuracion()
    parar = threading.Event()
    parar.set()

    # Intervalo largo a propósito: si el apagado no cortara, el test colgaría.
    assert ejecutar_simulado(config, intervalo_segundos=600, parar=parar) == 0


def test_el_bucle_no_toca_la_red_ni_lanza_procesos(monkeypatch: pytest.MonkeyPatch) -> None:
    """El esqueleto simula: no hay bucle de consulta (fase 1) ni Chrome (fase 3)."""
    import socket
    import subprocess

    def prohibido(*args: object, **kwargs: object) -> None:
        raise AssertionError("el modo simulado no puede tocar el mundo real")

    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(subprocess, "run", prohibido)
    monkeypatch.setattr(subprocess, "Popen", prohibido)

    assert ejecutar_simulado(Configuracion(), intervalo_segundos=RAPIDO, ciclos=2) == 2


def test_el_apagado_se_registra_en_este_sistema_operativo() -> None:
    """Que `signal.signal` acepte lo que le pasamos es parte de "sin cambios de
    código": en Windows no existen las mismas señales que en Linux y macOS."""
    anteriores = {
        nombre: signal.getsignal(getattr(signal, nombre))
        for nombre in ("SIGINT", "SIGTERM", "SIGBREAK")
        if getattr(signal, nombre, None) is not None
    }
    try:
        parar = threading.Event()
        atender_apagado(parar)  # no debe levantar
        assert not parar.is_set()
    finally:
        for nombre, manejador in anteriores.items():
            signal.signal(getattr(signal, nombre), manejador)


class TestNodeParaPlaywright:
    """⚠️ El `node` que trae Playwright no carga en macOS anterior a Big Sur.

    Está compilado para macOS 11+ (13.5 en las versiones nuevas) y en Catalina
    dyld mata el proceso antes de que Playwright arranque. Pasó en producción:
    una iMac 2012 con 10.15 dejó de poder vincular el navegador después de una
    actualización de dependencias, con un error que no nombra a Playwright.

    Los tres casos que importan: que en una Mac vieja use el node del sistema,
    que en una Mac al día **no toque nada**, y que respete una decisión previa.
    """

    @staticmethod
    def _en_macos(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
        monkeypatch.setattr(main_mod.sys, "platform", "darwin")
        monkeypatch.setattr(main_mod.platform, "mac_ver", lambda: (version, ("", "", ""), ""))
        monkeypatch.delenv("PLAYWRIGHT_NODEJS_PATH", raising=False)

    def test_en_catalina_usa_el_node_del_sistema(self, monkeypatch, tmp_path) -> None:
        self._en_macos(monkeypatch, "10.15.7")
        node = tmp_path / "node"
        node.write_text("")
        monkeypatch.setattr(main_mod, "NODE_DEL_SISTEMA", (node,))

        assert main_mod.apuntar_a_node_del_sistema() == str(node)
        assert os.environ["PLAYWRIGHT_NODEJS_PATH"] == str(node)

    def test_en_una_mac_al_dia_no_toca_nada(self, monkeypatch, tmp_path) -> None:
        """El node embebido es el correcto: cambiarlo sería romper lo que anda."""
        self._en_macos(monkeypatch, "14.4")
        node = tmp_path / "node"
        node.write_text("")
        monkeypatch.setattr(main_mod, "NODE_DEL_SISTEMA", (node,))

        assert main_mod.apuntar_a_node_del_sistema() is None
        assert "PLAYWRIGHT_NODEJS_PATH" not in os.environ

    def test_big_sur_reportado_como_10_16_no_cuenta_como_viejo(self, monkeypatch, tmp_path) -> None:
        """Big Sur puede reportarse como 10.16 por compatibilidad, y ahí el
        node de Playwright carga bien. El corte está justo en ese borde."""
        self._en_macos(monkeypatch, "10.16")
        node = tmp_path / "node"
        node.write_text("")
        monkeypatch.setattr(main_mod, "NODE_DEL_SISTEMA", (node,))

        assert main_mod.apuntar_a_node_del_sistema() is None

    def test_una_eleccion_previa_se_respeta(self, monkeypatch, tmp_path) -> None:
        self._en_macos(monkeypatch, "10.15.7")
        monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", "/lo/que/eligieron")

        assert main_mod.apuntar_a_node_del_sistema() is None
        assert os.environ["PLAYWRIGHT_NODEJS_PATH"] == "/lo/que/eligieron"

    def test_sin_node_del_sistema_lo_reporta_en_vez_de_romper(self, monkeypatch, tmp_path) -> None:
        """No hay nada que hacer, pero el log tiene que decir qué falta."""
        self._en_macos(monkeypatch, "10.15.7")
        monkeypatch.setattr(main_mod, "NODE_DEL_SISTEMA", (tmp_path / "no-esta",))

        assert main_mod.apuntar_a_node_del_sistema() is None

    def test_fuera_de_macos_no_aplica(self, monkeypatch) -> None:
        monkeypatch.setattr(main_mod.sys, "platform", "win32")
        monkeypatch.delenv("PLAYWRIGHT_NODEJS_PATH", raising=False)

        assert main_mod.apuntar_a_node_del_sistema() is None


def test_sslkeylogfile_se_descarta_al_arrancar(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un antivirus con escudo web mata el proceso si esa variable queda puesta.

    Avast la deja apuntando a su driver de filtrado. OpenSSL abre ese archivo
    con `fopen` al crear cualquier contexto TLS, eso cruza la frontera entre
    runtimes de C, y en Windows termina en

        OPENSSL_Uplink(...,08): no OPENSSL_Applink

    que mata el proceso antes de que el agente llegue a presentarse. El mensaje
    no menciona ni al antivirus ni al TLS, así que sin este test nadie lo ata.
    """
    monkeypatch.setenv("SSLKEYLOGFILE", r"\.\aswMonFltProxy\427a3e2b6ab3ddc2")

    sacado = main_mod.soltar_sslkeylogfile()

    assert sacado == r"\.\aswMonFltProxy\427a3e2b6ab3ddc2"
    assert "SSLKEYLOGFILE" not in os.environ


def test_sin_sslkeylogfile_no_pasa_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SSLKEYLOGFILE", raising=False)
    assert main_mod.soltar_sslkeylogfile() is None


class TestWebcryptoParaClaudeCode:
    """⚠️ En Node 18 el servidor MCP del navegador no encuentra `crypto`.

    Sin esto, `claude -p --chrome` no conecta con la extensión y la máquina no
    lee un solo chat. Verificado en la iMac con Catalina: con el flag, el mismo
    comando que fallaba lista las pestañas.

    El detalle que costó caro: `typeof crypto` en una terminal dice `object` y
    hace descartar esta causa. Node 18 expone WebCrypto en el hilo principal
    pero no en los worker threads, que es donde corre el MCP.
    """

    @staticmethod
    def _en_macos(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
        monkeypatch.setattr(main_mod.sys, "platform", "darwin")
        monkeypatch.setattr(main_mod.platform, "mac_ver", lambda: (version, ("", "", ""), ""))
        monkeypatch.delenv("NODE_OPTIONS", raising=False)

    def test_en_catalina_enciende_el_flag(self, monkeypatch) -> None:
        self._en_macos(monkeypatch, "10.15.7")

        assert main_mod.habilitar_webcrypto_global() is True
        assert os.environ["NODE_OPTIONS"] == main_mod.FLAG_WEBCRYPTO

    def test_en_una_mac_al_dia_no_lo_toca(self, monkeypatch) -> None:
        """En Node 20 ese flag ya no existe: pasarlo haría que no arranque nada."""
        self._en_macos(monkeypatch, "14.4")

        assert main_mod.habilitar_webcrypto_global() is False
        assert "NODE_OPTIONS" not in os.environ

    def test_no_pisa_lo_que_ya_habia_en_node_options(self, monkeypatch) -> None:
        self._en_macos(monkeypatch, "10.15.7")
        monkeypatch.setenv("NODE_OPTIONS", "--max-old-space-size=4096")

        assert main_mod.habilitar_webcrypto_global() is True
        assert os.environ["NODE_OPTIONS"] == f"--max-old-space-size=4096 {main_mod.FLAG_WEBCRYPTO}"

    def test_no_lo_agrega_dos_veces(self, monkeypatch) -> None:
        self._en_macos(monkeypatch, "10.15.7")
        monkeypatch.setenv("NODE_OPTIONS", main_mod.FLAG_WEBCRYPTO)

        assert main_mod.habilitar_webcrypto_global() is False
        assert os.environ["NODE_OPTIONS"].count(main_mod.FLAG_WEBCRYPTO) == 1

    def test_fuera_de_macos_no_aplica(self, monkeypatch) -> None:
        monkeypatch.setattr(main_mod.sys, "platform", "win32")
        monkeypatch.delenv("NODE_OPTIONS", raising=False)

        assert main_mod.habilitar_webcrypto_global() is False
