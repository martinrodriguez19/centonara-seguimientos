"""Las señales de redacción del pase único (D40): informativas, medibles, puras.

Lo que se custodia acá no es que el modelo escriba bien —eso no se puede
testear sin modelo— sino que **los chequeos sigan atrapando lo que ya
atrapaban** cuando alguien vuelva a tocar el prompt en tres meses. Es el golden
set: borradores fijos, buenos y malos, y lo que cada uno tiene que encender.
"""

from __future__ import annotations

import pytest

from app.core import configuracion, redaccion
from app.core.redaccion import Senal

CONFIG = {
    "palabras_conflicto": list(configuracion.POR_DEFECTO["palabras_conflicto"]),
    "frases_prohibidas": list(configuracion.POR_DEFECTO["frases_prohibidas"]),
}


def senales(texto: str, **cambios) -> list[str]:
    argumentos = {
        "texto": texto,
        "resumen": "preguntó por hierro del 8",
        "tema": None,
        "cita": None,
        "motivo": None,
        "config": CONFIG,
    }
    argumentos.update(cambios)
    return [str(h.senal) for h in redaccion.revisar(**argumentos)]


# ---------------------------------------------------------------------------
# El golden set: lo que está bien no enciende nada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Hola Marcelo, te escribo por las chapas que estabas viendo. Seguis con eso?",
        "Hola, quedamos en que te pasaba la cotizacion del porton. La necesitas todavia?",
        "Hola Ana, como va? Te escribo para ver si podemos retomar lo que estabamos hablando.",
        "Hola, vi que al final lo compraste. Te falto algo o quedo todo bien?",
        # Una sigla corta del rubro no es mayúscula sostenida.
        "Hola, el caño de PVC que preguntaste ya llegó. ¿Lo pasás a buscar?",
    ],
)
def test_un_borrador_bien_escrito_no_enciende_nada(texto: str) -> None:
    assert senales(texto) == []


# ---------------------------------------------------------------------------
# Los signos, contados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("Hola!! Como andas?", "exclamación"),
        ("¡Hola Marcelo! Cómo va", "exclamación"),
        ("Hola? Como andas? Seguis con eso?", "más de una pregunta"),
        ("Hola Juan... te escribo por las chapas", "puntos suspensivos"),
        ("Hola Juan… te escribo por las chapas", "puntos suspensivos"),
        ("Hola Juan 😊 te escribo por las chapas", "emojis"),
        ("Hola, URGENTE lo de las chapas", "mayúscula sostenida"),
    ],
)
def test_los_signos_de_mas_se_cuentan(texto: str, motivo: str) -> None:
    hallazgos = redaccion.revisar(
        texto=texto, resumen="", tema=None, cita=None, motivo=None, config=CONFIG
    )
    assert [h.senal for h in hallazgos] == [Senal.EXCESO_DE_SIGNOS]
    assert motivo in hallazgos[0].detalle


def test_una_sola_pregunta_con_apertura_y_cierre_esta_bien() -> None:
    assert redaccion.exceso_de_signos("Hola, ¿seguís necesitando las chapas?") is None


# ---------------------------------------------------------------------------
# El tono
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Estimado, sigue en pie esa necesidad?",
        "Hola, quedo a disposición por cualquier consulta.",
        "Buenas, me comunico con usted por el pedido.",
    ],
)
def test_una_frase_de_oficina_enciende_tono_formal(texto: str) -> None:
    assert Senal.TONO_FORMAL in senales(texto)


def test_la_frase_se_encuentra_sin_acentos_y_por_subcadena() -> None:
    """Igual que `palabras_conflicto`: el dueño no va a escribir todas las formas."""
    assert Senal.TONO_FORMAL in senales("Quedo a disposicion para lo que necesites.")


def test_sin_frases_configuradas_el_tono_no_se_mide() -> None:
    assert senales("Estimado, sigue en pie?", config={"frases_prohibidas": []}) == []


# ---------------------------------------------------------------------------
# El anclaje y el conflicto
# ---------------------------------------------------------------------------


def test_un_tema_sin_cita_es_sin_anclaje() -> None:
    assert senales("Hola, seguís con lo de las chapas?", tema="chapas", cita=None) == [
        str(Senal.SIN_ANCLAJE)
    ]


def test_un_tema_con_cita_esta_anclado() -> None:
    assert (
        senales("Hola, seguís con lo de las chapas?", tema="chapas", cita="me pasas precio chapa")
        == []
    )


def test_el_nivel_b_no_es_sin_anclaje() -> None:
    """Sin tema no hay nada que anclar: es la respuesta correcta, no una falla."""
    assert senales("Hola Ana, como va?", tema=None, cita=None) == []


def test_escribirle_a_un_chat_con_reclamo_es_lo_primero_que_se_marca() -> None:
    encendidas = senales(
        "Estimado, sigue en pie esa necesidad!", resumen="tiene un reclamo por la entrega"
    )
    assert encendidas[0] == str(Senal.CHAT_DISCONFORME)
    assert set(encendidas) == {
        str(Senal.CHAT_DISCONFORME),
        str(Senal.TONO_FORMAL),
        str(Senal.EXCESO_DE_SIGNOS),
    }


def test_un_post_venta_no_es_disconforme_por_hablar_de_la_compra() -> None:
    """`palabras_conflicto` trae "factura": un post-venta la menciona seguido."""
    assert (
        senales(
            "Hola, vi que ya lo compraste. Te falto algo?",
            resumen="ya compró y pidió la factura",
            motivo="ya_compro",
        )
        == []
    )
