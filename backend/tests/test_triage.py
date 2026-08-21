"""Tests del triage.

Dos cosas se prueban acá, y la segunda es tan importante como la primera:

1. Que cada señal se encienda cuando corresponde.
2. Que **no se encienda cuando no corresponde**. Un triage que retiene de más
   molesta, y un triage que molesta se termina apagando — y uno apagado es peor
   que no tenerlo, porque el equipo cree que está protegido.
"""

from __future__ import annotations

import pytest

from app.core import configuracion
from app.core.triage import (
    Hallazgo,
    Senal,
    busca_compromiso,
    contiene_alguna,
    evaluar,
    nombres_repetidos,
    proporcion_retenida,
)

CONFIG = configuracion.POR_DEFECTO


def evaluar_uno(**extra) -> list[Hallazgo]:
    """Un borrador que NO enciende ninguna señal, salvo lo que se cambie."""
    opciones = {
        "texto": "Hola Marcelo, quedamos en que te pasaba la disponibilidad. ¿Seguimos?",
        "resumen": "preguntó por precio de chapa galvanizada",
        "contacto_id": "+5491144405036",
        "contacto_nombre": "Ferretería Sur",
        "quien_hablo_ultimo": "contacto",
        "config": CONFIG,
    }
    opciones.update(extra)
    return evaluar(**opciones)


def senales(hallazgos: list[Hallazgo]) -> set[Senal]:
    return {h.senal for h in hallazgos}


# ---------------------------------------------------------------------------
# El punto de partida
# ---------------------------------------------------------------------------


def test_un_borrador_normal_sale_sin_que_nadie_lo_mire() -> None:
    """Si esto falla, el resto de los tests mienten."""
    assert evaluar_uno() == []


# ---------------------------------------------------------------------------
# PALABRA_CONFLICTO — la más importante
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resumen",
    [
        "puso un reclamo por la última entrega",
        "dice que tuvo un problema con el material",
        "quiere cancelar el pedido",
        "consultó por la garantía",
        "mandó el material defectuoso de vuelta",
        "habló de meter un abogado",
    ],
)
def test_un_reclamo_abierto_se_aparta(resumen: str) -> None:
    """Un seguimiento comercial sobre un reclamo es el peor error del sistema."""
    assert Senal.PALABRA_CONFLICTO in senales(evaluar_uno(resumen=resumen))


def test_la_palabra_se_encuentra_aunque_este_conjugada() -> None:
    """El cliente carga "reclamo"; el resumen puede decir "reclamos" o "reclamó"."""
    assert contiene_alguna("hizo dos reclamos", ["reclamo"]) == "reclamo"
    assert contiene_alguna("reclamó por teléfono", ["reclamo"]) == "reclamo"


def test_los_acentos_no_deciden_si_algo_se_aparta() -> None:
    """El cliente escribe "devolución" en el panel y el resumen dice "devolucion"."""
    assert contiene_alguna("pidió la devolucion", ["devolución"]) is not None
    assert contiene_alguna("pidió la devolución", ["devolucion"]) is not None


def test_sin_palabras_configuradas_la_senal_no_se_enciende() -> None:
    config = {**CONFIG, "palabras_conflicto": []}
    assert Senal.PALABRA_CONFLICTO not in senales(
        evaluar_uno(resumen="puso un reclamo", config=config)
    )


def test_el_cliente_puede_agregar_palabras_de_su_rubro() -> None:
    config = {**CONFIG, "palabras_conflicto": ["roto en obra"]}
    assert Senal.PALABRA_CONFLICTO in senales(
        evaluar_uno(resumen="llegó roto en obra", config=config)
    )


# ---------------------------------------------------------------------------
# SIN_RESPUESTA_PREVIA
# ---------------------------------------------------------------------------


def test_insistir_sobre_silencio_se_aparta() -> None:
    """Es lo que dispara que a uno lo reporten, y lo reportado bloquea líneas."""
    hallazgos = evaluar_uno(ya_le_escribimos=True, quien_hablo_ultimo="vendedor")
    assert Senal.SIN_RESPUESTA_PREVIA in senales(hallazgos)


def test_si_contesto_no_es_insistir() -> None:
    """Le escribimos, respondió: la conversación siguió. Eso es lo normal."""
    hallazgos = evaluar_uno(ya_le_escribimos=True, quien_hablo_ultimo="contacto")
    assert Senal.SIN_RESPUESTA_PREVIA not in senales(hallazgos)


def test_la_primera_vez_no_es_insistir() -> None:
    """Que el último en hablar hayamos sido nosotros, sin haberle escrito antes,
    es una conversación normal que quedó de nuestro lado."""
    hallazgos = evaluar_uno(ya_le_escribimos=False, quien_hablo_ultimo="vendedor")
    assert Senal.SIN_RESPUESTA_PREVIA not in senales(hallazgos)


