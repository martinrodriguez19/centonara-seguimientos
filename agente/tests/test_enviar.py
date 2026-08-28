"""Tests del motor de envío.

Es el código más peligroso del proyecto, así que estos tests están escritos
desde la pregunta contraria a la habitual: **¿cómo hago para que le escriba a la
persona equivocada?**

Los casos adversos —dos contactos con el mismo nombre, un grupo, un chat
archivado, un número ilegible— son los que deciden si el sistema es seguro. Y en
cada aborto se verifica que **no quedó nada escrito**: que el log diga "aborté"
no alcanza.
"""

from __future__ import annotations

import pytest

from agente.adaptadores.pagina import ErrorDeSelector, Pagina
from agente.adaptadores.simulada import Chat, PaginaSimulada
from agente.jobs.enviar import Resultado, enviar

MARCELO = "+5491144405036"
OTRO = "+5491133445566"
TEXTO = "Hola Marcelo, quedamos en que te pasaba la disponibilidad. ¿Seguimos?"

TODOS = ["*"]


def pagina_con(chats: dict[str, Chat], **extra) -> PaginaSimulada:
    return PaginaSimulada(chats, **extra)


def chat_normal() -> dict[str, Chat]:
    return {MARCELO: Chat(nombre="Marcelo Fernández", telefono=MARCELO)}


async def mandar(pagina: PaginaSimulada, **extra) -> Resultado:
    opciones = {
        "contacto_id": MARCELO,
        "contacto_nombre": "Marcelo Fernández",
        "texto": TEXTO,
        "modo": "real",
        "destinos_permitidos": TODOS,
    }
    opciones.update(extra)
    return await enviar(pagina, **opciones)


# ---------------------------------------------------------------------------
# El camino que funciona
# ---------------------------------------------------------------------------


async def test_un_envio_normal_sale_y_se_confirma() -> None:
    pagina = pagina_con(chat_normal())
    resultado = await mandar(pagina)

    assert resultado.ok
    assert pagina.enviados == [(MARCELO, TEXTO)]


async def test_el_texto_sale_literal() -> None:
    """Byte a byte. Acentos, saltos de línea, signos: lo que aprobó una persona."""
    texto = "Hola Marcelo,\n\n¿Avanzamos con el pedido de chapa? Quedó pendiente.\n\nSaludos ñ"
    pagina = pagina_con(chat_normal())

    await mandar(pagina, texto=texto)

    assert pagina.enviados[0][1] == texto


# ---------------------------------------------------------------------------
# ⚠️ La verificación de identidad — el paso más importante del proyecto
# ---------------------------------------------------------------------------


async def test_si_el_numero_no_coincide_no_escribe_nada() -> None:
    """⚠️ El peor error posible del sistema, y lo único que lo impide.

    El chat que se abrió es de otra persona. Se aborta antes de tocar el campo
    de escritura.
    """
    pagina = pagina_con({MARCELO: Chat(nombre="Otro Contacto", telefono=OTRO)})

    resultado = await mandar(pagina)

    assert not resultado.ok
    assert resultado.codigo == "CONTACTO_NO_COINCIDE"
    assert pagina.enviados == []
    assert not pagina.escribio_algo, "el campo tiene que haber quedado vacío"


async def test_el_detalle_dice_a_quien_iba_y_a_quien_se_abrio() -> None:
    """Es lo primero que alguien va a querer saber cuando esto salte."""
    pagina = pagina_con({MARCELO: Chat(nombre="Otro Contacto", telefono=OTRO)})

    resultado = await mandar(pagina)

    assert resultado.detalle["esperado"] == MARCELO
    assert resultado.detalle["encontrado"] == OTRO
    assert resultado.detalle["header"] == "Otro Contacto"


async def test_los_espacios_no_deciden_si_un_mensaje_sale() -> None:
    """WhatsApp muestra "+54 9 11 4440-5036" y el backend manda E.164.

    Comparar los dígitos evita un falso negativo por un guion — y no afloja
    nada: dos teléfonos distintos siguen teniendo dígitos distintos.
    """
    pagina = pagina_con({MARCELO: Chat(nombre="Marcelo", telefono="+54 9 11 4440-5036")})

    assert (await mandar(pagina)).ok


async def test_un_numero_que_no_se_puede_leer_aborta() -> None:
    """El prompt pide null si no lo puede leer con certeza. Acá se respeta."""
    pagina = pagina_con({MARCELO: Chat(nombre="Marcelo", telefono=None)})

    resultado = await mandar(pagina)

    assert resultado.codigo == "NUMERO_NO_RESOLUBLE"
    assert not pagina.escribio_algo


