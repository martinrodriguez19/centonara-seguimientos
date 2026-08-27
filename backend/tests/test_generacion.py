"""El puente entre `LISTAR`, `REDACTAR` y un borrador.

Es lo que faltaba para que una corrida llegue a algún lado: hasta acá el
resultado de un `LISTAR` se guardaba y no lo leía nadie, y `Tipo.REDACTAR` no lo
encolaba ningún código.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from bson import ObjectId

from app import db
from app.core import cola, configuracion, generacion, mensajes, triage
from app.core.esquema import inicializar
from app.core.estados import Estado

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

TRES = ["+5491123231151", "+5491136007586", "+5491139273345"]


@pytest.fixture
async def base(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    db_prueba = cliente[nombre]
    await inicializar(db_prueba)
    monkeypatch.setattr(db, "obtener_base", lambda: db_prueba)
    try:
        yield db_prueba
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


def chat(telefono="+54 9 11 2323-1151", **cambios):
    base = {
        "contacto_nombre": "Corralón San Justo",
        "contacto_telefono": telefono,
        "ultimo_mensaje_resumen": "preguntó por hierro del 8",
        "quien_hablo_ultimo": "contacto",
        "antiguedad_dias": 6,
    }
    base.update(cambios)
    return base


async def abrir_destinos(base, numeros=None):
    await configuracion.actualizar(base, {"destinos_permitidos": numeros or TRES})


# ---------------------------------------------------------------------------
# LISTAR -> REDACTAR
# ---------------------------------------------------------------------------


@sin_mongo
async def test_un_chat_permitido_se_convierte_en_un_redactar(base) -> None:
    await abrir_destinos(base)
    corrida = ObjectId()

    resultado = await generacion.encolar_redacciones(
        base, corrida_id=corrida, maquina="pc-1", chats=[chat()]
    )

    assert resultado.total == 1
    job = await base["jobs"].find_one({"_id": resultado.jobs[0]})
    assert job["tipo"] == str(cola.Tipo.REDACTAR)
    assert job["maquina"] == "pc-1"


@sin_mongo
async def test_el_telefono_no_viaja_en_el_payload_pero_si_en_el_contexto(base) -> None:
    """⚠️ `REDACTAR` no lleva teléfono: no lo necesita y no debe tenerlo.

    Redacta sin navegador y no envía nada, así que `PayloadRedactar` lo prohíbe.
    Pero el borrador que sale de su resultado sí necesita saber a quién es, y el
    triage necesita el número para revisar identidad y anti-duplicado. Por eso
    queda de este lado, en `contexto`, que el agente no recibe.
    """
    await abrir_destinos(base)
    resultado = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat()]
    )

    job = await base["jobs"].find_one({"_id": resultado.jobs[0]})
    assert "contacto_id" not in job["payload"]
    assert "contacto_telefono" not in job["payload"]
    assert job["contexto"]["contacto_id"] == "+5491123231151"


@sin_mongo
async def test_el_payload_es_el_que_el_esquema_acepta(base) -> None:
    """Si esto se desvía, el job explota recién en la máquina del vendedor."""
    from app.modelos.jobs import validar_payload

    await abrir_destinos(base)
    resultado = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat()]
    )

    job = await base["jobs"].find_one({"_id": resultado.jobs[0]})
    validar_payload("REDACTAR", job["payload"])


@sin_mongo
async def test_un_chat_sin_telefono_no_se_encola_y_se_cuenta(base) -> None:
    """`null` es una respuesta correcta del prompt, no un error."""
    await abrir_destinos(base)
    resultado = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat(telefono=None)]
    )

    assert resultado.total == 0
    assert resultado.sin_telefono == 1


@sin_mongo
async def test_un_chat_sin_telefono_va_a_resolver_con_sus_datos_guardados(base) -> None:
    """Ya no se descarta: el número vive en el panel de contacto de ese chat, y
    un `RESOLVER` determinístico lo va a buscar. Los datos del chat esperan en
    el `contexto`, del lado del backend — el agente sólo recibe nombres."""
    from app.modelos.jobs import validar_payload

    await abrir_destinos(base)
    resultado = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat(telefono=None)]
    )

    assert resultado.resolver_job is not None
    job = await base["jobs"].find_one({"_id": resultado.resolver_job})
    assert job["tipo"] == str(cola.Tipo.RESOLVER)
    assert job["payload"]["contactos"] == ["Corralón San Justo"]
    assert job["contexto"]["chats"]["Corralón San Justo"]["antiguedad_dias"] == 6
    validar_payload("RESOLVER", job["payload"])


@sin_mongo
async def test_sin_destinos_no_se_resuelve_nada(base) -> None:
    """Lista vacía significa a nadie (R4): resolver un número que después se
    filtraría es trabajar para un mensaje que no puede existir."""
    await configuracion.actualizar(base, {"destinos_permitidos": []})
    resultado = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat(telefono=None)]
    )

    assert resultado.resolver_job is None
    assert await base["jobs"].count_documents({}) == 0


@sin_mongo
async def test_el_resolver_reportado_dos_veces_no_duplica_redacciones(base) -> None:
    """La misma idempotencia que tiene el LISTAR, por contacto resuelto."""
    await abrir_destinos(base)
    corrida = ObjectId()
    encoladas = await generacion.encolar_redacciones(
        base, corrida_id=corrida, maquina="pc-1", chats=[chat(telefono=None)]
    )
    job = await base["jobs"].find_one({"_id": encoladas.resolver_job})
    contactos = [{"nombre": "Corralón San Justo", "telefono": "+54 9 11 2323-1151"}]

    primera = await generacion.encolar_redacciones_resueltas(base, job=job, contactos=contactos)
    segunda = await generacion.encolar_redacciones_resueltas(base, job=job, contactos=contactos)

    assert primera.total == 1
    assert segunda.total == 0
    assert await base["jobs"].count_documents({"tipo": str(cola.Tipo.REDACTAR)}) == 1


@sin_mongo
async def test_un_telefono_ilegible_se_trata_como_si_no_estuviera(base) -> None:
    await abrir_destinos(base)
    resultado = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat(telefono="llamar al fijo")]
    )

    assert resultado.sin_telefono == 1


@sin_mongo
async def test_no_se_paga_por_redactar_para_quien_no_se_le_puede_escribir(base) -> None:
    """⚠️ R4, y además plata.

    Un borrador para un número fuera de `destinos_permitidos` no va a poder
    salir nunca. Redactarlo cuesta una llamada al modelo para producir algo que
    el guardrail G2 va a rechazar después.
    """
    await abrir_destinos(base, ["+5491123231151"])

    resultado = await generacion.encolar_redacciones(
        base,
        corrida_id=ObjectId(),
        maquina="pc-1",
        chats=[chat(), chat(telefono="+5491155550000"), chat(telefono="+5491166660000")],
    )

    assert resultado.total == 1
    assert resultado.no_permitidos == 2


@sin_mongo
async def test_sin_destinos_configurados_no_se_encola_nada(base) -> None:
    """Lista vacía significa a nadie. Es el estado de fábrica, y es correcto."""
    resultado = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat(), chat(telefono=TRES[1])]
    )

    assert resultado.total == 0
    assert resultado.no_permitidos == 2


@sin_mongo
async def test_reportar_el_mismo_listar_dos_veces_no_encola_de_nuevo(base) -> None:
    """⚠️ Pasa de verdad: el agente reporta, se corta la red antes de leer la
    respuesta, y el barrido devuelve el job a la cola. Sin esto se paga dos
    veces por las mismas veinte redacciones."""
    await abrir_destinos(base)
    corrida = ObjectId()
    chats = [chat(), chat(telefono=TRES[1])]

    primera = await generacion.encolar_redacciones(
        base, corrida_id=corrida, maquina="pc-1", chats=chats
    )
    segunda = await generacion.encolar_redacciones(
        base, corrida_id=corrida, maquina="pc-1", chats=chats
    )

    assert primera.total == 2
    assert segunda.total == 0
    assert segunda.repetido is True
    assert await base["jobs"].count_documents({"tipo": str(cola.Tipo.REDACTAR)}) == 2


@sin_mongo
async def test_dos_maquinas_no_se_pisan(base) -> None:
    """La idempotencia es por máquina: cada una lee sus propios chats."""
    await abrir_destinos(base)
    corrida = ObjectId()

    await generacion.encolar_redacciones(base, corrida_id=corrida, maquina="pc-1", chats=[chat()])
    otra = await generacion.encolar_redacciones(
        base, corrida_id=corrida, maquina="pc-2", chats=[chat(telefono=TRES[1])]
    )

    assert otra.total == 1


# ---------------------------------------------------------------------------
# REDACTAR -> borrador
# ---------------------------------------------------------------------------


def job_redactar(corrida: ObjectId, contacto_id: str = TRES[0]) -> dict:
    return {
        "_id": ObjectId(),
        "corrida_id": corrida,
        "maquina": "pc-1",
        "tipo": str(cola.Tipo.REDACTAR),
        "payload": {},
        "contexto": {
            "contacto_id": contacto_id,
            "contacto_nombre": "Corralón San Justo",
            "resumen": "preguntó por hierro del 8",
            "quien_hablo_ultimo": "contacto",
            "antiguedad_dias": 6,
        },
    }


@sin_mongo
async def test_el_texto_redactado_se_guarda_como_borrador(base) -> None:
    corrida = ObjectId()
    mensaje_id = await generacion.guardar_borrador(
        base,
        job=job_redactar(corrida),
        detalle={"status": "ok", "texto": "Hola, ¿confirmamos la cantidad?"},
    )

    guardado = await base["mensajes"].find_one({"_id": mensaje_id})
    assert guardado["estado"] == str(Estado.BORRADOR)
    assert guardado["contacto_id"] == TRES[0]
    assert guardado["texto"] == "Hola, ¿confirmamos la cantidad?"
    #  El contexto del chat viaja al borrador: el triage lo necesita.
    assert guardado["resumen_ultimo"] == "preguntó por hierro del 8"


@sin_mongo
async def test_nace_en_borrador_y_no_pasa_solo_a_en_espera(base) -> None:
    """Quien valida es `validar_corrida`, sobre la tanda entera.

    Dos contactos con el mismo nombre sólo se detectan mirando todo junto, así
    que un borrador no puede auto-aprobarse al nacer.
    """
    mensaje_id = await generacion.guardar_borrador(
        base, job=job_redactar(ObjectId()), detalle={"status": "ok", "texto": "Hola"}
    )
    guardado = await base["mensajes"].find_one({"_id": mensaje_id})

    assert guardado["estado"] == str(Estado.BORRADOR)


@sin_mongo
async def test_sin_contexto_queda_retenido_y_no_descartado(base) -> None:
    """⚠️ Sin esto, el guardrail G3 lo descartaba por texto vacío.

    El modelo se negó a inventar un seguimiento, que es la respuesta que el
    prompt pide. Perder ese chat en `DESCARTADO` convierte una decisión correcta
    en un cliente al que nadie le escribe.
    """
    mensaje_id = await generacion.guardar_borrador(
        base,
        job=job_redactar(ObjectId()),
        detalle={"status": "sin_contexto", "motivo": "es una charla personal"},
    )

    guardado = await base["mensajes"].find_one({"_id": mensaje_id})
    assert guardado["estado"] == str(Estado.RETENIDO)
    assert str(triage.Senal.SIN_CONTEXTO) in guardado["senales"]
    assert guardado["texto"] == ""


@sin_mongo
async def test_un_retenido_sin_contexto_lo_puede_escribir_una_persona(base) -> None:
    """Que quede retenido sirve sólo si desde ahí se puede seguir."""
    mensaje_id = await generacion.guardar_borrador(
        base, job=job_redactar(ObjectId()), detalle={"status": "sin_contexto", "motivo": "x"}
    )

    await mensajes.editar_texto(base, mensaje_id, "Hola, ¿seguimos?", quien="dueño")
    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, quien="dueño")

    guardado = await base["mensajes"].find_one({"_id": mensaje_id})
    assert guardado["estado"] == str(Estado.EN_ESPERA)
    assert guardado["texto"] == "Hola, ¿seguimos?"


@sin_mongo
async def test_un_job_sin_contacto_no_inventa_destinatario(base) -> None:
    """R2: falla explícito. Un borrador sin saber a quién es, no se crea."""
    job = job_redactar(ObjectId())
    job["contexto"] = {}

    assert (
        await generacion.guardar_borrador(base, job=job, detalle={"status": "ok", "texto": "Hola"})
        is None
    )
    assert await base["mensajes"].count_documents({}) == 0


@sin_mongo
async def test_el_mismo_redactar_reportado_dos_veces_deja_un_solo_mensaje(base) -> None:
    corrida = ObjectId()
    job = job_redactar(corrida)
    detalle = {"status": "ok", "texto": "Hola"}

    primero = await generacion.guardar_borrador(base, job=job, detalle=detalle)
    segundo = await generacion.guardar_borrador(base, job=job, detalle=detalle)

    assert primero is not None
    assert segundo is None
    assert await base["mensajes"].count_documents({"corrida_id": corrida}) == 1


# ---------------------------------------------------------------------------
# v1.2: contexto de empresa, anti-duplicado previo, memoria y barrido (D27)
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_contexto_de_empresa_viaja_en_el_payload(base) -> None:
    """Lo que el dueño escribió llega a cada redacción, y el esquema lo admite."""
    from app.modelos.jobs import validar_payload

    await abrir_destinos(base)
    await configuracion.actualizar(base, {"contexto_empresa": "Vendemos entradas de eventos."})

    resultado = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat()]
    )

    job = await base["jobs"].find_one({"_id": resultado.jobs[0]})
    assert job["payload"]["contexto_empresa"] == "Vendemos entradas de eventos."
    validar_payload("REDACTAR", job["payload"])


@sin_mongo
async def test_las_indicaciones_largas_llegan_enteras_a_la_redaccion(base) -> None:
    """⚠️ D33: los tres topes tienen que coincidir.

    El del endpoint deja guardar 20.000; si el recorte de acá o el esquema del
    payload se quedaran cortos, el dueño escribiría un catálogo que el redactor
    nunca ve entero — y nadie se enteraría, porque no falla nada.
    """
    from app.modelos.jobs import validar_payload

    await abrir_destinos(base)
    indicaciones = "b" * (configuracion.LARGO_CONTEXTO_EMPRESA - 15) + "PROMO-DEL-FINAL"
    await configuracion.actualizar(base, {"contexto_empresa": indicaciones})

    resultado = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat()]
    )

    job = await base["jobs"].find_one({"_id": resultado.jobs[0]})
    assert job["payload"]["contexto_empresa"].endswith("PROMO-DEL-FINAL")
    assert len(job["payload"]["contexto_empresa"]) == configuracion.LARGO_CONTEXTO_EMPRESA
    validar_payload("REDACTAR", job["payload"])


@sin_mongo
async def test_un_contacto_con_mensaje_reciente_no_se_vuelve_a_redactar(base) -> None:
    """El anti-duplicado corre ANTES de pagar la redacción: un borrador de la
    corrida de la mañana bloquea al de la tarde — y en el barrido es lo que
    garantiza no recontactar dos veces al mismo cliente."""
    await abrir_destinos(base)
    await mensajes.crear_borrador(
        base,
        corrida_id=ObjectId(),
        maquina="pc-1",
        contacto_id="+5491123231151",
        contacto_nombre="Corralón San Justo",
        texto="Hola, ¿seguimos?",
        resumen_ultimo="preguntó por hierro del 8",
        quien_hablo_ultimo="contacto",
        antiguedad_dias=6,
    )

    resultado = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat()]
    )

    assert resultado.total == 0
    assert resultado.ya_contactados == 1


@sin_mongo
async def test_la_memoria_de_telefonos_evita_volver_al_navegador(base) -> None:
    """Lo que un RESOLVER averiguó una vez queda guardado: la próxima corrida
    que vea ese nombre sin número redacta directo, sin encolar otro RESOLVER."""
    await abrir_destinos(base)
    primera = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat(telefono=None)]
    )
    job = await base["jobs"].find_one({"_id": primera.resolver_job})
    await generacion.encolar_redacciones_resueltas(
        base,
        job=job,
        contactos=[{"nombre": "Corralón San Justo", "telefono": "+54 9 11 2323-1151"}],
    )

    segunda = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[chat(telefono=None)]
    )

    assert segunda.desde_cache == 1
    assert segunda.resolver_job is None
    assert segunda.total == 1


@sin_mongo
async def test_el_barrido_ignora_la_ventana_de_antiguedad(base) -> None:
    """El barrido ES su propia estrategia: un chat de hace un año entra aunque
    la ventana del modo recientes diga 30 días."""
    await abrir_destinos(base)
    await configuracion.actualizar(base, {"antiguedad_min_dias": 0, "antiguedad_max_dias": 30})
    viejo = chat(antiguedad_dias=300)

    recientes = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[viejo]
    )
    assert recientes.fuera_de_antiguedad == 1

    barrido = await generacion.encolar_redacciones(
        base, corrida_id=ObjectId(), maquina="pc-1", chats=[viejo], estrategia="barrido"
    )
    assert barrido.total == 1
