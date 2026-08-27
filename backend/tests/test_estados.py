"""Tests de la máquina de estados.

Cobertura exigida: 100%.

El test que importa no es el del camino feliz — es el que **intenta cada
transición que no existe y verifica que falla**. Si la tabla se afloja por
descuido, esto es lo que lo detecta.
"""

import itertools

import pytest

from app.core.estados import (
    TERMINALES,
    TRANSICIONES,
    Estado,
    Motivo,
    MotivoRequerido,
    TransicionInvalida,
    es_terminal,
    puede,
    tomar_para_enviar,
    transicionar,
)

# Todos los pares posibles, y los que la tabla declara. La diferencia entre los
# dos conjuntos es lo que TIENE que fallar.
TODOS_LOS_PARES = set(itertools.product(Estado, Estado))
VALIDOS = {(desde, hasta) for desde, hastas in TRANSICIONES.items() for hasta in hastas}
INVALIDOS = TODOS_LOS_PARES - VALIDOS


def _motivo_para(hasta: Estado) -> Motivo | None:
    return Motivo.VETADO if hasta is Estado.DESCARTADO else None


# ---------------------------------------------------------------------------
# El camino feliz
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("desde", "hasta"), sorted(VALIDOS))
def test_las_transiciones_declaradas_funcionan(desde: Estado, hasta: Estado) -> None:
    assert transicionar(desde, hasta, _motivo_para(hasta)) is hasta


def test_el_ciclo_completo_de_un_mensaje_que_sale() -> None:
    estado = Estado.BORRADOR
    estado = transicionar(estado, Estado.EN_ESPERA)
    estado = tomar_para_enviar(estado)
    estado = transicionar(estado, Estado.ENVIADO)
    assert estado is Estado.ENVIADO
    assert es_terminal(estado)


def test_el_ciclo_de_un_borrador_que_se_deja_en_whatsapp() -> None:
    """D30: el modo borradores termina en BORRADOR_DEJADO, que es terminal.

    El sistema no vuelve a tocar ese chat: lo manda el vendedor, o nadie.
    """
    estado = Estado.BORRADOR
    estado = transicionar(estado, Estado.EN_ESPERA)
    estado = tomar_para_enviar(estado)
    estado = transicionar(estado, Estado.BORRADOR_DEJADO)
    assert es_terminal(estado)


def test_el_ciclo_de_un_retenido_que_alguien_libera() -> None:
    estado = Estado.BORRADOR
    estado = transicionar(estado, Estado.RETENIDO)
    estado = transicionar(estado, Estado.EN_ESPERA)
    assert tomar_para_enviar(estado) is Estado.ENVIANDO


def test_un_envio_que_falla_y_se_reintenta_vuelve_a_la_cola() -> None:
    """ENVIANDO → EN_ESPERA es cómo se reintenta sin perder el mensaje."""
    estado = tomar_para_enviar(Estado.EN_ESPERA)
    estado = transicionar(estado, Estado.EN_ESPERA)
    assert tomar_para_enviar(estado) is Estado.ENVIANDO


# ---------------------------------------------------------------------------
# Lo que tiene que fallar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("desde", "hasta"), sorted(INVALIDOS))
def test_toda_transicion_no_declarada_falla(desde: Estado, hasta: Estado) -> None:
    """Uno por cada par que la tabla no declara. Son treinta y pico."""
    assert not puede(desde, hasta)
    with pytest.raises(TransicionInvalida):
        transicionar(desde, hasta, _motivo_para(hasta))


@pytest.mark.parametrize("estado", sorted(TERMINALES))
def test_de_un_estado_terminal_no_se_sale(estado: Estado) -> None:
    assert es_terminal(estado)
    assert TRANSICIONES[estado] == frozenset()
    for destino in Estado:
        with pytest.raises(TransicionInvalida):
            transicionar(estado, destino, _motivo_para(destino))


def test_un_descartado_no_resucita() -> None:
    """Si hay que mandar ese mensaje, se genera uno nuevo. No hay `revivir()`."""
    with pytest.raises(TransicionInvalida):
        transicionar(Estado.DESCARTADO, Estado.EN_ESPERA)


def test_un_enviado_no_vuelve() -> None:
    with pytest.raises(TransicionInvalida):
        transicionar(Estado.ENVIADO, Estado.ENVIANDO)


# ---------------------------------------------------------------------------
# Sólo EN_ESPERA puede pasar a ENVIANDO — la regla más importante de la tabla
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("desde", [e for e in Estado if e is not Estado.EN_ESPERA])
def test_solo_en_espera_puede_pasar_a_enviando(desde: Estado) -> None:
    """A partir de ENVIANDO el agente le escribe a una persona real.

    Ningún otro estado tiene ese derecho: ni BORRADOR (no pasó las reglas), ni
    RETENIDO (nadie lo liberó), ni los terminales.
    """
    with pytest.raises(TransicionInvalida):
        tomar_para_enviar(desde)


def test_transicionar_directo_a_enviando_desde_en_espera_sigue_siendo_valido() -> None:
    """`tomar_para_enviar` es una fachada, no una segunda tabla de reglas.

    Si algún día divergen, esto lo detecta.
    """
    assert transicionar(Estado.EN_ESPERA, Estado.ENVIANDO) is Estado.ENVIANDO


# ---------------------------------------------------------------------------
# El motivo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "desde", sorted(hasta for hasta, d in TRANSICIONES.items() if Estado.DESCARTADO in d)
)
def test_descartar_sin_motivo_falla(desde: Estado) -> None:
    """Un DESCARTADO sin motivo es un mensaje que nadie puede explicar después."""
    with pytest.raises(MotivoRequerido):
        transicionar(desde, Estado.DESCARTADO)


@pytest.mark.parametrize("motivo", sorted(Motivo))
def test_todos_los_motivos_sirven_para_descartar(motivo: Motivo) -> None:
    assert transicionar(Estado.EN_ESPERA, Estado.DESCARTADO, motivo) is Estado.DESCARTADO


def test_un_motivo_en_una_transicion_que_no_descarta_falla() -> None:
    """Evita el `motivo` copiado y pegado que después nadie entiende."""
    with pytest.raises(TransicionInvalida):
        transicionar(Estado.BORRADOR, Estado.EN_ESPERA, Motivo.VETADO)


# ---------------------------------------------------------------------------
# La tabla misma
# ---------------------------------------------------------------------------


def test_la_tabla_cubre_todos_los_estados() -> None:
    """Un estado nuevo sin fila en la tabla reventaría con KeyError en runtime."""
    assert set(TRANSICIONES) == set(Estado)


def test_ningun_destino_de_la_tabla_es_un_estado_inventado() -> None:
    for hastas in TRANSICIONES.values():
        assert hastas <= set(Estado)


def test_los_estados_se_guardan_legibles_en_la_base() -> None:
    """`StrEnum`: en Mongo queda "EN_ESPERA", no un entero que hay que traducir."""
    assert Estado.EN_ESPERA == "EN_ESPERA"
    assert Motivo.VETADO == "vetado"