# ---------------------------------------------------------------------------
# IDENTIDAD_AMBIGUA
# ---------------------------------------------------------------------------


def test_sin_numero_no_sabemos_a_quien_le_escribimos() -> None:
    """El prompt pide poner null si no puede leerlo con certeza. Esto lo atrapa."""
    hallazgos = evaluar_uno(contacto_id="")
    assert Senal.IDENTIDAD_AMBIGUA in senales(hallazgos)
    assert "no se pudo leer" in hallazgos[0].detalle


def test_un_numero_que_no_resuelve_se_aparta() -> None:
    hallazgos = evaluar_uno(contacto_id="no es un numero")
    assert Senal.IDENTIDAD_AMBIGUA in senales(hallazgos)


def test_dos_contactos_con_el_mismo_nombre_se_apartan() -> None:
    """Dos "Ferretería Sur" con teléfonos distintos son dos negocios."""
    hallazgos = evaluar_uno(nombre_repetido=True)
    assert Senal.IDENTIDAD_AMBIGUA in senales(hallazgos)
    assert "Ferretería Sur" in hallazgos[0].detalle


def test_nombres_repetidos_encuentra_los_duplicados() -> None:
    chats = [
        {"contacto_nombre": "Ferretería Sur", "contacto_id": "+5491100000001"},
        {"contacto_nombre": "ferreteria sur", "contacto_id": "+5491100000002"},
        {"contacto_nombre": "Corralón Norte", "contacto_id": "+5491100000003"},
    ]
    assert nombres_repetidos(chats) == {"ferreteria sur"}, (
        "una tilde no puede decidir si se detecta el duplicado"
    )


def test_el_mismo_contacto_dos_veces_no_es_ambiguo() -> None:
    """Mismo nombre y mismo número: es una sola persona, no dos."""
    chats = [
        {"contacto_nombre": "Marcelo", "contacto_id": "+5491100000001"},
        {"contacto_nombre": "Marcelo", "contacto_id": "+5491100000001"},
    ]
    assert nombres_repetidos(chats) == set()


def test_un_chat_sin_nombre_no_rompe_la_deteccion() -> None:
    assert nombres_repetidos([{"contacto_nombre": "", "contacto_id": "+549"}]) == set()


# ---------------------------------------------------------------------------
# COMPROMISO_CONCRETO
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Te lo dejo en $1.500 el metro",
        "Son 25000 pesos con el envío",
        "Te hago un 15% de descuento",
        "Te lo mando USD 200",
        "Lo tenés el 15/9 sin falta",
        "Te lo llevo el lunes",
        "Mañana te confirmo y sale",
        "Lo tenés en 3 días",
        "Dentro de 2 semanas está en obra",
        "Te reservo 200 metros",
        "Quedan 5 chapas para vos",
    ],
)
def test_una_promesa_concreta_se_aparta(texto: str) -> None:
    """⚠️ Un dato inventado por el modelo se convierte en una promesa comercial.

    Nadie se lo va a reclamar al sistema: se lo van a reclamar al vendedor.
    """
    assert Senal.COMPROMISO_CONCRETO in senales(evaluar_uno(texto=texto))


@pytest.mark.parametrize(
    "texto",
    [
        "Hola Marcelo, ¿seguimos con lo que hablamos?",
        "Quedó pendiente que te pasara la info. ¿Te sirve que lo veamos?",
        "¿Llegaste a ver lo que te mandé?",
        "Te escribo para retomar. ¿Cómo venís con la obra?",
        "Contame si te sirve y lo vemos.",
    ],
)
def test_un_seguimiento_sin_promesas_pasa(texto: str) -> None:
    """La otra mitad: que no se aparte lo que es exactamente lo que queremos."""
    assert Senal.COMPROMISO_CONCRETO not in senales(evaluar_uno(texto=texto))


def test_el_detalle_dice_QUE_prometio() -> None:
    """Quien lo revisa tiene que ver el número sin releer todo el mensaje."""
    hallazgos = evaluar_uno(texto="Te lo dejo en $1.500")
    compromiso = next(h for h in hallazgos if h.senal is Senal.COMPROMISO_CONCRETO)
    assert "1.500" in compromiso.detalle


def test_busca_compromiso_devuelve_none_sin_promesas() -> None:
    assert busca_compromiso("Hola, ¿cómo va todo?") is None


# ---------------------------------------------------------------------------
# CHAT_NO_COMERCIAL — la que más puede retener de más
# ---------------------------------------------------------------------------


def test_un_chat_sin_senales_de_trabajo_se_aparta() -> None:
    """Las líneas mezclan lo personal con lo laboral."""
    hallazgos = evaluar_uno(resumen="le mandó fotos del asado del domingo")
    assert Senal.CHAT_NO_COMERCIAL in senales(hallazgos)


def test_un_chat_de_trabajo_no_se_aparta() -> None:
    assert Senal.CHAT_NO_COMERCIAL not in senales(
        evaluar_uno(resumen="pidió presupuesto por 200 metros de chapa")
    )


