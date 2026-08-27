"""Tests de la validación: guardrails + triage sobre una tanda real.

Acá se prueba lo que ninguno de los dos módulos puede probar solo: que el orden
sea el correcto, que el estado de cada mensaje termine donde corresponde, y que
el circuito completo —generar, validar, revisar, enviar— cierre.
"""

from __future__ import annotations

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from bson import ObjectId
from conftest import ar

from app.core import configuracion, mensajes, validacion, vendedores
from app.core.esquema import inicializar
from app.core.estados import Estado, Motivo

MIERCOLES = ar(19, 11, 0)  # media mañana en Argentina

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
        await configuracion.actualizar(db, {"destinos_permitidos": ["*"]})
        await vendedores.dar_de_alta(db, maquina="mac-rocio", nombre="Rocío")
        await db["vendedores"].update_one(
            {"maquina": "mac-rocio"},
            {"$set": {"activo": True, "acepto_condiciones_en": MIERCOLES}},
        )
        yield db
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


async def borrador(base, corrida: ObjectId, n: int, **extra) -> ObjectId:
    opciones = {
        "corrida_id": corrida,
        "maquina": "mac-rocio",
        "contacto_id": f"+54911000{n:05d}",
        "contacto_nombre": f"Contacto {n}",
        "texto": "Hola, quedó pendiente lo que hablamos. ¿Seguimos?",
        "resumen_ultimo": "preguntó por precio de chapa",
        "quien_hablo_ultimo": "contacto",
        "ahora": MIERCOLES,
    }
    opciones.update(extra)
    return await mensajes.crear_borrador(base, **opciones)


async def estado_de(base, mensaje_id: ObjectId) -> str:
    return (await base["mensajes"].find_one({"_id": mensaje_id}))["estado"]


# ---------------------------------------------------------------------------
# Los tres caminos
# ---------------------------------------------------------------------------


@sin_mongo
async def test_un_borrador_limpio_queda_listo_para_salir(base) -> None:
    corrida = ObjectId()
    mensaje_id = await borrador(base, corrida, 1)

    resultado = await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    assert resultado.en_espera == [mensaje_id]
    assert await estado_de(base, mensaje_id) == Estado.EN_ESPERA


@sin_mongo
async def test_un_borrador_con_placeholder_se_descarta(base) -> None:
    """Guardrail: no sale nunca. Nadie tiene que decidir nada sobre esto."""
    corrida = ObjectId()
    mensaje_id = await borrador(base, corrida, 1, texto="Hola {nombre}, ¿seguimos?")

    resultado = await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    assert resultado.rechazados == [mensaje_id]
    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == Estado.DESCARTADO
    assert documento["motivo"] == Motivo.RECHAZADO
    assert "G3_TEXTO_INVALIDO" in documento["senales"]


@sin_mongo
async def test_un_borrador_sobre_un_reclamo_se_retiene(base) -> None:
    """Triage: puede salir, pero que lo mire alguien."""
    corrida = ObjectId()
    mensaje_id = await borrador(base, corrida, 1, resumen_ultimo="puso un reclamo por la entrega")

    resultado = await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    assert resultado.retenidos == [mensaje_id]
    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == Estado.RETENIDO
    assert "PALABRA_CONFLICTO" in documento["senales"]


@sin_mongo
async def test_el_guardrail_gana_sobre_el_triage(base) -> None:
    """⚠️ El orden importa.

    Si un mensaje no puede salir, no tiene sentido apartarlo para que alguien
    decida si sale. El panel no le pide una decisión a nadie sobre algo que ya
    está decidido.
    """
    corrida = ObjectId()
    mensaje_id = await borrador(
        base,
        corrida,
        1,
        texto="Hola {nombre}",  # guardrail
        resumen_ultimo="puso un reclamo",  # triage
    )

    await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == Estado.DESCARTADO
    assert "PALABRA_CONFLICTO" not in documento["senales"]


# ---------------------------------------------------------------------------
# La tanda entera
# ---------------------------------------------------------------------------