async def test_un_header_ilegible_aborta() -> None:
    """Pasa con chats archivados y con la interfaz a medio cargar.

    "No sé qué dice" no es lo mismo que "dice lo que esperaba".
    """
    pagina = pagina_con({MARCELO: Chat(nombre="Marcelo", telefono=MARCELO, header_ilegible=True)})

    resultado = await mandar(pagina)

    assert resultado.codigo == "NUMERO_NO_RESOLUBLE"
    assert not pagina.escribio_algo


async def test_un_grupo_nunca_recibe_un_seguimiento() -> None:
    """El error que se evita acá es distinto: mandárselo a veinte a la vez."""
    pagina = pagina_con({MARCELO: Chat(nombre="Obra Belgrano", telefono=None, es_grupo=True)})

    resultado = await mandar(pagina)

    assert resultado.codigo == "CONTACTO_NO_COINCIDE"
    assert "grupo" in resultado.detalle["motivo"]
    assert pagina.enviados == []


async def test_un_contacto_sin_chat_no_inventa_uno() -> None:
    pagina = pagina_con({})

    resultado = await mandar(pagina)

    assert resultado.codigo == "CHAT_NO_ABRE"
    assert pagina.enviados == []


async def test_dos_contactos_con_el_mismo_nombre_no_confunden_al_sistema() -> None:
    """⚠️ El caso que un humano confundiría y el código no.

    Dos "Ferretería Sur" con teléfonos distintos. La búsqueda abre uno; la
    comparación es contra el NÚMERO, así que si abrió el otro, aborta.
    """
    pagina = pagina_con(
        {
            MARCELO: Chat(nombre="Ferretería Sur", telefono=MARCELO),
            OTRO: Chat(nombre="Ferretería Sur", telefono=OTRO),
        }
    )

    assert (await mandar(pagina, contacto_id=MARCELO)).ok
    assert pagina.enviados == [(MARCELO, TEXTO)]

    # Y si la búsqueda hubiera abierto el equivocado, no sale nada.
    pagina_confundida = pagina_con({MARCELO: Chat(nombre="Ferretería Sur", telefono=OTRO)})
    assert (await mandar(pagina_confundida)).codigo == "CONTACTO_NO_COINCIDE"
    assert pagina_confundida.enviados == []


# ---------------------------------------------------------------------------
# R4 — la lista de destinos permitidos
# ---------------------------------------------------------------------------


async def test_sin_lista_no_le_escribe_a_nadie() -> None:
    """El estado seguro es el que se obtiene sin configurar nada."""
    pagina = pagina_con(chat_normal())

    resultado = await mandar(pagina, destinos_permitidos=None)

    assert resultado.codigo == "DESTINO_NO_PERMITIDO"
    assert pagina.enviados == []


async def test_un_numero_fuera_de_la_lista_no_recibe_nada() -> None:
    pagina = pagina_con(chat_normal())

    resultado = await mandar(pagina, destinos_permitidos=[OTRO])

    assert resultado.codigo == "DESTINO_NO_PERMITIDO"
    assert pagina.enviados == []


async def test_la_lista_se_verifica_antes_de_abrir_el_navegador() -> None:
    """No hace falta ni mirar la pantalla para saber que no corresponde."""
    pagina = pagina_con(chat_normal(), sesion=False)

    # Con la sesión caída, si llegara al paso 1 devolvería SESION_CAIDA.
    resultado = await mandar(pagina, destinos_permitidos=[])

    assert resultado.codigo == "DESTINO_NO_PERMITIDO"


async def test_un_numero_de_la_lista_si_recibe() -> None:
    pagina = pagina_con(chat_normal())
    assert (await mandar(pagina, destinos_permitidos=[MARCELO])).ok


# ---------------------------------------------------------------------------
# El campo de escritura
# ---------------------------------------------------------------------------


async def test_si_el_vendedor_estaba_escribiendo_no_se_le_pisa() -> None:
    """Alguien está usando ese chat en este momento."""
    pagina = pagina_con(
        {
            MARCELO: Chat(
                nombre="Marcelo",
                telefono=MARCELO,
                borrador_del_vendedor="che, te decía que",
            )
        }
    )

    resultado = await mandar(pagina)

    assert resultado.codigo == "CAMPO_NO_VACIO"
    assert pagina.enviados == []
    assert pagina.campo == "che, te decía que", "no se tocó lo que estaba escrito"


