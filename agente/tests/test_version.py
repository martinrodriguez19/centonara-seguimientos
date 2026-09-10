"""La versión que el agente reporta sale de `agente/VERSION`, no de una constante."""

from __future__ import annotations

from pathlib import Path

from agente import version


def test_sin_archivo_es_la_version_de_desarrollo(tmp_path: Path) -> None:
    """Una máquina donde nadie instaló nada no miente diciendo un commit."""
    assert version.leer(tmp_path) == version.SIN_INSTALAR


def test_lee_el_sha_y_la_fecha_de_la_primera_linea(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("7912e13 2026-09-09\n", encoding="utf-8")
    assert version.leer(tmp_path) == "7912e13 2026-09-09"


def test_un_archivo_vacio_vale_lo_mismo_que_ninguno(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("   \n\n", encoding="utf-8")
    assert version.leer(tmp_path) == version.SIN_INSTALAR


def test_recorta_y_normaliza_para_que_el_registro_nunca_falle(tmp_path: Path) -> None:
    """El backend acepta 64 caracteres: un archivo raro no puede tumbar el registro."""
    (tmp_path / "VERSION").write_text("abc1234    " + "x" * 200 + "\nsegunda línea", "utf-8")
    leida = version.leer(tmp_path)
    assert leida.startswith("abc1234 x")
    assert len(leida) <= version.LARGO_MAXIMO
    assert "\n" not in leida


def test_sha_extrae_el_commit_o_nada() -> None:
    assert version.sha("7912e13 2026-09-09") == "7912e13"
    assert version.sha("7912e13") == "7912e13"
    assert version.sha("0.1.0-dev") is None
    assert version.sha("") is None


def test_la_version_del_paquete_viene_de_ahi() -> None:
    """En el repo no hay `VERSION`, así que el paquete dice que es de desarrollo."""
    import agente

    carpeta = Path(agente.__file__).resolve().parent.parent
    assert agente.__version__ == version.leer(carpeta)