def test_vaciar_la_lista_apaga_la_senal() -> None:
    """⚠️ El interruptor de la señal más propensa a retener de más.

    Si al calibrar retiene demasiado, se vacía desde el panel: sin tocar código
    y sin desplegar.
    """
    config = {**CONFIG, "palabras_comerciales": []}
    hallazgos = evaluar_uno(resumen="cualquier cosa que no sea comercial", config=config)
    assert Senal.CHAT_NO_COMERCIAL not in senales(hallazgos)


# ---------------------------------------------------------------------------
# Cómo se combinan
# ---------------------------------------------------------------------------


def test_se_devuelven_todas_las_senales_no_la_primera() -> None:
    """Quien revisa quiere saber todo lo que llamó la atención."""
    hallazgos = evaluar_uno(
        resumen="puso un reclamo por la entrega",
        texto="Te lo dejo en $1.500 el lunes",
        contacto_id="",
    )
    assert {
        Senal.PALABRA_CONFLICTO,
        Senal.COMPROMISO_CONCRETO,
        Senal.IDENTIDAD_AMBIGUA,
    } <= senales(hallazgos)


def test_una_sola_senal_alcanza_para_apartar() -> None:
    """El triage no puntúa: cualquiera de las cinco manda a revisión."""
    assert len(evaluar_uno(contacto_id="")) >= 1


def test_un_hallazgo_se_lee_solo() -> None:
    """Va al panel: tiene que decir qué pasó sin abrir el código."""
    hallazgo = Hallazgo(Senal.PALABRA_CONFLICTO, "el chat menciona 'reclamo'")
    assert "PALABRA_CONFLICTO" in str(hallazgo)
    assert "reclamo" in str(hallazgo)


def test_son_cinco_senales_de_triage_y_una_de_redaccion() -> None:
    """Eran siete. Se sacaron dos: la antigüedad —que contradecía el criterio
    validado del MVP— y el largo, que ya cubre un guardrail.

    `SIN_CONTEXTO` se cuenta aparte porque no la enciende `evaluar()`: la trae el
    resultado de `REDACTAR` cuando el modelo se niega a inventar un seguimiento.
    Es una señal del mismo tipo —por qué se apartó un mensaje, y el panel la
    muestra igual— pero no sale de mirar el texto, porque no hay texto.
    """
    del_triage = set(Senal) - {Senal.SIN_CONTEXTO}
    assert len(del_triage) == 5
    assert len(Senal) == 6


# ---------------------------------------------------------------------------
# Calibración
# ---------------------------------------------------------------------------


def test_la_proporcion_retenida_se_puede_medir() -> None:
    """El objetivo es 10 a 20%, y la única forma de saberlo es medirlo."""
    tanda = [[], [], [Hallazgo(Senal.PALABRA_CONFLICTO, "x")], []]
    assert proporcion_retenida(tanda) == 0.25


def test_la_proporcion_de_una_tanda_vacia_es_cero() -> None:
    assert proporcion_retenida([]) == 0.0


def test_una_tanda_realista_retiene_dentro_del_objetivo() -> None:
    """⚠️ La prueba de calibración.

    Diez chats como los que produce una corrida real: ocho de rutina, uno con
    un reclamo y uno con una promesa. Si el triage retiene mucho más que eso,
    en producción va a molestar y alguien lo va a apagar.

    No reemplaza medirlo con datos reales, pero detecta que una señal nueva se
    volvió demasiado celosa.
    """
    tanda = [
        # Ocho de rutina
        ("preguntó por precio de chapa", "¿Seguimos con lo que hablamos?"),
        ("pidió presupuesto de hierro", "Te escribo para retomar. ¿Lo vemos?"),
        ("consultó stock de cemento", "¿Llegaste a ver lo que te pasé?"),
        ("preguntó por entrega de arena", "Contame si te sirve y avanzamos."),
        ("quería cotización de ladrillos", "¿Cómo venís con la obra?"),
        ("pidió precio de perfiles", "Quedó pendiente lo tuyo, ¿lo retomamos?"),
        ("consultó disponibilidad de caños", "¿Te sirve que lo veamos esta semana?"),
        ("preguntó por material para obra", "¿Avanzamos con lo que charlamos?"),
        # Uno con reclamo y uno con promesa
        ("puso un reclamo por la última entrega", "¿Seguimos con el pedido?"),
        ("pidió precio de chapa", "Te lo dejo en $1.200 el metro"),
    ]

    evaluaciones = [evaluar_uno(resumen=resumen, texto=texto) for resumen, texto in tanda]
    proporcion = proporcion_retenida(evaluaciones)

    assert 0.10 <= proporcion <= 0.30, (
        f"retuvo el {proporcion:.0%}; el objetivo es 10 a 20%. "
        f"Apartados: {[i for i, e in enumerate(evaluaciones) if e]}"
    )