@sin_mongo
async def test_una_tanda_se_reparte_en_los_tres_grupos(base) -> None:
    corrida = ObjectId()
    await borrador(base, corrida, 1)
    await borrador(base, corrida, 2)
    await borrador(base, corrida, 3, texto="Hola {nombre}")
    await borrador(base, corrida, 4, resumen_ultimo="quiere cancelar el pedido")

    resultado = await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    assert len(resultado.en_espera) == 2
    assert len(resultado.retenidos) == 1
    assert len(resultado.rechazados) == 1
    assert resultado.total == 4


@sin_mongo
async def test_dos_borradores_para_el_mismo_contacto_no_pasan_los_dos(base) -> None:
    """⚠️ Por esto la validación es secuencial y no en paralelo.

    Si se validaran a la vez, los dos verían "todavía no le escribimos" y los
    dos pasarían — y ese contacto recibiría dos mensajes.
    """
    corrida = ObjectId()
    await borrador(base, corrida, 1, contacto_id="+5491144405036", texto="Primero")
    await borrador(base, corrida, 2, contacto_id="+5491144405036", texto="Segundo")

    resultado = await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    assert len(resultado.en_espera) == 1
    assert len(resultado.rechazados) == 1


@sin_mongo
async def test_el_tope_por_corrida_corta(base) -> None:
    """Protege de un LISTAR que devuelve mil chats en vez de veinte."""
    await configuracion.actualizar(base, {"tope_por_corrida": 3})
    corrida = ObjectId()
    for n in range(6):
        await borrador(base, corrida, n)

    resultado = await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    assert len(resultado.en_espera) == 3
    assert len(resultado.rechazados) == 3


@sin_mongo
async def test_dos_contactos_con_el_mismo_nombre_se_retienen(base) -> None:
    """Sólo se ve mirando la tanda entera: son dos negocios distintos."""
    corrida = ObjectId()
    uno = await borrador(base, corrida, 1, contacto_nombre="Ferretería Sur")
    otro = await borrador(base, corrida, 2, contacto_nombre="Ferreteria Sur")

    await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    for mensaje_id in (uno, otro):
        documento = await base["mensajes"].find_one({"_id": mensaje_id})
        assert documento["estado"] == Estado.RETENIDO
        assert "IDENTIDAD_AMBIGUA" in documento["senales"]


@sin_mongo
async def test_validar_dos_veces_no_toca_lo_ya_validado(base) -> None:
    """Sólo mira los BORRADOR. Correrlo de nuevo no revierte una decisión."""
    corrida = ObjectId()
    mensaje_id = await borrador(base, corrida, 1)
    await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)
    await mensajes.mover(base, mensaje_id, Estado.DESCARTADO, motivo=Motivo.VETADO)

    resultado = await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    assert resultado.total == 0
    assert await estado_de(base, mensaje_id) == Estado.DESCARTADO


@sin_mongo
async def test_una_corrida_sin_borradores_no_rompe(base) -> None:
    assert (await validacion.validar_corrida(base, ObjectId())).total == 0


@sin_mongo
async def test_no_se_valida_fuera_de_la_ventana_horaria(base) -> None:
    """⚠️ Generar de noche está bien; enviar de noche, no.

    Si la validación mirara la ventana, una corrida disparada a las ocho de la
    tarde rechazaría todo — y esos borradores eran perfectamente válidos para
    mandar al día siguiente.
    """
    corrida = ObjectId()
    mensaje_id = await borrador(base, corrida, 1)
    de_noche = ar(19, 22, 0)  # las diez de la noche, para quien lo recibiría

    resultado = await validacion.validar_corrida(base, corrida, ahora=de_noche)

    assert resultado.en_espera == [mensaje_id]


# ---------------------------------------------------------------------------
# Revalidar lo que editó una persona
# ---------------------------------------------------------------------------


@sin_mongo
async def test_un_humano_que_escribe_un_placeholder_recibe_el_mismo_rechazo(base) -> None:
    """El sistema no tiene forma de saber quién escribió el texto, ni debería."""
    corrida = ObjectId()
    mensaje_id = await borrador(base, corrida, 1)
    await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    await mensajes.editar_texto(base, mensaje_id, "Hola {nombre}", quien="martin")
    violaciones = await validacion.revalidar_editado(base, mensaje_id, ahora=MIERCOLES)

    assert any("placeholder" in v.detalle for v in violaciones)


