"""`RESOLVER`: leer números reales de chats agendados por nombre.

Contra la página simulada, que es donde se fabrican los casos que importan: el
grupo, el chat que no abre, el número ilegible, el DOM que cambia a mitad de
la lista. Lo único que importa por sobre todo: **nunca escribe nada**.
"""

from __future__ import annotations

from agente.adaptadores.simulada import Chat, PaginaSimulada
from agente.jobs.resolver import resolver

CORRALON = Chat(nombre="Corralón San Justo", telefono="+54 9 11 2323-1151")
PINTURERIA = Chat(nombre="Pinturería Sur", telefono=None)
OBRA = Chat(nombre="Obra Centro", telefono=None, es_grupo=True)


def pagina(*chats: Chat, **opciones) -> PaginaSimulada:
    return PaginaSimulada({c.nombre: c for c in chats}, **opciones)


async def test_lee_el_numero_de_un_chat_agendado_por_nombre() -> None:
    resultado = await resolver(pagina(CORRALON), contactos=["Corralón San Justo"])

    assert resultado.ok
    assert resultado.detalle["contactos"] == [
        {"nombre": "Corralón San Justo", "telefono": "+54 9 11 2323-1151", "motivo": None}
    ]
    assert resultado.detalle["resueltos"] == 1


async def test_lo_que_no_se_puede_leer_vuelve_null_con_motivo() -> None:
    """`null` es la respuesta honesta: deducir un número acá es escribirle a
    otra persona después."""
    resultado = await resolver(
        pagina(CORRALON, PINTURERIA, OBRA),
        contactos=["Corralón San Justo", "Pinturería Sur", "Obra Centro", "No Existe"],
    )

    assert resultado.ok
    por_nombre = {c["nombre"]: c for c in resultado.detalle["contactos"]}
    assert por_nombre["Pinturería Sur"]["motivo"] == "numero_no_legible"
    assert por_nombre["Obra Centro"]["motivo"] == "es_grupo"
    assert por_nombre["No Existe"]["motivo"] == "chat_no_abre"
    assert all(
        c["telefono"] is None for c in resultado.detalle["contactos"] if c["motivo"] is not None
    )
    assert resultado.detalle["resueltos"] == 1
    assert resultado.detalle["sin_numero"] == 3


async def test_no_escribe_nada_jamas() -> None:
    """Es un job de sólo lectura, y esto es lo que lo verifica de verdad."""
    doble = pagina(CORRALON, OBRA)
    await resolver(doble, contactos=["Corralón San Justo", "Obra Centro"])

    assert doble.enviados == []
    assert not doble.escribio_algo


async def test_sin_sesion_reporta_sesion_caida() -> None:
    resultado = await resolver(pagina(CORRALON, sesion=False), contactos=["Corralón San Justo"])

    assert not resultado.ok
    assert resultado.codigo == "SESION_CAIDA"


async def test_el_dom_que_cambia_frena_pero_no_tira_lo_ya_leido() -> None:
    """Si WhatsApp cambió a mitad de la lista, lo leído hasta ahí es trabajo
    hecho y viaja igual; el código le dice al backend que frene."""
    doble = pagina(CORRALON, selector_roto=True)
    resultado = await resolver(doble, contactos=["Corralón San Justo"])

    assert not resultado.ok
    assert resultado.codigo == "SELECTOR_ROTO"
    assert "contactos" in resultado.detalle


async def test_sin_contactos_es_un_error_explicito() -> None:
    resultado = await resolver(pagina(), contactos=["   ", ""])

    assert not resultado.ok
    assert resultado.codigo == "ERROR_INESPERADO"


async def test_no_abre_una_fila_que_no_contiene_el_nombre_buscado() -> None:
    """⚠️ La regla A3: `RESOLVER` no tiene la comparación de identidad que
    protege a `ENVIAR`. Si ninguna fila contiene el nombre, la respuesta es
    `null` — no el número del primer chat de la lista, que quedaría guardado
    como el del contacto y podría hacer pasar la verificación de un envío
    posterior contra el chat de otra persona."""
    #  El buscador devuelve UN resultado, pero es otro chat: la clave con la
    #  que se encuentra no coincide con lo que la fila muestra.
    doble = PaginaSimulada(
        {"Corralón San Justo": Chat(nombre="Corralón Villegas", telefono="+54 9 11 9999-0000")}
    )

    resultado = await resolver(doble, contactos=["Corralón San Justo"])

    assert resultado.ok
    assert resultado.detalle["contactos"] == [
        {"nombre": "Corralón San Justo", "telefono": None, "motivo": "chat_no_abre"}
    ]
    assert doble.abierto is None, "no tiene que haber abierto ningún chat"
