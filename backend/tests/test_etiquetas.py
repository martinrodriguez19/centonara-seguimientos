"""Las etiquetas del nombre del contacto (D50).

Lo que se custodia: que la detección falle **hacia no detectar**. Un
colocador sin etiqueta recibe el mensaje de siempre; un apodo tomado por
etiqueta le cambia el enfoque a alguien, y un `XX` no detectado le escribe a
la familia del vendedor.
"""

from __future__ import annotations

import pytest

from app.core import configuracion, etiquetas

CONFIG = {"etiquetas_contacto": configuracion.POR_DEFECTO["etiquetas_contacto"]}


@pytest.mark.parametrize(
    ("nombre", "esperada"),
    [
        ("Juan Pérez ARQ", "ARQ"),
        ("Juan Pérez - PAISA", "PAISA"),
        ("Corralón Sur (DIST)", "DIST"),
        ("Corralón Sur [DIST]", "DIST"),
        ("Marta Lopez/PILE", "PILE"),
        ("Ana CF", "CF"),
        ("Pedro COLO", "COLO"),
        ("Mamá XX", "XX"),
        ("Tío Pedro COLO XX", "XX"),
        ("Tío Pedro XX COLO", "XX"),
        ("Juan Pérez ARQ  ", "ARQ"),
    ],
)
def test_la_ultima_palabra_en_mayusculas_es_la_etiqueta(nombre: str, esperada: str) -> None:
    detectada = etiquetas.detectar(nombre, CONFIG)
    assert detectada is not None
    assert detectada.etiqueta == esperada


@pytest.mark.parametrize(
    "nombre",
    [
        "Juan Pérez",
        "Juan el Colo",  # apodo, no etiqueta
        "Colo Gómez",  # al principio no cuenta
        "ARQ Juan Pérez",  # al principio no cuenta
        "JUAN COLO",  # todo en mayúsculas: ambiguo
        "COLO",  # sin nombre delante
        "XX",
        "Juan Pérez Arq",  # en minúsculas no es etiqueta
        "Juan Pérez ARQU",  # una palabra que no está en la tabla
        "",
    ],
)
def test_ante_la_duda_no_hay_etiqueta(nombre: str) -> None:
    assert etiquetas.detectar(nombre, CONFIG) is None


def test_xx_no_se_contacta_y_las_demas_si() -> None:
    assert etiquetas.detectar("Mamá XX", CONFIG).no_contactar
    assert not etiquetas.detectar("Juan ARQ", CONFIG).no_contactar


def test_una_etiqueta_que_el_dueno_marco_como_no_contactar_manda() -> None:
    config = {
        "etiquetas_contacto": [
            {"etiqueta": "PROV", "significado": "Proveedor", "contactar": False},
            {"etiqueta": "ARQ", "contactar": True},
        ]
    }
    assert etiquetas.detectar("Hierros Sur PROV", config).no_contactar
    assert etiquetas.detectar("Hierros Sur ARQ PROV", config).etiqueta == "PROV"
    assert etiquetas.detectar("Hierros Sur PROV ARQ", config).etiqueta == "PROV"


def test_sin_tabla_no_se_detecta_nada() -> None:
    assert etiquetas.detectar("Mamá XX", {}) is None
    assert etiquetas.detectar("Mamá XX", {"etiquetas_contacto": []}) is None


def test_la_tabla_ignora_lo_raro() -> None:
    config = {
        "etiquetas_contacto": [
            {"etiqueta": "arq", "significado": "se normaliza", "enfoque": "  dos\n líneas "},
            {"etiqueta": "no vale", "significado": "con espacio"},
            {"etiqueta": "ÑU"},
            "basura",
            {"etiqueta": ""},
        ]
    }
    tabla = etiquetas.conocidas(config)
    assert list(tabla) == ["ARQ"]
    assert tabla["ARQ"].enfoque == "dos líneas"


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Juan Pérez ARQ", "Juan Pérez"),
        ("Tío Pedro COLO XX", "Tío Pedro"),
        ("Corralón Sur (DIST)", "Corralón Sur"),
        ("Juan Pérez", "Juan Pérez"),
        ("JUAN COLO", "JUAN COLO"),
    ],
)
def test_el_nombre_sin_etiqueta_es_como_se_saluda(nombre: str, esperado: str) -> None:
    assert etiquetas.nombre_sin_etiqueta(nombre, CONFIG) == esperado


def test_para_el_payload_viaja_lo_que_el_esquema_acepta() -> None:
    from app.modelos.jobs import EtiquetaContacto

    for cruda in etiquetas.para_el_payload(CONFIG):
        EtiquetaContacto.model_validate(cruda)
    assert [e["etiqueta"] for e in etiquetas.para_el_payload(CONFIG)][-1] == "XX"
