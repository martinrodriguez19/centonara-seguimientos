"""La marca de vida y el reinicio por cambio de versión (D46)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agente import reinicio


def test_la_marca_de_vida_dice_version_sha_pid_y_si_esta_ocupado(tmp_path: Path) -> None:
    cuando = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    reinicio.marcar_vivo("7912e13 2026-09-09", ocupado=True, casa=tmp_path, ahora=cuando)

    marca = json.loads((tmp_path / ".centonara" / "estado" / "vivo.json").read_text("utf-8"))
    assert marca["version"] == "7912e13 2026-09-09"
    assert marca["sha"] == "7912e13"
    assert marca["ocupado"] is True
    assert marca["cuando"] == cuando.isoformat()
    assert isinstance(marca["pid"], int)
    assert reinicio.leer_vivo(tmp_path) == marca


def test_una_version_sin_sha_deja_sha_nulo(tmp_path: Path) -> None:
    reinicio.marcar_vivo("0.1.0-dev", casa=tmp_path)
    assert reinicio.leer_vivo(tmp_path)["sha"] is None


def test_no_queda_un_temporal_a_medias(tmp_path: Path) -> None:
    reinicio.marcar_vivo("7912e13", casa=tmp_path)
    carpeta = tmp_path / ".centonara" / "estado"
    assert sorted(p.name for p in carpeta.iterdir()) == ["vivo.json"]


def test_sin_marca_leer_devuelve_none(tmp_path: Path) -> None:
    assert reinicio.leer_vivo(tmp_path) is None


def test_una_marca_ilegible_no_rompe_nada(tmp_path: Path) -> None:
    carpeta = tmp_path / ".centonara" / "estado"
    carpeta.mkdir(parents=True)
    (carpeta / "vivo.json").write_text("{esto no es json", "utf-8")
    assert reinicio.leer_vivo(tmp_path) is None


def test_cambio_la_version_compara_el_disco_con_lo_que_arranco(tmp_path: Path) -> None:
    assert reinicio.cambio_la_version(tmp_path, "0.1.0-dev") is False
    (tmp_path / "VERSION").write_text("7912e13 2026-09-09\n", "utf-8")
    assert reinicio.cambio_la_version(tmp_path, "0.1.0-dev") is True
    assert reinicio.cambio_la_version(tmp_path, "7912e13 2026-09-09") is False


def test_en_windows_se_relanza_como_hijo_desacoplado(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No depende de quién lo arrancó: sirve en una PC instalada a mano y con la tarea."""
    import subprocess

    lanzados: list[dict] = []

    class PopenFalso:
        def __init__(self, argumentos, **kwargs):
            lanzados.append({"argumentos": argumentos, **kwargs})

    monkeypatch.setattr(reinicio.sys, "platform", "win32")
    monkeypatch.setattr(reinicio.sys, "argv", ["agente.main"])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(subprocess, "Popen", PopenFalso)

    assert reinicio.reejecutar() == 0
    assert lanzados[0]["argumentos"] == [sys.executable, "-m", "agente.main"]
    assert (tmp_path / "Centonara" / "logs" / "agente.log").exists()


def test_en_windows_si_no_puede_relanzarse_sale_con_el_codigo_de_reinicio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """La tarea programada, si existe, lo reintenta al ver el fallo."""
    import subprocess

    def revienta(*args, **kwargs):
        raise OSError("sin permiso")

    monkeypatch.setattr(reinicio.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(subprocess, "Popen", revienta)
    assert reinicio.reejecutar() == reinicio.SALIDA_REINICIO


def test_en_posix_se_reemplaza_a_si_mismo(monkeypatch: pytest.MonkeyPatch) -> None:
    llamadas: list[tuple] = []
    monkeypatch.setattr(reinicio.sys, "platform", "darwin")
    monkeypatch.setattr(
        reinicio.os, "execv", lambda ejecutable, args: llamadas.append((ejecutable, args))
    )
    monkeypatch.setattr(reinicio.sys, "argv", ["agente.main", "--simulado"])

    reinicio.reejecutar()

    assert llamadas == [(sys.executable, [sys.executable, "-m", "agente.main", "--simulado"])]
