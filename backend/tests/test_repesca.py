"""La repesca (D61): revisar el día y completar lo que faltó.

Lo que se custodia: que cada máquina quede en el resultado correcto, que sólo
las que tienen algo que completar entren a la corrida, que salga una vez por
día a su hora, y que espere —sin perder el día— si hay una corrida en curso.
Las horas están en hora argentina (`ar`), como las ve el dueño.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import ar

from app import db
from app.core import alertas, cola, configuracion, corridas, programacion, repesca, vendedores
from app.core.esquema import inicializar

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

# El 02/10/2026 es viernes.
DIA = 2
MES = 10


def a_las(hora: int, minuto: int = 0) -> datetime:
    return ar(DIA, hora, minuto, mes=MES)


TARDE = a_las(17, 30)
REPESCA = a_las(21, 0)


@pytest.fixture
async def base(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    db_prueba = cliente[nombre]
    await inicializar(db_prueba)
    monkeypatch.setattr(db, "obtener_base", lambda: db_prueba)
    await configuracion.actualizar(
        db_prueba,
        {
            "repesca": {"activa": True, "hora": "21:00", "dias": [1, 2, 3, 4, 5, 6]},
            "modo_borrador": "extension",
            "tope_diario_borradores": 20,
        },
    )
    try:
        yield db_prueba
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


async def maquina(base, nombre: str, *, latido: datetime | None = REPESCA, **extra) -> None:
    await vendedores.dar_de_alta(base, maquina=nombre, nombre=nombre.title())
    await base["vendedores"].update_one(
        {"maquina": nombre},
        {
            "$set": {
                "activo": True,
                "acepto_condiciones_en": TARDE,
                "ultimo_latido": latido,
                **extra,
            }
        },
    )


async def dejo(base, nombre: str, cuantos: int, *, cuando: datetime = TARDE) -> None:
    for i in range(cuantos):
        await base["mensajes"].insert_one(
            {
                "maquina": nombre,
                "estado": "BORRADOR_DEJADO",
                "texto": f"seguimiento {i}",
                "clave_idempotencia": uuid4().hex,
                "creado_en": cuando,
            }
        )


async def corrida_de_la_tarde(base, tandas: list[dict]) -> None:
    """Una corrida de hoy, ya terminada, con las tandas que dejó."""
    await base["corridas"].insert_one(
        {
            "tipo": "generacion",
            "modo": "prueba",
            "estado": "terminada",
            "maquinas": [t["maquina"] for t in tandas],
            "creada_en": a_las(17, 0),
            "tandas": tandas,
        }
    )


def por_maquina(resumen: list[dict]) -> dict[str, str]:
    return {r["maquina"]: r["resultado"] for r in resumen}


# ---------------------------------------------------------------------------
# El resumen del día
# ---------------------------------------------------------------------------


@sin_mongo
async def test_cada_maquina_queda_en_su_resultado(base) -> None:
    await maquina(base, "pc-completa")
    await dejo(base, "pc-completa", 20)
    await maquina(base, "pc-sin-chats")
    await dejo(base, "pc-sin-chats", 7)
    await maquina(base, "pc-sin-cuota", pausa_cuota_hasta=REPESCA + timedelta(hours=1))
    await maquina(base, "pc-pausada", pausado_hasta=REPESCA + timedelta(hours=1))
    await maquina(base, "pc-apagada", latido=REPESCA - timedelta(hours=3))
    await maquina(base, "pc-corta")
    await dejo(base, "pc-corta", 14)
    await maquina(base, "pc-de-baja")
    await base["vendedores"].update_one({"maquina": "pc-de-baja"}, {"$set": {"activo": False}})
    await corrida_de_la_tarde(
        base,
        [
            {"maquina": "pc-sin-chats", "fin": "tanda_vacia"},
            {"maquina": "pc-corta", "fin": "tanda_fallida"},
        ],
    )

    config = await configuracion.obtener(base)
    resumen = await repesca.resumen_del_dia(base, config, REPESCA)

    assert por_maquina(resumen) == {
        "pc-apagada": "ausente",
        "pc-completa": "completa",
        "pc-corta": "repescada",
        "pc-pausada": "pausada",
        "pc-sin-chats": "sin_chats",
        "pc-sin-cuota": "sin_cuota",
    }
    corta = next(r for r in resumen if r["maquina"] == "pc-corta")
    assert (corta["dejados"], corta["tope"]) == (14, 20)


@sin_mongo
async def test_lo_de_ayer_no_cuenta_para_hoy(base) -> None:
    await maquina(base, "pc-1")
    await dejo(base, "pc-1", 20, cuando=TARDE - timedelta(days=1))
    config = await configuracion.obtener(base)
    assert por_maquina(await repesca.resumen_del_dia(base, config, REPESCA)) == {
        "pc-1": "repescada"
    }


@sin_mongo
async def test_completa_manda_sobre_la_ultima_tanda(base) -> None:
    await maquina(base, "pc-1")
    await dejo(base, "pc-1", 20)
    await corrida_de_la_tarde(base, [{"maquina": "pc-1", "fin": "tanda_fallida"}])
    config = await configuracion.obtener(base)
    assert por_maquina(await repesca.resumen_del_dia(base, config, REPESCA)) == {"pc-1": "completa"}


# ---------------------------------------------------------------------------
# El disparo
# ---------------------------------------------------------------------------


@sin_mongo
async def test_a_la_hora_larga_una_corrida_solo_para_las_que_faltan(base) -> None:
    await maquina(base, "pc-completa")
    await dejo(base, "pc-completa", 20)
    await maquina(base, "pc-corta")
    await dejo(base, "pc-corta", 14)

    assert await repesca.revisar(base, ahora=REPESCA) == "disparada"

    corrida = await base["corridas"].find_one({"motivo": "repesca"})
    assert corrida["maquinas"] == ["pc-corta"]
    assert corrida["disparada_por"] == "repesca"
    assert por_maquina(corrida["revision_del_dia"]) == {
        "pc-completa": "completa",
        "pc-corta": "repescada",
    }
    assert [j["maquina"] for j in await base["jobs"].find().to_list(None)] == ["pc-corta"]

    evento = await base["auditoria"].find_one({"que": "repesca_revisada"})
    assert evento["corrida_id"] == corrida["_id"]
    assert evento["detalle"]["sin_disparo"] is None


@sin_mongo
async def test_una_sola_vez_por_dia(base) -> None:
    await maquina(base, "pc-corta")
    assert await repesca.revisar(base, ahora=REPESCA) == "disparada"
    for job in await base["jobs"].find().to_list(None):
        await cola.reportar(base, job["_id"], ok=True)
    assert await repesca.revisar(base, ahora=REPESCA + timedelta(minutes=5)) is None
    assert await base["corridas"].count_documents({"motivo": "repesca"}) == 1


@sin_mongo
async def test_fuera_de_hora_o_apagada_no_hace_nada(base) -> None:
    await maquina(base, "pc-corta")
    assert await repesca.revisar(base, ahora=a_las(20, 55)) is None
    assert await repesca.revisar(base, ahora=a_las(23, 5)) is None

    await configuracion.actualizar(
        base, {"repesca": {"activa": False, "hora": "21:00", "dias": [1, 2, 3, 4, 5, 6]}}
    )
    assert await repesca.revisar(base, ahora=REPESCA) is None
    assert await base["corridas"].count_documents({}) == 0


@sin_mongo
async def test_el_domingo_no_corre(base) -> None:
    await maquina(base, "pc-corta")
    domingo = ar(4, 21, 0, mes=MES)
    assert await repesca.revisar(base, ahora=domingo) is None


@sin_mongo
async def test_si_todas_completaron_revisa_y_no_larga_nada(base) -> None:
    await maquina(base, "pc-1")
    await dejo(base, "pc-1", 20)

    assert await repesca.revisar(base, ahora=REPESCA) == "completo"

    assert await base["corridas"].count_documents({}) == 0
    evento = await base["auditoria"].find_one({"que": "repesca_revisada"})
    assert evento["detalle"]["sin_disparo"] == "completo"


@sin_mongo
async def test_en_el_circuito_viejo_revisa_pero_no_larga(base) -> None:
    await configuracion.actualizar(base, {"modo_borrador": "playwright"})
    await maquina(base, "pc-corta")

    assert await repesca.revisar(base, ahora=REPESCA) == "revisada:circuito_viejo"
    assert await base["corridas"].count_documents({}) == 0


@sin_mongo
async def test_con_pausa_global_revisa_pero_no_larga(base) -> None:
    await configuracion.pausar(base, pausado=True, quien="panel")
    await maquina(base, "pc-corta")
    assert await repesca.revisar(base, ahora=REPESCA) == "revisada:pausa_global"


@sin_mongo
async def test_con_una_corrida_en_curso_espera_sin_perder_el_dia(base) -> None:
    await maquina(base, "pc-corta", latido=a_las(17, 0))
    await corridas.disparar(base, quien="panel", ahora=a_las(17, 0))

    #  A las 21 sigue en curso: espera, no consume el día.
    assert await repesca.revisar(base, ahora=REPESCA) is None
    assert await base["auditoria"].count_documents({"que": "repesca_revisada"}) == 0

    #  Termina a las 21:20, y la vuelta siguiente repesca.
    for job in await base["jobs"].find().to_list(None):
        await cola.reportar(base, job["_id"], ok=True)
    await base["vendedores"].update_one(
        {"maquina": "pc-corta"}, {"$set": {"ultimo_latido": a_las(21, 24)}}
    )
    assert await repesca.revisar(base, ahora=a_las(21, 25)) == "disparada"


@sin_mongo
async def test_si_la_corrida_no_termina_en_la_gracia_queda_salteada(base) -> None:
    await maquina(base, "pc-corta", latido=a_las(17, 0))
    await corridas.disparar(base, quien="panel", ahora=a_las(17, 0))

    casi_al_final = REPESCA + timedelta(hours=programacion.HORAS_DE_GRACIA, minutes=-5)
    assert await repesca.revisar(base, ahora=casi_al_final) == "salteada:corrida_en_curso"
    evento = await base["auditoria"].find_one({"que": "corrida_programada_salteada"})
    assert evento["quien"] == "repesca"


@sin_mongo
async def test_su_marca_no_pisa_la_de_la_corrida_programada(base) -> None:
    await configuracion.actualizar(
        base, {"programacion": {"activa": True, "hora": "21:00", "dias": [1, 2, 3, 4, 5, 6, 7]}}
    )
    await maquina(base, "pc-corta")
    assert await programacion.revisar(base, ahora=REPESCA) == "disparada"
    for job in await base["jobs"].find().to_list(None):
        await cola.reportar(base, job["_id"], ok=True)
    #  La corrida de las 21 ya tomó su día; la repesca tiene el suyo.
    assert await repesca.revisar(base, ahora=REPESCA + timedelta(minutes=5)) == "disparada"


# ---------------------------------------------------------------------------
# Lo que ve el panel
# ---------------------------------------------------------------------------


@sin_mongo
async def test_la_revision_de_hoy_queda_para_el_inicio(base) -> None:
    await maquina(base, "pc-1")
    await dejo(base, "pc-1", 20)
    assert await repesca.ultima_revision(base, ahora=REPESCA) is None

    await repesca.revisar(base, ahora=REPESCA)

    revision = await repesca.ultima_revision(base, ahora=REPESCA + timedelta(minutes=1))
    assert revision["sin_disparo"] == "completo"
    assert por_maquina(revision["maquinas"]) == {"pc-1": "completa"}
    #  Al día siguiente ya no es "la de hoy".
    assert await repesca.ultima_revision(base, ahora=REPESCA + timedelta(days=1)) is None


@sin_mongo
async def test_si_despues_de_la_repesca_sigue_corta_avisa(base) -> None:
    await maquina(base, "pc-corta")
    await dejo(base, "pc-corta", 14)
    await repesca.revisar(base, ahora=REPESCA)
    corrida = await base["corridas"].find_one({"motivo": "repesca"})
    for job in await base["jobs"].find().to_list(None):
        await cola.reportar(base, job["_id"], ok=True)
    await base["corridas"].update_one(
        {"_id": corrida["_id"]},
        {"$set": {"tandas": [{"maquina": "pc-corta", "fin": "tanda_fallida"}]}},
    )

    hay = await alertas.revisar(base, ahora=REPESCA + timedelta(minutes=40))
    [aviso] = [a for a in hay if a.codigo == "repesca_incompleta"]
    assert aviso.maquina == "pc-corta"
    assert aviso.nivel is alertas.Nivel.AVISO


@sin_mongo
async def test_si_despues_de_la_repesca_no_quedaban_chats_no_avisa(base) -> None:
    await maquina(base, "pc-corta")
    await dejo(base, "pc-corta", 14)
    await repesca.revisar(base, ahora=REPESCA)
    corrida = await base["corridas"].find_one({"motivo": "repesca"})
    for job in await base["jobs"].find().to_list(None):
        await cola.reportar(base, job["_id"], ok=True)
    await base["corridas"].update_one(
        {"_id": corrida["_id"]},
        {"$set": {"tandas": [{"maquina": "pc-corta", "fin": "tanda_vacia"}]}},
    )

    hay = await alertas.revisar(base, ahora=REPESCA + timedelta(minutes=40))
    assert not [a for a in hay if a.codigo == "repesca_incompleta"]


def test_proxima_repesca_respeta_los_dias() -> None:
    programa = {"activa": True, "hora": "21:00", "dias": [1, 2, 3, 4, 5, 6]}
    #  Sábado 03/10 a las 22: la próxima es el lunes 05/10, no el domingo.
    proxima = programacion.proxima(programa, ahora=ar(3, 22, 0, mes=MES))
    assert proxima == ar(5, 21, 0, mes=MES).astimezone(UTC)