@sin_mongo
async def test_un_texto_editado_bien_no_da_problemas(base) -> None:
    corrida = ObjectId()
    mensaje_id = await borrador(base, corrida, 1)
    await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    await mensajes.editar_texto(base, mensaje_id, "Hola Marcelo, ¿avanzamos?", quien="martin")

    assert await validacion.revalidar_editado(base, mensaje_id, ahora=MIERCOLES) == []


@sin_mongo
async def test_revalidar_un_mensaje_que_no_existe_falla(base) -> None:
    with pytest.raises(mensajes.MensajeDesconocido):
        await validacion.revalidar_editado(base, ObjectId())


# ---------------------------------------------------------------------------
# La proporción retenida — el número con el que se calibra
# ---------------------------------------------------------------------------


@sin_mongo
async def test_la_proporcion_retenida_se_calcula_sobre_lo_que_puede_salir(base) -> None:
    """Los rechazados no cuentan: no eran candidatos a que alguien los mirara."""
    corrida = ObjectId()
    for n in range(8):
        await borrador(base, corrida, n)
    await borrador(base, corrida, 20, resumen_ultimo="puso un reclamo")
    await borrador(base, corrida, 21, texto="Hola {nombre}")

    resultado = await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    # 8 listos + 1 retenido = 9 candidatos; 1 retenido sobre 9.
    assert resultado.proporcion_retenida == pytest.approx(1 / 9)


def test_la_proporcion_de_una_tanda_vacia_es_cero() -> None:
    assert validacion.Resultado().proporcion_retenida == 0.0


# ---------------------------------------------------------------------------
# El circuito completo
# ---------------------------------------------------------------------------


@sin_mongo
async def test_de_borrador_a_envio_encolado(base) -> None:
    """Generar, validar, aprobar y encolar. El recorrido entero."""
    from app.core import cola, corridas

    corrida_id = (
        await base["corridas"].insert_one(
            {
                "disparada_por": "panel",
                "tipo": "generacion",
                "modo": "prueba",
                "estado": "generando",
                "maquinas": ["mac-rocio"],
                "creada_en": MIERCOLES,
            }
        )
    ).inserted_id

    for n in range(5):
        await borrador(base, corrida_id, n)

    resultado = await validacion.validar_corrida(base, corrida_id, ahora=MIERCOLES)
    assert len(resultado.en_espera) == 5

    encolado = await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)
    assert encolado.mensajes == 5

    jobs = await base["jobs"].find({"corrida_id": corrida_id}).to_list(None)
    assert len(jobs) == 5
    assert all(j["tipo"] == cola.Tipo.ENVIAR for j in jobs)
    assert all(j["payload"]["modo"] == "prueba" for j in jobs)


@sin_mongo
async def test_el_canario_abre_un_hueco_antes_del_resto(base) -> None:
    """⚠️ Los tres primeros y después diez minutos.

    Si esos tres fallan, frenar cuesta diecisiete mensajes menos que enterarse
    al final.
    """
    from app.core import cola, corridas

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "revision", "creada_en": MIERCOLES}
    )
    for n in range(10):
        await borrador(base, corrida_id, n)
    await validacion.validar_corrida(base, corrida_id, ahora=MIERCOLES)

    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)

    jobs = sorted(
        await base["jobs"].find({"corrida_id": corrida_id}).to_list(None),
        key=lambda j: j["disponible_desde"],
    )
    salto = (
        jobs[cola.CANARIO]["disponible_desde"] - jobs[cola.CANARIO - 1]["disponible_desde"]
    ).total_seconds()

    assert salto >= cola.ESPERA_CANARIO_S


@sin_mongo
async def test_no_se_encola_fuera_de_la_ventana(base) -> None:
    from app.core import corridas

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "revision", "creada_en": MIERCOLES}
    )
    await borrador(base, corrida_id, 1)
    await validacion.validar_corrida(base, corrida_id, ahora=MIERCOLES)

    de_noche = MIERCOLES.replace(hour=23)
    with pytest.raises(corridas.FueraDeVentana):
        await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=de_noche)


@sin_mongo
async def test_no_se_encola_con_el_kill_switch_puesto(base) -> None:
    from app.core import corridas

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "revision", "creada_en": MIERCOLES}
    )
    await borrador(base, corrida_id, 1)
    await validacion.validar_corrida(base, corrida_id, ahora=MIERCOLES)
    await configuracion.pausar(base, pausado=True, quien="prueba")

    with pytest.raises(corridas.Pausado):
        await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)


