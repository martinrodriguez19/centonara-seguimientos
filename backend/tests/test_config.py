"""Configuración: lo que se lee del entorno y lo que se rechaza."""

import pytest
from pydantic import ValidationError

from app.config import Configuracion


def test_lee_las_variables_del_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTORNO", "staging")
    monkeypatch.setenv("MONGO_URL", "mongodb://mongo-de-prueba:27017")
    monkeypatch.setenv("MONGO_DB", "otra")

    config = Configuracion(_env_file=None)

    assert config.entorno == "staging"
    assert config.mongo_url == "mongodb://mongo-de-prueba:27017"
    assert config.mongo_db == "otra"


def test_un_entorno_inventado_no_arranca() -> None:
    """`ENTORNO=produccion` es la que habilita el envío real (05 §6). Un typo no
    puede quedar en un valor intermedio: revienta al arrancar."""
    with pytest.raises(ValidationError):
        Configuracion(_env_file=None, entorno="produccón")


def test_por_defecto_el_entorno_es_local() -> None:
    """El default más conservador: la máquina de cualquiera es local."""
    assert Configuracion(_env_file=None).entorno == "local"


def test_los_logs_van_en_json_fuera_de_local() -> None:
    assert Configuracion(_env_file=None, entorno="local").logs_en_json is False
    assert Configuracion(_env_file=None, entorno="staging").logs_en_json is True
    assert Configuracion(_env_file=None, entorno="produccion").logs_en_json is True
    # El override manual gana sobre la heurística.
    assert Configuracion(_env_file=None, entorno="local", log_json=True).logs_en_json is True
