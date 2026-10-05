"""Los horarios del panel en la tarea del actualizador (D63), sin tocar el sistema.

`correr` se inyecta: ningún test lanza PowerShell ni launchctl. En Mac se
trabaja sobre un plist de verdad en `tmp_path`.
"""

from __future__ import annotations

import plistlib
from datetime import UTC, timedelta, timezone
from pathlib import Path

import pytest

from agente.tareas import ARGENTINA, Reprogramador, a_hora_local

DISPARADORES = [
    {"hora": "15:00", "dias": [1, 2, 3, 4, 5, 6, 7], "para": "actualizar"},
    {"hora": "16:45", "dias": [1, 2, 3, 4, 5, 6], "para": "revisar_antes_de_corrida"},
]


class Consola:
    """Anota los comandos y contesta lo que el test diga."""

    def __init__(self, codigo: int = 0, salida: str = "") -> None:
        self.comandos: list[list[str]] = []
        self.codigo = codigo
        self.salida = salida

    def __call__(self, comando: list[str]) -> tuple[int, str]:
        self.comandos.append(comando)
        return self.codigo, self.salida


# ---------------------------------------------------------------------------
# La hora local
# ---------------------------------------------------------------------------


def test_en_argentina_la_hora_queda_igual() -> None:
    assert a_hora_local("16:45", [1, 2], zona_local=ARGENTINA) == (16, 45, [1, 2])


def test_en_otra_zona_se_corre() -> None:
    assert a_hora_local("15:00", [1], zona_local=UTC) == (18, 0, [1])


def test_si_cruza_la_medianoche_se_corren_los_dias() -> None:
    #  23:45 en Argentina son las 02:45 del día siguiente en UTC.
    assert a_hora_local("23:45", [6, 7], zona_local=UTC) == (2, 45, [1, 7])
    madrid = timezone(timedelta(hours=2))
    assert a_hora_local("20:45", [1], zona_local=madrid) == (1, 45, [2])


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------


def windows(tmp_path: Path, consola: Consola) -> Reprogramador:
    return Reprogramador(plataforma="win32", casa=tmp_path, correr=consola, zona_local=ARGENTINA)


def test_windows_pone_un_disparador_por_horario(tmp_path: Path) -> None:
    consola = Consola()
    r = windows(tmp_path, consola)

    r.recibir({"disparadores": DISPARADORES, "actualizar_ya": False})

    [comando] = consola.comandos
    assert comando[0] == "powershell.exe"
    guion = comando[-1]
    assert "-AtLogOn" in guion
    assert (
        "-DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday -At '15:00'" in guion
    )
    assert "-DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday,Saturday -At '16:45'" in guion
    assert "Set-ScheduledTask -TaskName 'Centonara Actualizador'" in guion
    assert "RepetitionInterval" not in guion
    assert r.estado == "ok"


def test_windows_sin_disparadores_vuelve_a_cada_hora(tmp_path: Path) -> None:
    consola = Consola()
    r = windows(tmp_path, consola)
    r.recibir({"disparadores": [], "actualizar_ya": False})
    assert "RepetitionInterval (New-TimeSpan -Hours 1)" in consola.comandos[0][-1]
    assert r.estado == "cada_hora"


def test_lo_mismo_no_se_vuelve_a_aplicar_y_un_cambio_si(tmp_path: Path) -> None:
    consola = Consola()
    r = windows(tmp_path, consola)
    r.recibir({"disparadores": DISPARADORES})
    r.recibir({"disparadores": DISPARADORES})
    assert len(consola.comandos) == 1
    r.recibir({"disparadores": DISPARADORES[:1]})
    assert len(consola.comandos) == 2


def test_si_windows_no_deja_queda_la_falla_y_no_revienta(tmp_path: Path) -> None:
    consola = Consola(codigo=1, salida="Acceso denegado")
    r = windows(tmp_path, consola)
    r.recibir({"disparadores": DISPARADORES})
    assert r.estado is not None and r.estado.startswith("falla")
    assert "Acceso denegado" in r.estado
    #  Se reintenta en el próximo latido.
    r.recibir({"disparadores": DISPARADORES})
    assert len(consola.comandos) == 2


def test_con_el_actualizador_corriendo_espera(tmp_path: Path) -> None:
    (tmp_path / ".centonara").mkdir()
    (tmp_path / ".centonara" / "actualizador.lock").write_text("1")
    consola = Consola()
    r = windows(tmp_path, consola)
    r.recibir({"disparadores": DISPARADORES})
    assert consola.comandos == []
    assert r.estado is None


