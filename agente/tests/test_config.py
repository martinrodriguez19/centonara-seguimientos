"""Configuración: lo que se lee del entorno y lo que se rechaza."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from agente.config import Configuracion


def test_lee_las_variables_del_agente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTE_BACKEND_URL", "https://api.ejemplo.com")
    monkeypatch.setenv("AGENTE_TOKEN", "tok-123")
    monkeypatch.setenv("AGENTE_MACHINE_ID", "PC-7")
    monkeypatch.setenv("AGENTE_DEVICE_ID", "dev-abc")

    config = Configuracion()

    assert config.backend_url == "https://api.ejemplo.com"
    assert config.token == "tok-123"
    assert config.machine_id == "PC-7"
    assert config.device_id == "dev-abc"


def test_claude_bin_se_lee_sin_prefijo(monkeypatch: pytest.MonkeyPatch) -> None:
    """`CLAUDE_BIN` es la única del agente que no lleva AGENTE_ (06 §4)."""
    monkeypatch.setenv("CLAUDE_BIN", r"C:\Users\vendedor\AppData\claude.exe")
    assert Configuracion().claude_bin == r"C:\Users\vendedor\AppData\claude.exe"


def test_por_defecto_es_local() -> None:
    config = Configuracion()
    assert config.entorno == "local"


def test_un_agente_modo_viejo_en_el_env_se_ignora(monkeypatch: pytest.MonkeyPatch) -> None:
    """D32: la perilla AGENTE_MODO se eliminó — fue la causa del 26/08.

    Las Macs ya instaladas la tienen en su `.env`: no puede romper el arranque
    ni tener ningún efecto. La única forma de no ser operativo es `--simulado`.
    """
    monkeypatch.setenv("AGENTE_MODO", "simulado")
    config = Configuracion()
    assert not hasattr(config, "modo")


def test_un_entorno_inventado_no_arranca() -> None:
    """`ENTORNO=produccion` es la que habilita el envío real (05 §6)."""
    with pytest.raises(ValidationError):
        Configuracion(entorno="produccón")


def test_el_resumen_para_log_no_incluye_el_token() -> None:
    """Los logs del agente terminan en un adjunto de soporte."""
    config = Configuracion(token="tok-secreto")
    resumen = config.resumen_para_log()

    assert "tok-secreto" not in repr(resumen)
    assert resumen["token_definido"] is True
    assert Configuracion(token="").resumen_para_log()["token_definido"] is False


def test_los_logs_van_en_json_fuera_de_local() -> None:
    assert Configuracion(entorno="local").logs_en_json is False
    assert Configuracion(entorno="produccion").logs_en_json is True
    assert Configuracion(entorno="produccion").logs_en_json is True
    # El override manual gana sobre la heurística.
    assert Configuracion(entorno="local", log_json=True).logs_en_json is True


def test_la_carpeta_del_agente_no_depende_del_directorio_actual(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Se resuelve desde el paquete, no desde donde se ejecutó el comando."""
    from agente.config import CARPETA_AGENTE

    monkeypatch.chdir(tmp_path)
    assert (CARPETA_AGENTE / "agente" / "main.py").is_file()


def test_env_example_no_comenta_al_lado_de_un_valor_vacio() -> None:
    """Un comentario al lado de un valor VACÍO se convierte en el valor.

    `python-dotenv` recorta el `# ...` sólo cuando hay algo antes. Con la línea
    `AGENTE_DEVICE_ID=              # fijo por máquina`, el valor pasa a ser
    literalmente `# fijo por máquina` —una cadena no vacía— y el chequeo de
    diagnóstico, que sólo mira que no esté vacío, devolvía **OK en verde con el
    deviceId sin configurar**. Es el problema #5 del MVP pasando desapercibido.

    Los comentarios de las variables vacías van en la línea de ARRIBA.
    """
    ejemplo = Path(__file__).resolve().parents[2] / ".env.example"
    culpables = [
        linea
        for linea in ejemplo.read_text(encoding="utf-8").splitlines()
        if re.fullmatch(r"[A-Z_][A-Z0-9_]*=\s*#.*", linea)
    ]
    assert not culpables, "estas variables quedan con el comentario como valor: " + "; ".join(
        culpables
    )
