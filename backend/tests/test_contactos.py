"""Tests de la normalización a E.164.

Cobertura exigida: 100%. Es lo que decide si dos anotaciones distintas del mismo
teléfono son el mismo contacto — y de eso dependen el anti-duplicado y la
verificación de identidad antes de escribir.
"""

import pytest

from app.core.contactos import NumeroInvalido, normalizar, son_el_mismo

# Los cinco formatos del criterio de salida: todos son el mismo teléfono.
MISMO_NUMERO = [
    "11 4440-5036",
    "+54 11 4440 5036",
    "0111544405036",
    "+549 11 4440-5036",
    "1544405036",
    "+5491144405036",
    "5491144405036",
    "011 15-4440-5036",
    "(011) 4440-5036",
    "11-4440-5036",
]


@pytest.mark.parametrize("crudo", MISMO_NUMERO)
def test_todos_los_formatos_dan_el_mismo_e164(crudo: str) -> None:
    assert normalizar(crudo) == "+5491144405036"


def test_todos_los_formatos_son_el_mismo_contacto() -> None:
    """Lo que importa en la práctica: que el anti-duplicado los junte a todos."""
    normalizados = {normalizar(c) for c in MISMO_NUMERO}
    assert len(normalizados) == 1


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        # Área de 3 dígitos — Córdoba, Rosario, Mendoza, La Plata
        ("351 123-4567", "+5493511234567"),
        ("0351 15 123 4567", "+5493511234567"),
        ("+54 341 456-7890", "+5493414567890"),
        ("0221 15 444 5566", "+5492214445566"),
        ("+5492613334455", "+5492613334455"),
        # Área de 4 dígitos — Río Gallegos, Concepción del Uruguay
        ("2966 12-3456", "+5492966123456"),
        ("02966 15 123456", "+5492966123456"),
        ("3446 45-6789", "+5493446456789"),
        # Ya normalizado: idempotente
        ("+5493511234567", "+5493511234567"),
    ],
)
def test_areas_de_dos_tres_y_cuatro_digitos(crudo: str, esperado: str) -> None:
    assert normalizar(crudo) == esperado


def test_normalizar_es_idempotente() -> None:
    una_vez = normalizar("011 15-4440-5036")
    assert normalizar(una_vez) == una_vez


# ---------------------------------------------------------------------------
# Lo que tiene que fallar. Falla cerrado: ante la duda, no es un número.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("crudo", "motivo"),
    [
        (None, "vacio"),
        ("", "vacio"),
        ("   ", "vacio"),
        ("no es un teléfono", "vacio"),
        ("+34 600 123 456", "pais_no_soportado"),  # España
        ("+1 415 555 2671", "pais_no_soportado"),  # Estados Unidos
        ("+55 11 91234 5678", "pais_no_soportado"),  # Brasil
        ("11 4440", "largo_invalido"),  # corto
        ("11 4440 5036 999", "largo_invalido"),  # largo
        ("999 123-4567", "area_desconocida"),
        ("100 123-4567", "area_desconocida"),
    ],
)
def test_numeros_invalidos(crudo: str | None, motivo: str) -> None:
    with pytest.raises(NumeroInvalido) as error:
        normalizar(crudo)
    assert error.value.motivo == motivo


def test_el_error_lleva_el_valor_original_para_poder_depurarlo() -> None:
    """`raw` y contexto siempre presentes: es la regla R5 aplicada a un error."""
    with pytest.raises(NumeroInvalido) as error:
        normalizar("999 123-4567")
    assert "999" in error.value.detalle


def test_un_mas_de_argentina_no_es_pais_no_soportado() -> None:
    """`+54...` entra por el camino normal aunque tenga el `+`."""
    assert normalizar("+541144405036") == "+5491144405036"


# ---------------------------------------------------------------------------
# son_el_mismo — lo que usa la verificación de identidad antes de escribir
# ---------------------------------------------------------------------------


def test_son_el_mismo_reconoce_dos_anotaciones_del_mismo_telefono() -> None:
    assert son_el_mismo("011 15-4440-5036", "+5491144405036")


def test_son_el_mismo_distingue_dos_telefonos_distintos() -> None:
    assert not son_el_mismo("11 4440-5036", "11 4440-5037")


@pytest.mark.parametrize(
    ("uno", "otro"),
    [
        (None, "+5491144405036"),
        ("+5491144405036", None),
        ("", "+5491144405036"),
        ("cualquier cosa", "+5491144405036"),
        ("+34 600 123 456", "+5491144405036"),
    ],
)
def test_son_el_mismo_falla_cerrado_ante_lo_que_no_puede_normalizar(
    uno: str | None, otro: str | None
) -> None:
    """R2: ante cualquier duda, NO son el mismo. Nunca se escribe por las dudas.

    Es el caso que importa: si el agente no puede leer el número del chat
    abierto, la comparación tiene que dar False y abortar el envío — no
    lanzar una excepción que alguien podría atrapar mal más arriba.
    """
    assert not son_el_mismo(uno, otro)


def test_son_el_mismo_no_iguala_dos_numeros_ilegibles_entre_si() -> None:
    """Dos `None` no son "el mismo contacto": son dos incógnitas."""
    assert not son_el_mismo(None, None)
    assert not son_el_mismo("basura", "basura")
