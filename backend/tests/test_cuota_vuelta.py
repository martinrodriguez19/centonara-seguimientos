"""Cuando vuelve la cuota de Claude, se completa el día (D65.3).

Lo que se custodia: que la corrida salga una sola vez y sólo para las máquinas
que quedaron cortas, que espere si hay una corrida en curso, y que no salga de
noche ni cuando el día ya terminó. Las horas están en hora argentina (`ar`).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import ar

from app import db
from app.core import configuracion, corridas, cuota, vendedores
from app.core.esquema import inicializar

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

# El 02/10/2026 es viernes.
TARDE = ar(2, 17, 30, mes=10)
VUELVE = ar(2, 19, 0, mes=10)


@pytest.fixture
async def base(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    db_prueba = cliente[nombre]
    await inicializar(db_prueba)
    monkeypatch.setattr(db, "obtener_base", lambda: db_prueba)
    await configuracion.actualizar(
        db_prueba, {"modo_borrador": "extension", "tope_diario_borradores": 20}
    )
    try:
        yield db_prueba
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


async def maquina(base, nombre: str, *, dejados: int = 0) -> None:
    await vendedores.dar_de_alta(base, maquina=nombre, nombre=nombre.title())
    await base["vendedores"].update_one(
        {"maquina": nombre},
        {
            "$set": {
                "activo": True,
                "acepto_condiciones_en": TARDE,
                "ultimo_latido": VUELVE + timedelta(hours=1),
                "pausa_cuota_hasta": VUELVE,
            }
        },
    )
    for i in range(dejados):
        await base["mensajes"].insert_one(
            {
                "maquina": nombre,
                "estado": "BORRADOR_DEJADO",
                "texto": f"seguimiento {i}",
                "clave_idempotencia": uuid4().hex,
                "creado_en": TARDE,
            }
        )


async def sin_cuota_hasta(base, vuelve: datetime = VUELVE) -> None:
    await base["programacion"].update_one(
        {"_id": cuota.MARCA}, {"$set": {"vuelve_en": vuelve}}, upsert=True
    )


@sin_mongo
async def test_sin_pausa_registrada_no_hace_nada(base) -> None:
    assert await cuota.revisar_vuelta(base, ahora=VUELVE) is None


@sin_mongo
async def test_mientras_dura_la_pausa_no_hace_nada(base) -> None:
    await maquina(base, "pc-1")
    await sin_cuota_hasta(base)

    assert await cuota.revisar_vuelta(base, ahora=VUELVE - timedelta(minutes=5)) is None
    assert await base["corridas"].count_documents({}) == 0


@sin_mongo
async def test_al_volver_corre_solo_para_las_que_quedaron_cortas(base) -> None:
    await maquina(base, "pc-corta", dejados=6)
    await maquina(base, "pc-completa", dejados=20)
    await sin_cuota_hasta(base)
    ahora = VUELVE + timedelta(minutes=3)

    assert await cuota.revisar_vuelta(base, ahora=ahora) == "disparada"

    [corrida] = await base["corridas"].find({}).to_list(None)
    assert corrida["maquinas"] == ["pc-corta"]
    assert corrida["motivo"] == "cuota"
    evento = await base["auditoria"].find_one({"que": "cuota_retomada"})
    assert evento["corrida_id"] == corrida["_id"]
    #  Una vez por día: la vuelta siguiente del mantenimiento no repite.
    assert await cuota.revisar_vuelta(base, ahora=ahora + timedelta(minutes=5)) is None
    assert await base["corridas"].count_documents({}) == 1


@sin_mongo
async def test_si_todas_completaron_no_larga_nada(base) -> None:
    await maquina(base, "pc-1", dejados=20)
    await sin_cuota_hasta(base)

    assert await cuota.revisar_vuelta(base, ahora=VUELVE + timedelta(minutes=3)) == "completo"
    assert await base["corridas"].count_documents({}) == 0


@sin_mongo
async def test_con_una_corrida_en_curso_espera_y_despues_la_saltea(base) -> None:
    await maquina(base, "pc-1")
    await sin_cuota_hasta(base)
    await base["corridas"].insert_one(
        {
            "tipo": "generacion",
            "modo": "prueba",
            "estado": "en_curso",
            "maquinas": ["otra"],
            "creada_en": VUELVE,
        }
    )
    #  Para que `en_curso` no la cierre por falta de latido.
    await base["jobs"].insert_one(
        {"corrida_id": (await base["corridas"].find_one())["_id"], "estado": "pendiente"}
    )

    assert await cuota.revisar_vuelta(base, ahora=VUELVE + timedelta(minutes=30)) is None
    assert await cuota.revisar_vuelta(base, ahora=VUELVE + timedelta(hours=3)) == (
        "salteada:corrida_en_curso"
    )


@sin_mongo
async def test_si_vuelve_de_noche_queda_salteada(base) -> None:
    await configuracion.actualizar(
        base,
        {
            "descanso": {
                "activa": True,
                "desde": "22:00",
                "hasta": "08:00",
                "dias": [1, 2, 3, 4, 5, 6],
                "dia_libre": [7],
                "suspender": True,
            }
        },
    )
    await maquina(base, "pc-1")
    noche = ar(2, 22, 40, mes=10)
    await sin_cuota_hasta(base, noche)

    assert await cuota.revisar_vuelta(base, ahora=noche + timedelta(minutes=2)) == (
        "salteada:descanso"
    )
    assert await base["corridas"].count_documents({}) == 0
    evento = await base["auditoria"].find_one({"que": "corrida_programada_salteada"})
    assert evento["quien"] == "cuota"


@sin_mongo
async def test_una_pausa_de_ayer_no_corre_hoy(base) -> None:
    await maquina(base, "pc-1")
    await sin_cuota_hasta(base)

    al_otro_dia = VUELVE + timedelta(days=1)
    assert await cuota.revisar_vuelta(base, ahora=al_otro_dia) == "salteada:dia_terminado"
    assert await base["corridas"].count_documents({}) == 0


@sin_mongo
async def test_dos_avisos_se_quedan_con_la_hora_mas_tarde(base) -> None:
    await maquina(base, "pc-1")
    temprano = datetime.now(UTC) + timedelta(hours=1)
    tarde = datetime.now(UTC) + timedelta(hours=3)

    await cuota.registrar(base, maquina="pc-1", detalle={"reinicia_en": tarde.isoformat()})
    await cuota.registrar(base, maquina="pc-1", detalle={"reinicia_en": temprano.isoformat()})

    marca = await base["programacion"].find_one({"_id": cuota.MARCA})
    assert abs(marca["vuelve_en"] - (tarde + cuota.MARGEN_REINICIO)) < timedelta(seconds=1)


@sin_mongo
async def test_la_corrida_de_la_vuelta_respeta_la_pausa_global(base) -> None:
    await maquina(base, "pc-1")
    await sin_cuota_hasta(base)
    await configuracion.pausar(base, pausado=True, quien="panel")

    resultado = await cuota.revisar_vuelta(base, ahora=VUELVE + timedelta(minutes=3))

    assert resultado == "revisada:pausa_global"
    assert await corridas.en_curso(base) is None