def test_actualizar_ahora_dispara_una_sola_vez_por_pedido(tmp_path: Path) -> None:
    consola = Consola()
    r = windows(tmp_path, consola)
    for _ in range(3):
        r.recibir({"disparadores": [], "actualizar_ya": True})
    disparos = [c for c in consola.comandos if c[0] == "schtasks"]
    assert disparos == [["schtasks", "/Run", "/TN", "Centonara Actualizador"]]
    r.recibir({"disparadores": [], "actualizar_ya": False})
    r.recibir({"disparadores": [], "actualizar_ya": True})
    assert len([c for c in consola.comandos if c[0] == "schtasks"]) == 2


@pytest.mark.parametrize("basura", [None, "texto", 3])
def test_algo_que_no_es_un_horario_se_ignora(tmp_path: Path, basura) -> None:
    consola = Consola()
    r = windows(tmp_path, consola)
    r.recibir(basura)
    assert consola.comandos == []
    assert r.estado is None


# ---------------------------------------------------------------------------
# Mac
# ---------------------------------------------------------------------------


def plist_del_instalador(casa: Path) -> Path:
    carpeta = casa / "Library" / "LaunchAgents"
    carpeta.mkdir(parents=True)
    plist = carpeta / "com.centonara.actualizador.plist"
    plist.write_bytes(
        plistlib.dumps(
            {
                "Label": "com.centonara.actualizador",
                "ProgramArguments": ["/usr/bin/python3", "/x/actualizar.py", "--repo", "/x"],
                "RunAtLoad": True,
                "StartInterval": 3600,
            }
        )
    )
    return plist


def mac(tmp_path: Path, consola: Consola) -> Reprogramador:
    return Reprogramador(plataforma="darwin", casa=tmp_path, correr=consola, zona_local=ARGENTINA)


def test_mac_reescribe_el_calendario_y_recarga_solo_el_actualizador(tmp_path: Path) -> None:
    plist = plist_del_instalador(tmp_path)
    consola = Consola()
    r = mac(tmp_path, consola)

    r.recibir({"disparadores": DISPARADORES})

    datos = plistlib.loads(plist.read_bytes())
    assert "StartInterval" not in datos
    calendario = datos["StartCalendarInterval"]
    #  launchd cuenta el domingo como 0.
    assert {"Hour": 15, "Minute": 0, "Weekday": 0} in calendario
    assert {"Hour": 16, "Minute": 45, "Weekday": 6} in calendario
    assert {"Hour": 16, "Minute": 45, "Weekday": 0} not in calendario
    assert len(calendario) == 7 + 6
    #  Lo demás del plist queda como lo dejó el instalador.
    assert datos["ProgramArguments"][1] == "/x/actualizar.py"
    assert datos["RunAtLoad"] is True

    assert [c[:2] for c in consola.comandos] == [
        ["launchctl", "bootout"],
        ["launchctl", "bootstrap"],
    ]
    assert consola.comandos[0][2].endswith("/com.centonara.actualizador")
    assert r.estado == "ok"


def test_mac_sin_disparadores_vuelve_a_cada_hora(tmp_path: Path) -> None:
    plist = plist_del_instalador(tmp_path)
    r = mac(tmp_path, Consola())
    r.recibir({"disparadores": DISPARADORES})
    r.recibir({"disparadores": []})
    datos = plistlib.loads(plist.read_bytes())
    assert datos["StartInterval"] == 3600
    assert "StartCalendarInterval" not in datos
    assert r.estado == "cada_hora"


def test_mac_sin_plist_es_una_falla_con_nombre(tmp_path: Path) -> None:
    consola = Consola()
    r = mac(tmp_path, consola)
    r.recibir({"disparadores": DISPARADORES})
    assert r.estado is not None and "com.centonara.actualizador.plist" in r.estado
    assert consola.comandos == []


def test_mac_si_launchctl_no_lo_carga_queda_la_falla(tmp_path: Path) -> None:
    plist_del_instalador(tmp_path)
    r = mac(tmp_path, Consola(codigo=5, salida="Bootstrap failed"))
    r.recibir({"disparadores": DISPARADORES})
    assert r.estado is not None and "Bootstrap failed" in r.estado


def test_mac_actualizar_ahora_usa_kickstart_sin_matar(tmp_path: Path) -> None:
    consola = Consola()
    r = mac(tmp_path, consola)
    r.recibir({"disparadores": [], "actualizar_ya": True})
    [kick] = [c for c in consola.comandos if "kickstart" in c]
    assert "-k" not in kick


def test_en_linux_no_toca_nada(tmp_path: Path) -> None:
    consola = Consola()
    r = Reprogramador(plataforma="linux", casa=tmp_path, correr=consola)
    r.recibir({"disparadores": DISPARADORES, "actualizar_ya": True})
    assert consola.comandos == []
