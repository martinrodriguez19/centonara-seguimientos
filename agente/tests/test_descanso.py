"""El descanso (D64) del lado del agente, sin suspender nada de verdad.

`correr` se inyecta: ningún test lanza rundll32 ni pmset. A la mañana la
máquina la despierta el vendedor; el agente sólo la duerme, una vez por
descanso y nunca en el medio de un job.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from agente.descanso import Descanso

ARGENTINA = timezone(timedelta(hours=-3))
AHORA = datetime(2026, 10, 2, 3, 0, tzinfo=ARGENTINA).astimezone(UTC)  # viernes 03:00
HASTA = datetime(2026, 10, 2, 8, 0, tzinfo=ARGENTINA).astimezone(UTC)
HORARIOS = {"descanso_hasta": HASTA.isoformat(), "suspender": True}


class Sistema:
    def __init__(self) -> None:
        self.comandos: list[list[str]] = []

    def __call__(self, comando: list[str], timeout: float) -> tuple[int, str]:
        self.comandos.append(comando)
        return 0, ""


def descanso(tmp_path: Path, sistema: Sistema, plataforma: str = "win32", *, ahora=AHORA):
    d = Descanso(plataforma=plataforma, casa=tmp_path, correr=sistema, ahora=lambda: ahora)
    d.recibir(HORARIOS)
    return d


def marca(tmp_path: Path) -> dict | None:
    archivo = tmp_path / ".centonara" / "estado" / "descanso.json"
    return json.loads(archivo.read_text()) if archivo.exists() else None


def test_windows_suspende(tmp_path: Path) -> None:
    sistema = Sistema()
    assert descanso(tmp_path, sistema).revisar(False) == "suspende"
    assert sistema.comandos == [["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]]
    assert marca(tmp_path) == {"hasta": HASTA.isoformat(), "suspendida": True}


def test_mac_suspende(tmp_path: Path) -> None:
    sistema = Sistema()
    assert descanso(tmp_path, sistema, "darwin").revisar(False) == "suspende"
    assert sistema.comandos == [["pmset", "sleepnow"]]


def test_no_programa_ningun_despertar(tmp_path: Path) -> None:
    """La despierta el vendedor cuando llega (02/10/2026)."""
    sistema = Sistema()
    descanso(tmp_path, sistema).revisar(False)
    todo = " ".join(" ".join(c) for c in sistema.comandos)
    assert "WakeToRun" not in todo and "pmset repeat" not in todo and "powercfg" not in todo


def test_con_un_job_en_curso_espera_pero_deja_la_marca(tmp_path: Path) -> None:
    """La marca va igual: el guardián no tiene que revivirlo mientras tanto."""
    sistema = Sistema()
    assert descanso(tmp_path, sistema).revisar(True) is None
    assert marca(tmp_path) == {"hasta": HASTA.isoformat(), "suspendida": False}
    assert sistema.comandos == []


def test_una_sola_vez_por_descanso(tmp_path: Path) -> None:
    """Si alguien la despierta a mano a las 3 de la mañana, no se la vuelve a dormir."""
    sistema = Sistema()
    d = descanso(tmp_path, sistema)
    d.revisar(False)
    d.revisar(False)
    #  Aunque el agente se reinicie: la marca está en disco.
    descanso(tmp_path, sistema).revisar(False)
    assert len(sistema.comandos) == 1


def test_el_descanso_siguiente_vuelve_a_suspender(tmp_path: Path) -> None:
    sistema = Sistema()
    descanso(tmp_path, sistema).revisar(False)
    manana = Descanso(
        plataforma="win32",
        casa=tmp_path,
        correr=sistema,
        ahora=lambda: AHORA + timedelta(days=1),
    )
    manana.recibir({**HORARIOS, "descanso_hasta": (HASTA + timedelta(days=1)).isoformat()})
    assert manana.revisar(False) == "suspende"
    assert len(sistema.comandos) == 2


def test_sin_suspender_descansa_igual(tmp_path: Path) -> None:
    sistema = Sistema()
    d = descanso(tmp_path, sistema)
    d.recibir({**HORARIOS, "suspender": False})
    assert d.revisar(False) == "descansa_sin_suspender"
    assert sistema.comandos == []


def test_fuera_del_descanso_no_hace_nada_y_borra_la_marca(tmp_path: Path) -> None:
    sistema = Sistema()
    d = descanso(tmp_path, sistema)
    d.revisar(True)
    assert marca(tmp_path) is not None

    d.recibir({"descanso_hasta": None})
    assert d.revisar(False) is None
    assert marca(tmp_path) is None


def test_cuando_pasa_la_hora_se_olvida(tmp_path: Path) -> None:
    descanso(tmp_path, Sistema()).revisar(True)
    despues = descanso(tmp_path, Sistema(), ahora=HASTA + timedelta(minutes=1))
    assert despues.revisar(False) is None
    assert marca(tmp_path) is None


@pytest.mark.parametrize("basura", [None, "x", {"descanso_hasta": "no es una fecha"}])
def test_un_horario_ilegible_no_duerme_a_nadie(tmp_path: Path, basura) -> None:
    sistema = Sistema()
    d = Descanso(plataforma="win32", casa=tmp_path, correr=sistema, ahora=lambda: AHORA)
    d.recibir(basura)
    assert d.revisar(False) is None
    assert sistema.comandos == []


def test_en_linux_no_hay_que_suspender(tmp_path: Path) -> None:
    sistema = Sistema()
    assert descanso(tmp_path, sistema, "linux").revisar(False) == "suspende"
    assert sistema.comandos == []


async def test_la_vuelta_en_paralelo(tmp_path: Path) -> None:
    sistema = Sistema()
    d = descanso(tmp_path, sistema)

    async def sin_esperar(_: float) -> None:
        return None

    await d.vigilar(lambda: False, parar=asyncio.Event(), dormir=sin_esperar, vueltas=1)
    assert len(sistema.comandos) == 1
