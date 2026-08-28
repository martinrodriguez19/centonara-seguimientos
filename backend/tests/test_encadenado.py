"""Tests del encadenado automático de borradores (D36).

Cada `REDACTAR` que vuelve limpio se convierte al instante en su "dejar
borrador": guardrails por mensaje → EN_ESPERA → un ENVIAR en modo prueba,
espaciado detrás de los de su máquina. Lo que se prueba acá es la parte que
decidió el dueño y la que no se negocia:

- los guardrails son código y descartan igual que siempre (R3);
- una pausa NO descarta: el borrador espera a que alguien mire;
- el triage informa pero ya no retiene;
- dos carreras no encolan dos jobs.
"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from bson import ObjectId
from conftest import ar

from app.core import configuracion, corridas, mensajes, vendedores
from app.core.esquema import inicializar
from app.core.estados import Estado, Motivo

MIERCOLES = ar(19, 11, 0)

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


async def corrida_generando(base) -> ObjectId:
    corrida_id = ObjectId()
    await base["corridas"].insert_one(
        {
            "_id": corrida_id,
            "tipo": "generacion",
            "modo": "prueba",
            "estado": "generando",
            "maquinas": ["mac-rocio"],
            "creada_en": MIERCOLES,
        }
    )
    return corrida_id


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
# El camino limpio
# ---------------------------------------------------------------------------


@sin_mongo
async def test_una_redaccion_limpia_queda_encolada_para_dejar_borrador(base) -> None:
    corrida = await corrida_generando(base)
    mensaje_id = await borrador(base, corrida, 1)

    job_id = await corridas.encadenar_borrador(base, mensaje_id, quien="pc-1", ahora=MIERCOLES)

    assert job_id is not None
    assert await estado_de(base, mensaje_id) == Estado.EN_ESPERA

    job = await base["jobs"].find_one({"_id": job_id})
    assert job["tipo"] == "ENVIAR"
    assert job["payload"]["modo"] == "prueba", "el encadenado nunca envía de verdad"
    assert job["payload"]["mensaje_id"] == str(mensaje_id)
    assert job["maquina"] == "mac-rocio"


@sin_mongo
async def test_el_encadenado_pone_la_corrida_en_enviando_y_audita_una_vez(base) -> None:
    corrida = await corrida_generando(base)
    uno = await borrador(base, corrida, 1)
    dos = await borrador(base, corrida, 2)

    await corridas.encadenar_borrador(base, uno, quien="pc-1", ahora=MIERCOLES)
    await corridas.encadenar_borrador(base, dos, quien="pc-1", ahora=MIERCOLES)

    assert (await base["corridas"].find_one({"_id": corrida}))["estado"] == "enviando"
    eventos = await base["auditoria"].count_documents({"detalle.accion": "borradores_automaticos"})
    assert eventos == 1, "el arranque se audita una sola vez por corrida"


@sin_mongo
async def test_el_segundo_de_la_misma_maquina_sale_detras_del_primero(base) -> None:
    corrida = await corrida_generando(base)
    uno = await borrador(base, corrida, 1)
    dos = await borrador(base, corrida, 2)

    primero = await corridas.encadenar_borrador(base, uno, quien="pc-1", ahora=MIERCOLES)
    segundo = await corridas.encadenar_borrador(base, dos, quien="pc-1", ahora=MIERCOLES)

    job_uno = await base["jobs"].find_one({"_id": primero})
    job_dos = await base["jobs"].find_one({"_id": segundo})
    assert job_dos["disponible_desde"] > job_uno["disponible_desde"], "espaciado, no en ráfaga"


@sin_mongo
async def test_dejar_borradores_corre_tambien_de_noche(base) -> None:
    """D37: la ventana es del envío real. La generación puede terminar a las 23."""
    corrida = await corrida_generando(base)
    mensaje_id = await borrador(base, corrida, 1)

    de_noche = MIERCOLES.replace(hour=23)
    job_id = await corridas.encadenar_borrador(base, mensaje_id, quien="pc-1", ahora=de_noche)

    assert job_id is not None
    assert await estado_de(base, mensaje_id) == Estado.EN_ESPERA


# ---------------------------------------------------------------------------
# Los guardrails siguen siendo código (R3)
# ---------------------------------------------------------------------------


@sin_mongo
async def test_un_placeholder_descarta_y_no_encola(base) -> None:
    corrida = await corrida_generando(base)
    mensaje_id = await borrador(base, corrida, 1, texto="Hola {nombre}, ¿seguimos?")

    job_id = await corridas.encadenar_borrador(base, mensaje_id, quien="pc-1", ahora=MIERCOLES)

    assert job_id is None
    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == Estado.DESCARTADO
    assert documento["motivo"] == Motivo.RECHAZADO
    assert "G3_TEXTO_INVALIDO" in documento["senales"]
    assert await base["jobs"].count_documents({}) == 0


@sin_mongo
async def test_un_destino_no_permitido_descarta(base) -> None:
    await configuracion.actualizar(base, {"destinos_permitidos": ["+5491199999999"]})
    corrida = await corrida_generando(base)
    mensaje_id = await borrador(base, corrida, 1)

    assert await corridas.encadenar_borrador(base, mensaje_id, quien="pc-1") is None
    assert await estado_de(base, mensaje_id) == Estado.DESCARTADO


@sin_mongo
async def test_el_tope_por_corrida_sigue_valiendo(base) -> None:
    """G4: un LISTAR que trae mil chats no deja mil borradores en los chats."""
    await configuracion.actualizar(base, {"tope_por_corrida": 2})
    corrida = await corrida_generando(base)

    resultados = []
    for n in range(3):
        mensaje_id = await borrador(base, corrida, n)
        resultados.append(
            await corridas.encadenar_borrador(base, mensaje_id, quien="pc-1", ahora=MIERCOLES)
        )

    assert resultados[0] is not None
    assert resultados[1] is not None
    assert resultados[2] is None, "el tercero no cabe en la corrida"


@sin_mongo
async def test_el_anti_duplicado_no_deja_dos_borradores_al_mismo_contacto(base) -> None:
    """G5 por mensaje: si ya hay uno esperando o dejado, no se escribe otro."""
    corrida = await corrida_generando(base)
    uno = await borrador(base, corrida, 1)
    await corridas.encadenar_borrador(base, uno, quien="pc-1", ahora=MIERCOLES)

    otra = await corrida_generando(base)
    repetido = await borrador(base, otra, 1, texto="Otro texto para el mismo contacto")

    assert await corridas.encadenar_borrador(base, repetido, quien="pc-1", ahora=MIERCOLES) is None
    assert await estado_de(base, repetido) == Estado.DESCARTADO


# ---------------------------------------------------------------------------
# La pausa espera, no descarta
# ---------------------------------------------------------------------------


@sin_mongo
async def test_con_el_kill_switch_puesto_el_borrador_espera(base) -> None:
    """Descartar por una pausa tiraría una redacción pagada por un freno
    transitorio. Queda en BORRADOR: lo retoma "Revisar ahora", o vence (D3)."""
    await configuracion.pausar(base, pausado=True, quien="prueba")
    corrida = await corrida_generando(base)
    mensaje_id = await borrador(base, corrida, 1)

    job_id = await corridas.encadenar_borrador(base, mensaje_id, quien="pc-1", ahora=MIERCOLES)

    assert job_id is None
    assert await estado_de(base, mensaje_id) == Estado.BORRADOR
    assert await base["jobs"].count_documents({}) == 0


@sin_mongo
async def test_sin_consentimiento_el_borrador_espera(base) -> None:
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"}, {"$set": {"acepto_condiciones_en": None}}
    )
    corrida = await corrida_generando(base)
    mensaje_id = await borrador(base, corrida, 1)

    assert await corridas.encadenar_borrador(base, mensaje_id, quien="pc-1") is None
    assert await estado_de(base, mensaje_id) == Estado.BORRADOR


# ---------------------------------------------------------------------------
# El triage informa, ya no retiene (D36)
# ---------------------------------------------------------------------------


@sin_mongo
async def test_una_senal_de_triage_no_retiene_pero_queda_a_la_vista(base) -> None:
    corrida = await corrida_generando(base)
    mensaje_id = await borrador(base, corrida, 1, resumen_ultimo="puso un reclamo por la entrega")

    job_id = await corridas.encadenar_borrador(base, mensaje_id, quien="pc-1", ahora=MIERCOLES)

    assert job_id is not None, "el borrador se deja igual: la revisión es del vendedor"
    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == Estado.EN_ESPERA
    assert documento["senales"], "la señal quedó guardada como información"


@sin_mongo
async def test_un_nombre_repetido_en_la_corrida_se_senala(base) -> None:
    corrida = await corrida_generando(base)
    uno = await borrador(base, corrida, 1, contacto_nombre="Ferretería Sur")
    await corridas.encadenar_borrador(base, uno, quien="pc-1", ahora=MIERCOLES)

    dos = await borrador(base, corrida, 2, contacto_nombre="Ferretería Sur")
    await corridas.encadenar_borrador(base, dos, quien="pc-1", ahora=MIERCOLES)

    documento = await base["mensajes"].find_one({"_id": dos})
    assert documento["estado"] == Estado.EN_ESPERA
    assert any("IDENTIDAD" in s for s in documento["senales"])


# ---------------------------------------------------------------------------
# Carreras y estados ajenos
# ---------------------------------------------------------------------------


@sin_mongo
async def test_dos_encadenados_en_carrera_encolan_un_solo_job(base) -> None:
    """Dos reportes del mismo REDACTAR llegan a la vez: uno gana la transición
    condicional y el otro rebota sin encolar nada."""
    corrida = await corrida_generando(base)
    mensaje_id = await borrador(base, corrida, 1)

    resultados = await asyncio.gather(
        corridas.encadenar_borrador(base, mensaje_id, quien="pc-1", ahora=MIERCOLES),
        corridas.encadenar_borrador(base, mensaje_id, quien="pc-1", ahora=MIERCOLES),
    )

    encolados = [r for r in resultados if r is not None]
    assert len(encolados) == 1
    assert await base["jobs"].count_documents({"payload.mensaje_id": str(mensaje_id)}) == 1


@sin_mongo
async def test_un_mensaje_que_no_esta_en_borrador_no_se_toca(base) -> None:
    """`sin_contexto` ya está en RETENIDO: espera una persona, no un job."""
    corrida = await corrida_generando(base)
    mensaje_id = await borrador(base, corrida, 1, texto="")
    await mensajes.mover(base, mensaje_id, Estado.RETENIDO, senales=["SIN_CONTEXTO"])

    assert await corridas.encadenar_borrador(base, mensaje_id, quien="pc-1") is None
    assert await estado_de(base, mensaje_id) == Estado.RETENIDO
    assert await base["jobs"].count_documents({}) == 0