@sin_mongo
async def test_un_retenido_no_se_encola_hasta_que_alguien_lo_libere(base) -> None:
    from app.core import corridas

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "revision", "creada_en": MIERCOLES}
    )
    retenido = await borrador(base, corrida_id, 1, resumen_ultimo="puso un reclamo")
    await validacion.validar_corrida(base, corrida_id, ahora=MIERCOLES)

    assert (
        await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)
    ).mensajes == 0

    await mensajes.mover(base, retenido, Estado.EN_ESPERA, quien="panel")
    assert (
        await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)
    ).mensajes == 1


@sin_mongo
async def test_el_canario_fallido_frena_todo(base) -> None:
    """Los tres primeros terminaron y ninguno salió bien: algo está roto."""
    from app.core import cola, corridas

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "enviando", "creada_en": MIERCOLES}
    )
    for n in range(6):
        await borrador(base, corrida_id, n)
    await validacion.validar_corrida(base, corrida_id, ahora=MIERCOLES)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)

    jobs = sorted(
        await base["jobs"].find({"corrida_id": corrida_id}).to_list(None),
        key=lambda j: j["disponible_desde"],
    )
    for job in jobs[: cola.CANARIO]:
        await base["jobs"].update_one(
            {"_id": job["_id"]}, {"$set": {"estado": str(cola.EstadoJob.FALLIDO)}}
        )

    assert await corridas.revisar_canario(base, corrida_id) is True
    assert await configuracion.esta_pausado(base) is True


@sin_mongo
async def test_el_canario_con_uno_bueno_no_frena(base) -> None:
    """Uno que falla entre tres es mala suerte, no un sistema roto."""
    from app.core import cola, corridas

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "enviando", "creada_en": MIERCOLES}
    )
    for n in range(6):
        await borrador(base, corrida_id, n)
    await validacion.validar_corrida(base, corrida_id, ahora=MIERCOLES)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)

    jobs = sorted(
        await base["jobs"].find({"corrida_id": corrida_id}).to_list(None),
        key=lambda j: j["disponible_desde"],
    )
    estados = [cola.EstadoJob.FALLIDO, cola.EstadoJob.LISTO, cola.EstadoJob.FALLIDO]
    for job, estado in zip(jobs[: cola.CANARIO], estados, strict=True):
        await base["jobs"].update_one({"_id": job["_id"]}, {"$set": {"estado": str(estado)}})

    assert await corridas.revisar_canario(base, corrida_id) is False
    assert await configuracion.esta_pausado(base) is False


@sin_mongo
async def test_el_canario_no_decide_con_jobs_a_medias(base) -> None:
    """Con uno solo reportado no se distingue mala suerte de sistema roto."""
    from app.core import cola, corridas

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "enviando", "creada_en": MIERCOLES}
    )
    for n in range(6):
        await borrador(base, corrida_id, n)
    await validacion.validar_corrida(base, corrida_id, ahora=MIERCOLES)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)

    jobs = sorted(
        await base["jobs"].find({"corrida_id": corrida_id}).to_list(None),
        key=lambda j: j["disponible_desde"],
    )
    await base["jobs"].update_one(
        {"_id": jobs[0]["_id"]}, {"$set": {"estado": str(cola.EstadoJob.FALLIDO)}}
    )

    assert await corridas.revisar_canario(base, corrida_id) is False
    assert await configuracion.esta_pausado(base) is False


@sin_mongo
async def test_una_corrida_frenada_se_puede_reanudar(base) -> None:
    """D31: el "ya lo miré, continuar". Vuelve a `enviando` y suelta el freno.

    Antes `frenada` era un estado sin salida: la alerta del canario quedaba
    encendida para siempre y la única forma de apagarla era cancelar, perdiendo
    los envíos pendientes.
    """
    from app.core import cola, corridas

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "enviando", "creada_en": MIERCOLES}
    )
    for n in range(6):
        await borrador(base, corrida_id, n)
    await validacion.validar_corrida(base, corrida_id, ahora=MIERCOLES)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)

    jobs = sorted(
        await base["jobs"].find({"corrida_id": corrida_id}).to_list(None),
        key=lambda j: j["disponible_desde"],
    )
    for job in jobs[: cola.CANARIO]:
        await base["jobs"].update_one(
            {"_id": job["_id"]}, {"$set": {"estado": str(cola.EstadoJob.FALLIDO)}}
        )
    assert await corridas.revisar_canario(base, corrida_id) is True

    await corridas.reanudar(base, corrida_id, quien="panel", ahora=MIERCOLES)

    assert (await base["corridas"].find_one({"_id": corrida_id}))["estado"] == "enviando"
    assert await configuracion.esta_pausado(base) is False
    evento = await base["auditoria"].find_one({"que": "corrida_reanudada"})
    assert evento is not None and evento["quien"] == "panel"


