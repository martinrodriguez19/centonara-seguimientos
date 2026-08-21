"""Los tests de los ocho guardrails.

**Un test del camino feliz no prueba nada acá.** Cada guardrail tiene al menos
un test que *intenta violarlo* y verifica que falla. Si mañana alguien afloja un
`if` por comodidad, esto es lo que lo agarra.

Cobertura exigida de `core/guardrails.py`: 100%.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core import configuracion, guardrails, mensajes, vendedores
from app.core.esquema import inicializar
from app.core.guardrails import Guardrail, revisar_texto, revisar_ventana

# Un miércoles a las 11:00. Día hábil, dentro de la ventana.
MIERCOLES = datetime(2026, 8, 19, 11, 0, tzinfo=UTC)

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)


@pytest.fixture
async def base():
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    try:
        db = cliente[nombre]
        await inicializar(db)
        # Un destino permitido y una máquina lista: el punto de partida donde
        # NO hay violaciones, para que cada test rompa una sola cosa.
        await configuracion.actualizar(db, {"destinos_permitidos": ["+5491144405036"]})
        await vendedores.dar_de_alta(db, maquina="mac-rocio", nombre="Rocío")
        await db["vendedores"].update_one(
            {"maquina": "mac-rocio"},
            {"$set": {"activo": True, "acepto_condiciones_en": MIERCOLES}},
        )
        yield db
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


async def revisar(base, **extra):
    opciones = {
        "contacto_id": "+5491144405036",
        "texto": "Hola Marcelo, quedamos en pasarte el precio de la chapa. ¿Seguimos?",
        "maquina": "mac-rocio",
        "ahora": MIERCOLES,
    }
    opciones.update(extra)
    return await guardrails.revisar(base, **opciones)


def codigos(violaciones) -> set[Guardrail]:
    return {v.guardrail for v in violaciones}


# ---------------------------------------------------------------------------
# El punto de partida
# ---------------------------------------------------------------------------


@sin_mongo
async def test_un_mensaje_bien_formado_no_viola_nada(base) -> None:
    """Si esto falla, todos los demás tests mienten."""
    assert await revisar(base) == []


# ---------------------------------------------------------------------------
# G2 — Destino permitido. El que hace que todo sea seguro de construir.
# ---------------------------------------------------------------------------


@sin_mongo
async def test_g2_un_numero_fuera_de_la_lista_no_pasa(base) -> None:
    violaciones = await revisar(base, contacto_id="+5491133445566")
    assert Guardrail.DESTINO in codigos(violaciones)


@sin_mongo
async def test_g2_con_la_lista_vacia_no_pasa_nadie(base) -> None:
    """⚠️ El estado seguro es el que se obtiene sin hacer nada.

    Una lista vacía significa "a nadie", no "a todos". Un sistema recién
    desplegado que nadie configuró no le puede escribir a ningún cliente.
    """
    await configuracion.actualizar(base, {"destinos_permitidos": []})
    assert Guardrail.DESTINO in codigos(await revisar(base))


@sin_mongo
async def test_g2_con_la_lista_abierta_pasa_cualquiera(base) -> None:
    """Y esto es lo que hace que abrirla sea un acto deliberado y auditado."""
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    violaciones = await revisar(base, contacto_id="+5491199887766")
    assert Guardrail.DESTINO not in codigos(violaciones)


# ---------------------------------------------------------------------------
# G3 — Texto válido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Hola {nombre}, ¿seguimos?",
        "Hola {{nombre}}, ¿seguimos?",
        "Te paso el precio de [producto]",
        "El total es XXX pesos",
        "TODO: completar con el precio",
        "Precio: TBD",
    ],
)
def test_g3_un_placeholder_sin_resolver_no_pasa(texto: str) -> None:
    """⚠️ El más importante de G3 y el menos obvio.

    El texto se envía EXACTAMENTE como está: nadie lo completa después. Un
    "Hola {nombre}" que sale es peor que uno que no sale.
    """
    violacion = revisar_texto(texto, largo_maximo=600)
    assert violacion is not None
    assert violacion.guardrail is Guardrail.TEXTO
    assert "placeholder" in violacion.detalle


@pytest.mark.parametrize("texto", ["", "   ", "\n\t  \n"])
def test_g3_un_texto_vacio_no_pasa(texto: str) -> None:
    violacion = revisar_texto(texto, largo_maximo=600)
    assert violacion is not None
    assert "vacío" in violacion.detalle


def test_g3_un_texto_demasiado_largo_no_pasa() -> None:
    violacion = revisar_texto("a" * 601, largo_maximo=600)
    assert violacion is not None
    assert "601" in violacion.detalle


def test_g3_un_texto_normal_pasa() -> None:
    assert revisar_texto("Hola Marcelo, ¿avanzamos con el pedido?", largo_maximo=600) is None


def test_g3_un_texto_justo_en_el_limite_pasa() -> None:
    assert revisar_texto("a" * 600, largo_maximo=600) is None


def test_g3_las_llaves_de_un_emoji_o_una_cuenta_no_son_placeholders() -> None:
    """Que no sea tan celoso que rechace texto legítimo."""
    assert revisar_texto("Te debo $1.500 (mil quinientos)", largo_maximo=600) is None


@sin_mongo
async def test_g3_llega_hasta_la_revision_completa(base) -> None:
    assert Guardrail.TEXTO in codigos(await revisar(base, texto="Hola {nombre}"))


# ---------------------------------------------------------------------------
# G4 — Topes
# ---------------------------------------------------------------------------


@sin_mongo
async def test_g4_el_tope_diario_frena(base) -> None:
    """Es lo que protege la línea de trabajo del vendedor."""
    from bson import ObjectId

    corrida = ObjectId()
    await base["vendedores"].update_one({"maquina": "mac-rocio"}, {"$set": {"tope_diario": 2}})

    for n in range(2):
        mensaje_id = await mensajes.crear_borrador(
            base,
            corrida_id=corrida,
            maquina="mac-rocio",
            contacto_id=f"+54911000000{n}",
            contacto_nombre=f"Contacto {n}",
            texto=f"Mensaje {n}",
            ahora=MIERCOLES,
        )
        await mensajes.mover(base, mensaje_id, mensajes.Estado.EN_ESPERA, ahora=MIERCOLES)

    assert Guardrail.TOPE in codigos(await revisar(base))


@sin_mongo
async def test_g4_por_debajo_del_tope_pasa(base) -> None:
    await base["vendedores"].update_one({"maquina": "mac-rocio"}, {"$set": {"tope_diario": 20}})
    assert Guardrail.TOPE not in codigos(await revisar(base))


def test_g4_el_tope_por_corrida_es_otra_cosa() -> None:
    """Protege de un bug que encole de más, no de que se bloquee una línea."""
    config = {"tope_por_corrida": 25}
    assert guardrails.cabe_en_la_corrida(24, config) is None
    assert guardrails.cabe_en_la_corrida(25, config) is not None


# ---------------------------------------------------------------------------
# G5 — Anti-duplicado
# ---------------------------------------------------------------------------


@sin_mongo
async def test_g5_no_se_le_escribe_dos_veces_al_mismo_contacto(base) -> None:
    from bson import ObjectId

    mensaje_id = await mensajes.crear_borrador(
        base,
        corrida_id=ObjectId(),
        maquina="mac-rocio",
        contacto_id="+5491144405036",
        contacto_nombre="Marcelo",
        texto="Primer mensaje",
        ahora=MIERCOLES,
    )
    await mensajes.mover(base, mensaje_id, mensajes.Estado.EN_ESPERA, ahora=MIERCOLES)

    assert Guardrail.DUPLICADO in codigos(await revisar(base))


@sin_mongo
async def test_g5_un_encolado_que_todavia_no_salio_igual_cuenta(base) -> None:
    """⚠️ Si no contara, disparar la corrida dos veces mandaría dos mensajes.

    El primero todavía no llegó, pero va a llegar.
    """
    from bson import ObjectId

    mensaje_id = await mensajes.crear_borrador(
        base,
        corrida_id=ObjectId(),
        maquina="mac-rocio",
        contacto_id="+5491144405036",
        contacto_nombre="Marcelo",
        texto="Va a salir",
        ahora=MIERCOLES,
    )
    await mensajes.mover(base, mensaje_id, mensajes.Estado.EN_ESPERA, ahora=MIERCOLES)

    assert Guardrail.DUPLICADO in codigos(await revisar(base))


@sin_mongo
async def test_g5_pasados_los_dias_se_le_puede_volver_a_escribir(base) -> None:
    from bson import ObjectId

    hace_mucho = MIERCOLES - timedelta(days=30)
    mensaje_id = await mensajes.crear_borrador(
        base,
        corrida_id=ObjectId(),
        maquina="mac-rocio",
        contacto_id="+5491144405036",
        contacto_nombre="Marcelo",
        texto="Mensaje viejo",
        ahora=hace_mucho,
    )
    await mensajes.mover(base, mensaje_id, mensajes.Estado.EN_ESPERA, ahora=hace_mucho)

    assert Guardrail.DUPLICADO not in codigos(await revisar(base))


@sin_mongo
async def test_g5_un_mensaje_descartado_no_bloquea_al_siguiente(base) -> None:
    """Si se vetó o se rechazó, ese contacto no recibió nada."""
    from bson import ObjectId

    mensaje_id = await mensajes.crear_borrador(
        base,
        corrida_id=ObjectId(),
        maquina="mac-rocio",
        contacto_id="+5491144405036",
        contacto_nombre="Marcelo",
        texto="Este se vetó",
        ahora=MIERCOLES,
    )
    await mensajes.mover(
        base,
        mensaje_id,
        mensajes.Estado.DESCARTADO,
        motivo=mensajes.Motivo.VETADO,
        ahora=MIERCOLES,
    )

    assert Guardrail.DUPLICADO not in codigos(await revisar(base))


# ---------------------------------------------------------------------------
# G6 — Ventana horaria
# ---------------------------------------------------------------------------

VENTANA = {"inicio": "09:00", "fin": "19:00", "dias": [1, 2, 3, 4, 5]}


@pytest.mark.parametrize(
    ("cuando", "pasa"),
    [
        (datetime(2026, 8, 19, 9, 0, tzinfo=UTC), True),  # justo al abrir
        (datetime(2026, 8, 19, 13, 0, tzinfo=UTC), True),  # mediodía
        (datetime(2026, 8, 19, 18, 59, tzinfo=UTC), True),  # justo antes de cerrar
        (datetime(2026, 8, 19, 8, 59, tzinfo=UTC), False),  # un minuto temprano
        (datetime(2026, 8, 19, 19, 0, tzinfo=UTC), False),  # justo al cerrar
        (datetime(2026, 8, 19, 3, 0, tzinfo=UTC), False),  # de madrugada
        (datetime(2026, 8, 22, 13, 0, tzinfo=UTC), False),  # sábado
        (datetime(2026, 8, 23, 13, 0, tzinfo=UTC), False),  # domingo
    ],
)
def test_g6_la_ventana_horaria(cuando: datetime, pasa: bool) -> None:
    """No es cortesía: un mensaje comercial a las 3 AM es de lo que hace que a
    alguien lo reporten, y lo reportado es lo que bloquea líneas."""
    assert (revisar_ventana(VENTANA, ahora=cuando) is None) is pasa


def test_g6_una_ventana_sin_configurar_usa_lo_razonable() -> None:
    assert revisar_ventana({}, ahora=datetime(2026, 8, 19, 13, 0, tzinfo=UTC)) is None
    assert revisar_ventana({}, ahora=datetime(2026, 8, 19, 3, 0, tzinfo=UTC)) is not None


@sin_mongo
async def test_g6_llega_hasta_la_revision_completa(base) -> None:
    madrugada = datetime(2026, 8, 19, 3, 0, tzinfo=UTC)
    assert Guardrail.VENTANA in codigos(await revisar(base, ahora=madrugada))


@sin_mongo
async def test_g6_se_puede_saltear_para_el_modo_prueba(base) -> None:
    """Probar a las tres de la mañana tiene que ser posible; enviar, no."""
    madrugada = datetime(2026, 8, 19, 3, 0, tzinfo=UTC)
    violaciones = await revisar(base, ahora=madrugada, verificar_ventana=False)
    assert Guardrail.VENTANA not in codigos(violaciones)


# ---------------------------------------------------------------------------
# G7 — Pausa
# ---------------------------------------------------------------------------


@sin_mongo
async def test_g7_la_pausa_global_frena_todo(base) -> None:
    await configuracion.pausar(base, pausado=True, quien="prueba")
    assert Guardrail.PAUSA in codigos(await revisar(base))


@sin_mongo
async def test_g7_una_maquina_pausada_por_su_vendedor_no_manda(base) -> None:
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"}, {"$set": {"pausado_hasta": MIERCOLES + timedelta(hours=4)}}
    )
    assert Guardrail.PAUSA in codigos(await revisar(base, ahora=MIERCOLES))


@sin_mongo
async def test_g7_una_maquina_inactiva_no_manda(base) -> None:
    await base["vendedores"].update_one({"maquina": "mac-rocio"}, {"$set": {"activo": False}})
    assert Guardrail.PAUSA in codigos(await revisar(base))


@sin_mongo
async def test_g7_sin_consentimiento_no_manda(base) -> None:
    """R6: salen mensajes en su nombre, desde su línea. Tiene que constar que sabe."""
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"}, {"$set": {"acepto_condiciones_en": None}}
    )
    violaciones = await revisar(base)
    assert Guardrail.PAUSA in codigos(violaciones)
    assert any("consentimiento" in v.detalle for v in violaciones)


@sin_mongo
async def test_g7_una_maquina_que_no_existe_no_manda(base) -> None:
    violaciones = await revisar(base, maquina="mac-inventada")
    assert Guardrail.PAUSA in codigos(violaciones)


# ---------------------------------------------------------------------------
# La forma de la revisión
# ---------------------------------------------------------------------------


@sin_mongo
async def test_se_devuelven_todas_las_violaciones_no_la_primera(base) -> None:
    """Quien mira quiere saber todo lo que hay que arreglar, no de a una."""
    await configuracion.actualizar(base, {"destinos_permitidos": []})
    madrugada = datetime(2026, 8, 19, 3, 0, tzinfo=UTC)

    violaciones = await revisar(base, texto="Hola {nombre}", ahora=madrugada)

    assert {Guardrail.DESTINO, Guardrail.TEXTO, Guardrail.VENTANA} <= codigos(violaciones)


@sin_mongo
async def test_exigir_lanza_con_la_primera(base) -> None:
    with pytest.raises(guardrails.GuardrailViolado) as error:
        await guardrails.exigir(
            base,
            contacto_id="+5491133445566",
            texto="Hola",
            maquina="mac-rocio",
            ahora=MIERCOLES,
        )
    assert error.value.codigo is Guardrail.DESTINO


@sin_mongo
async def test_exigir_no_lanza_con_un_mensaje_bien_formado(base) -> None:
    await guardrails.exigir(
        base,
        contacto_id="+5491144405036",
        texto="Hola Marcelo, ¿avanzamos?",
        maquina="mac-rocio",
        ahora=MIERCOLES,
    )


@sin_mongo
async def test_se_le_puede_pasar_la_configuracion_ya_leida(base) -> None:
    """Encolar veinte mensajes no puede leer la configuración veinte veces."""
    config = await configuracion.obtener(base)
    vendedor = await base["vendedores"].find_one({"maquina": "mac-rocio"})

    assert await revisar(base, config=config, vendedor=vendedor) == []


def test_una_violacion_se_lee_sola() -> None:
    """Va al panel y al log: tiene que decir qué pasó sin abrir el código."""
    violacion = guardrails.Violacion(Guardrail.TEXTO, "quedó un placeholder")
    assert "G3_TEXTO_INVALIDO" in str(violacion)
    assert "placeholder" in str(violacion)


def test_los_ocho_guardrails_estan_declarados() -> None:
    """Ocho, no veinte. Si alguien agrega el noveno, que sea a propósito."""
    assert len(Guardrail) == 8


def test_dos_guardrails_solo_existen_en_el_agente() -> None:
    """G1 y G8 se verifican mirando la pantalla real: el backend no puede."""
    assert Guardrail.IDENTIDAD in Guardrail
    assert Guardrail.CAMPO_NO_VACIO in Guardrail
