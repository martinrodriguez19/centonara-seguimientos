"""La memoria de a quién no se le vuelve a escribir (D42).

Lo que se custodia: que el veto nazca solo del reporte, que venza, que la clave
sea el número cuando se vio y el nombre cuando no, y —lo que más importa— que
entre **primero** a la lista que el pase único obedece, aunque la lista se
trunque.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from bson import ObjectId

from app import db
from app.core import configuracion, pase_unico, vetados
from app.core.esquema import inicializar

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

AHORA = datetime(2026, 9, 9, 14, 0, tzinfo=UTC)
CONFIG = {"dias_veto_disconforme": 365, "dias_veto_ya_compro": 180}


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


def chat(nombre="Enojado SRL", telefono="+5491123231151", **cambios):
    base = {
        "contacto_nombre": nombre,
        "contacto_telefono": telefono,
        "ultimo_mensaje_resumen": "reclamó por la entrega",
        "cita": "no me manden mas nada",
    }
    base.update(cambios)
    return base


def test_la_clave_es_el_numero_si_se_vio() -> None:
    assert vetados.clave("Juan", "+54 9 11 2323-1151") == "+5491123231151"


def test_sin_numero_la_clave_es_el_nombre_y_nunca_se_deduce() -> None:
    assert vetados.clave("Juan Ferretería", None) == "nombre:Juan Ferretería"
    assert vetados.clave("Juan", "no es un número") == "nombre:Juan"


@sin_mongo
async def test_un_disconforme_queda_vetado_un_ano(base) -> None:
    registrado = await vetados.registrar(
        base,
        maquina="mac-rocio",
        chat=chat(),
        motivo="disconforme",
        corrida_id=ObjectId(),
        config=CONFIG,
        ahora=AHORA,
    )

    assert registrado is True
    fila = await base["vetados"].find_one({"maquina": "mac-rocio"})
    assert fila["clave"] == "+5491123231151"
    assert fila["nombre"] == "Enojado SRL"
    assert fila["motivo"] == "disconforme"
    assert fila["cita"] == "no me manden mas nada"
    assert fila["vence_en"] == AHORA + timedelta(days=365)


@sin_mongo
async def test_un_ya_compro_vence_antes(base) -> None:
    await vetados.registrar(
        base,
        maquina="mac-rocio",
        chat=chat(cita=None),
        motivo="ya_compro",
        corrida_id=ObjectId(),
        config=CONFIG,
        ahora=AHORA,
    )

    fila = await base["vetados"].find_one({"maquina": "mac-rocio"})
    assert fila["vence_en"] == AHORA + timedelta(days=180)
    #  Sin cita, la justificación es el resumen: algo tiene que quedar escrito.
    assert fila["cita"] == "reclamó por la entrega"


@sin_mongo
async def test_un_motivo_comun_no_veta(base) -> None:
    registrado = await vetados.registrar(
        base,
        maquina="mac-rocio",
        chat=chat(),
        motivo="campo_ocupado",
        corrida_id=ObjectId(),
        config=CONFIG,
        ahora=AHORA,
    )

    assert registrado is False
    assert await base["vetados"].count_documents({}) == 0


@sin_mongo
async def test_leer_el_mismo_chat_dos_veces_renueva_en_vez_de_apilar(base) -> None:
    for momento in (AHORA, AHORA + timedelta(days=30)):
        await vetados.registrar(
            base,
            maquina="mac-rocio",
            chat=chat(),
            motivo="disconforme",
            corrida_id=ObjectId(),
            config=CONFIG,
            ahora=momento,
        )

    assert await base["vetados"].count_documents({}) == 1
    fila = await base["vetados"].find_one({})
    assert fila["creado_en"] == AHORA
    assert fila["vence_en"] == AHORA + timedelta(days=395)


@sin_mongo
async def test_los_vigentes_son_de_esta_maquina_y_no_vencieron(base) -> None:
    await vetados.registrar(
        base,
        maquina="mac-rocio",
        chat=chat("Vigente"),
        motivo="disconforme",
        corrida_id=ObjectId(),
        config=CONFIG,
        ahora=AHORA,
    )
    await vetados.registrar(
        base,
        maquina="mac-rocio",
        chat=chat("Vencido", "+5491100000001"),
        motivo="ya_compro",
        corrida_id=ObjectId(),
        config={"dias_veto_ya_compro": 1},
        ahora=AHORA - timedelta(days=3),
    )
    await vetados.registrar(
        base,
        maquina="mac-sofia",
        chat=chat("De otra", "+5491100000002"),
        motivo="disconforme",
        corrida_id=ObjectId(),
        config=CONFIG,
        ahora=AHORA,
    )

    assert await vetados.vigentes(base, "mac-rocio", ahora=AHORA) == ["Vigente"]


@sin_mongo
async def test_levantar_saca_a_alguien_y_dice_si_existia(base) -> None:
    await vetados.registrar(
        base,
        maquina="mac-rocio",
        chat=chat(),
        motivo="disconforme",
        corrida_id=ObjectId(),
        config=CONFIG,
        ahora=AHORA,
    )
    (fila,) = await vetados.listar(base, maquina="mac-rocio")

    assert await vetados.levantar(base, ObjectId(fila["id"]), quien="panel") is True
    assert await vetados.levantar(base, ObjectId(fila["id"]), quien="panel") is False
    assert await vetados.vigentes(base, "mac-rocio", ahora=AHORA) == []


# ---------------------------------------------------------------------------
# Lo que importa: la lista que el pase único obedece
# ---------------------------------------------------------------------------


@sin_mongo
async def test_los_vetados_van_primeros_en_no_escribir_aunque_se_trunque(base) -> None:
    """Con 150 contactos tocados en la ventana, el vetado sigue en la lista."""
    from app.core import mensajes
    from app.core.estados import Estado

    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    await vetados.registrar(
        base,
        maquina="mac-rocio",
        chat=chat("Zeta Enojado"),
        motivo="disconforme",
        corrida_id=ObjectId(),
        config=CONFIG,
        ahora=AHORA - timedelta(days=100),
    )
    corrida_id = ObjectId()
    for i in range(150):
        mensaje_id = await mensajes.crear_borrador(
            base,
            corrida_id=corrida_id,
            maquina="mac-rocio",
            contacto_id=f"+54911{i:08d}",
            contacto_nombre=f"Reciente {i:03d}",
            texto="Hola, seguimos?",
            ahora=AHORA - timedelta(hours=i),
        )
        await mensajes.mover(base, mensaje_id, Estado.BORRADOR_DEJADO, quien="mac-rocio")

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["no_escribir"][0] == "Zeta Enojado"
    assert len(payload["no_escribir"]) == pase_unico.MAX_NO_ESCRIBIR
    assert "Reciente 000" in payload["no_escribir"], "los más recientes siguen entrando"


@sin_mongo
async def test_el_reporte_de_una_tanda_alimenta_la_memoria(base) -> None:
    """Un disconforme salteado y un post-venta dejado: los dos quedan vetados."""
    from app.core import vendedores

    await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()
    job = {
        "_id": ObjectId(),
        "tipo": "BORRADORES",
        "maquina": "mac-rocio",
        "corrida_id": corrida_id,
        "payload": {"n_chats": 6, "run_id": str(corrida_id), "ya_vistos": []},
        "estado": "listo",
    }
    visitados = [
        {
            "contacto_nombre": "Enojado",
            "contacto_telefono": None,
            "ultimo_mensaje_resumen": "reclamó",
            "quien_hablo_ultimo": "contacto",
            "antiguedad_dias": 30,
            "borrador_dejado": False,
            "texto_borrador": "",
            "motivo": "disconforme",
        },
        {
            "contacto_nombre": "Ya compró",
            "contacto_telefono": "+5491123231151",
            "ultimo_mensaje_resumen": "ya compró",
            "quien_hablo_ultimo": "contacto",
            "antiguedad_dias": 30,
            "borrador_dejado": True,
            "texto_borrador": "Hola, vi que lo compraste. Te falto algo?",
            "motivo": "ya_compro",
        },
        {
            "contacto_nombre": "Normal",
            "contacto_telefono": None,
            "ultimo_mensaje_resumen": "pidió precio",
            "quien_hablo_ultimo": "contacto",
            "antiguedad_dias": 30,
            "borrador_dejado": True,
            "texto_borrador": "Hola, seguis con lo del precio?",
            "motivo": None,
        },
    ]

    procesado = await pase_unico.procesar_reporte(
        base, job=job, detalle={"chats": visitados, "fin_de_ventana": True}, ahora=AHORA
    )

    assert procesado.vetados == 2
    assert len(procesado.registrados) == 2
    assert sorted(await vetados.vigentes(base, "mac-rocio", ahora=AHORA)) == [
        "Enojado",
        "Ya compró",
    ]
    fila = await base["vetados"].find_one({"nombre": "Ya compró"})
    assert fila["clave"] == "+5491123231151"
