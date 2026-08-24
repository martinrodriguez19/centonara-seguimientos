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


def test_la_opcion_simulado_gana_sobre_el_entorno() -> None:
    config = Configuracion(modo="real")
    assert resolver_modo(config, forzar_simulado=True) == "simulado"
    assert resolver_modo(config, forzar_simulado=False) == "real"


@pytest.mark.parametrize("modo", ["prueba", "real"])
def test_con_simulado_arranca_aunque_el_entorno_pida_enviar(
    modo: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La opción explícita lleva hacia el lado seguro, no al revés."""
    monkeypatch.setenv("AGENTE_MODO", modo)
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