@sin_mongo
async def test_reanudar_una_corrida_que_no_esta_frenada_falla(base) -> None:
    """Reanudar otra cosa no significa nada: aceptarlo escondería un bug."""
    import pytest

    from app.core import corridas

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "enviando", "creada_en": MIERCOLES}
    )

    with pytest.raises(corridas.NoEstaFrenada):
        await corridas.reanudar(base, corrida_id, quien="panel", ahora=MIERCOLES)


@sin_mongo
async def test_cancelar_una_corrida_enviando_resuelve_los_mensajes(base) -> None:
    """D31: nada queda en `ENVIANDO` o `EN_ESPERA` esperando un envío que no
    va a llegar. Pasan a `DESCARTADO` con motivo `cancelado`."""
    from app.core import corridas
    from app.core.estados import Motivo

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "enviando", "creada_en": MIERCOLES}
    )
    for n in range(3):
        await borrador(base, corrida_id, n)
    await validacion.validar_corrida(base, corrida_id, ahora=MIERCOLES)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)
    # Uno ya lo tomó un agente:
    en_espera = await base["mensajes"].find({"corrida_id": corrida_id}).to_list(None)
    await mensajes.mover(base, en_espera[0]["_id"], Estado.ENVIANDO, quien="mac-rocio")

    await corridas.cancelar(base, corrida_id, quien="panel", ahora=MIERCOLES)

    finales = await base["mensajes"].find({"corrida_id": corrida_id}).to_list(None)
    assert {m["estado"] for m in finales} == {str(Estado.DESCARTADO)}
    assert {m["motivo"] for m in finales} == {str(Motivo.CANCELADO)}


@sin_mongo
async def test_un_mensaje_vencido_no_se_encola(base) -> None:
    """Entre que se generó y que alguien apretó enviar pasó un día."""
    from app.core import corridas

    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {"_id": corrida_id, "modo": "prueba", "estado": "revision", "creada_en": MIERCOLES}
    )
    viejo = MIERCOLES - timedelta(hours=25)
    await borrador(base, corrida_id, 1, ahora=viejo)
    await validacion.validar_corrida(base, corrida_id, ahora=viejo)

    await mensajes.vencer_viejos(base, ahora=MIERCOLES)

    encolado = await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=MIERCOLES)
    assert encolado.mensajes == 0


@sin_mongo
async def test_revalidar_no_se_encuentra_a_si_mismo_como_duplicado(base) -> None:
    """⚠️ El bug que el test destapó.

    Revalidar corría los seis guardrails, y el anti-duplicado cuenta los
    mensajes que están por salir — incluido el que se acababa de editar. Decía
    "ya le escribimos a este contacto" sobre el mensaje mismo, y editar un
    borrador aprobado era imposible.
    """
    corrida = ObjectId()
    mensaje_id = await borrador(base, corrida, 1)
    await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    await mensajes.editar_texto(base, mensaje_id, "Otro texto, igual de válido", quien="martin")

    assert await validacion.revalidar_editado(base, mensaje_id, ahora=MIERCOLES) == []


@sin_mongo
async def test_revalidar_si_mira_la_lista_de_destinos(base) -> None:
    """Pudo cambiar entre que el mensaje se aprobó y que alguien lo editó."""
    corrida = ObjectId()
    mensaje_id = await borrador(base, corrida, 1)
    await validacion.validar_corrida(base, corrida, ahora=MIERCOLES)

    await configuracion.actualizar(base, {"destinos_permitidos": []})
    violaciones = await validacion.revalidar_editado(base, mensaje_id, ahora=MIERCOLES)

    assert any("destinos permitidos" in v.detalle for v in violaciones)