# ---------------------------------------------------------------------------
# Modo prueba: dejar borradores (D30)
# ---------------------------------------------------------------------------


async def test_en_modo_prueba_hace_todo_menos_enviar() -> None:
    pagina = pagina_con(chat_normal())

    resultado = await mandar(pagina, modo="prueba")

    assert resultado.ok
    assert resultado.borrador
    assert resultado.texto_escrito == TEXTO
    assert pagina.enviados == [], "no salió nada"


async def test_el_modo_prueba_deja_el_texto_como_borrador_del_chat() -> None:
    """D30: el texto queda como borrador de WhatsApp, no se borra.

    El vendedor lo ve en su lista de chats y lo manda con un click. El chat
    queda cerrado — es lo que hace que WhatsApp persista el borrador.
    """
    chats = chat_normal()
    pagina = pagina_con(chats)

    await mandar(pagina, modo="prueba")

    assert pagina.abierto is None, "el chat quedó cerrado"
    unico = next(iter(chats.values()))
    assert unico.borrador_del_vendedor == TEXTO, "el texto quedó como borrador"


async def test_el_reporte_del_borrador_lo_dice() -> None:
    """⚠️ Sin el flag, el backend marcaría el borrador como ENVIADO: lo
    contaría en el tope diario y no se podría enviar de verdad nunca."""
    pagina = pagina_con(chat_normal())

    resultado = await mandar(pagina, modo="prueba")

    assert resultado.a_reporte()["borrador"] is True

    resultado_real = await mandar(pagina_con(chat_normal()), modo="real")
    assert resultado_real.a_reporte()["borrador"] is False


@pytest.mark.parametrize("modo", ["prueba", "simulado", "", "REAL", "Real"])
async def test_cualquier_cosa_que_no_sea_real_exactamente_no_envia(modo: str) -> None:
    """⚠️ Para que algo salga de verdad hay que decirlo exactamente.

    Un typo en la configuración no puede ser la diferencia entre simular y
    mandarle a un cliente.
    """
    pagina = pagina_con(chat_normal())

    await mandar(pagina, modo=modo)

    assert pagina.enviados == []


# ---------------------------------------------------------------------------
# ⚠️ El orden del paso 1: navegar primero, preguntar por la sesión después
# ---------------------------------------------------------------------------
#
# La causa principal de la corrida fallida del 27/08: la página del navegador
# dedicado nace sin navegar (about:blank), y ahí no hay ni QR ni lista de
# chats. Preguntar por la sesión antes de abrir devolvía SESION_CAIDA con la
# sesión perfectamente sana — y como se abortaba sin navegar, los tres
# reintentos morían igual.


async def test_navega_antes_de_preguntar_por_la_sesion() -> None:
    pagina = pagina_con(chat_normal())
    assert not pagina.navegada
    assert not await pagina.sesion_iniciada(), "sin navegar, la sesión no se ve"

    resultado = await mandar(pagina)

    assert resultado.ok, "con la sesión sana el envío tiene que salir"
    assert pagina.navegada, "el motor navegó antes de decidir"


async def test_el_qr_a_la_vista_es_sesion_caida() -> None:
    """La sesión caída de verdad se reporta DESPUÉS de navegar, no antes."""
    pagina = pagina_con(chat_normal(), sesion=False)

    resultado = await mandar(pagina)

    assert resultado.codigo == "SESION_CAIDA"
    assert pagina.navegada, "se navegó antes de declarar la sesión caída"
    assert pagina.enviados == []


async def test_una_pagina_que_no_carga_es_timeout_y_no_frena_la_corrida() -> None:
    """Red lenta o Chrome recién abierto: transitorio. TIMEOUT reintenta;
    SELECTOR_ROTO habría frenado la corrida entera por una demora."""
    pagina = pagina_con(chat_normal(), carga=False)

    resultado = await mandar(pagina)

    assert resultado.codigo == "TIMEOUT"
    assert resultado.codigo != "SELECTOR_ROTO"
    assert pagina.enviados == []


# ---------------------------------------------------------------------------
# La búsqueda del chat es por nombre (D34)
# ---------------------------------------------------------------------------


async def test_el_chat_se_busca_por_nombre() -> None:
    """Los contactos reales están agendados por nombre: buscar el E.164 no
    encuentra nada. La identidad la sigue decidiendo el número (paso 6)."""
    pagina = pagina_con({"Marcelo Fernández": Chat(nombre="Marcelo Fernández", telefono=MARCELO)})

    resultado = await mandar(pagina)

    assert resultado.ok
    assert pagina.enviados == [(MARCELO, TEXTO)]


async def test_si_el_nombre_no_trae_nada_se_prueba_con_el_numero() -> None:
    """Un chat renombrado o con emojis: el número queda de red de seguridad."""
    pagina = pagina_con(chat_normal())  # las claves son números

    assert (await mandar(pagina)).ok


async def test_sin_nombre_se_busca_directo_por_numero() -> None:
    pagina = pagina_con(chat_normal())

    assert (await mandar(pagina, contacto_nombre="")).ok


async def test_un_homonimo_abierto_por_nombre_no_recibe_nada() -> None:
    """⚠️ Buscar por nombre hace más probable abrir el chat de un homónimo.

    No afloja nada: la comparación por número (R1) lo aborta igual.
    """
    pagina = pagina_con({"Ferretería Sur": Chat(nombre="Ferretería Sur", telefono=OTRO)})

    resultado = await mandar(pagina, contacto_id=MARCELO, contacto_nombre="Ferretería Sur")

    assert resultado.codigo == "CONTACTO_NO_COINCIDE"
    assert pagina.enviados == []
    assert not pagina.escribio_algo


async def test_el_chat_no_abre_dice_que_se_busco() -> None:
    pagina = pagina_con({})

    resultado = await mandar(pagina)

    assert resultado.codigo == "CHAT_NO_ABRE"
    assert resultado.detalle["buscado"] == "Marcelo Fernández"
    assert resultado.detalle["motivo"] == "sin_resultados"


# ---------------------------------------------------------------------------
# Cuando la página se rompe
# ---------------------------------------------------------------------------


async def test_un_selector_roto_frena_y_lo_dice() -> None:
    """No es este envío el que falló: van a fallar todos."""
    pagina = pagina_con(chat_normal(), selector_roto=True)

    resultado = await mandar(pagina)

    assert resultado.codigo == "SELECTOR_ROTO"
    assert pagina.enviados == []


async def test_la_sesion_caida_se_distingue_de_todo_lo_demas() -> None:
    """Es transitorio: el vendedor escanea el QR y sigue. Por eso se reintenta."""
    pagina = pagina_con(chat_normal(), sesion=False)

    assert (await mandar(pagina)).codigo == "SESION_CAIDA"


async def test_un_error_inesperado_no_deja_el_envio_a_medias() -> None:
    """Nada se traga en silencio y nada sigue de largo."""

    class PaginaQueRevienta(PaginaSimulada):
        async def resolver_numero(self) -> str | None:
            raise RuntimeError("Chrome se cerró")

    pagina = PaginaQueRevienta(chat_normal())
    resultado = await mandar(pagina)

    assert resultado.codigo == "ERROR_INESPERADO"
    assert "Chrome se cerró" in resultado.detalle["mensaje"]
    assert pagina.enviados == []


async def test_sin_confirmacion_no_se_da_por_enviado() -> None:
    """⚠️ "Apreté enviar" y "el mensaje salió" no son lo mismo.

    `SIN_CONFIRMAR` no significa que no salió: significa que no sabemos. Por eso
    no se reintenta —mandarlo dos veces sería peor— y por eso alerta.
    """
    pagina = pagina_con(chat_normal(), confirma=False)

    resultado = await mandar(pagina)

    assert not resultado.ok
    assert resultado.codigo == "SIN_CONFIRMAR"
    assert "puede haber salido" in resultado.detalle["advertencia"]
    assert pagina.enviados == [(MARCELO, TEXTO)], "el mensaje sí se mandó"


# ---------------------------------------------------------------------------
# La forma del resultado
# ---------------------------------------------------------------------------


def test_el_resultado_se_convierte_en_lo_que_espera_el_backend() -> None:
    reporte = Resultado(False, "CONTACTO_NO_COINCIDE", {"esperado": MARCELO}).a_reporte()

    assert reporte["ok"] is False
    assert reporte["codigo"] == "CONTACTO_NO_COINCIDE"
    assert reporte["detalle"]["esperado"] == MARCELO


def test_la_pagina_simulada_cumple_el_protocolo() -> None:
    """Si el Protocol crece, esto avisa antes de que falle en producción."""
    assert isinstance(PaginaSimulada(), Pagina)


def test_el_error_de_selector_es_su_propio_tipo() -> None:
    """Se distingue de "no está": uno es un dato del mundo, el otro es que
    WhatsApp Web cambió y hay que frenar la corrida entera."""
    assert issubclass(ErrorDeSelector, Exception)
