"""La corrida programada (D51): que salga a la hora, una vez, y que no salga cuando no debe.

Lo que se custodia es la aritmética del "cuándo": el loop de mantenimiento
pregunta cada cinco minutos, y de todas esas preguntas exactamente una tiene
que disparar por día. Las horas de los tests están escritas en hora argentina
(`ar`), que es la que ve el dueño en el panel.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from conftest import ar

from app import db
from app.core import auditoria, configuracion, corridas, programacion, vendedores
from app.core.esquema import inicializar

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

# El 16/09/2026 es miércoles.
DIA = 16
MES = 9


def a_las(hora: int, minuto: int = 0, *, dia: int = DIA) -> datetime:
    return ar(dia, hora, minuto, mes=MES)


@pytest.fixture
async def base(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    db_prueba = cliente[nombre]
    await inicializar(db_prueba)
    monkeypatch.setattr(db, "obtener_base", lambda: db_prueba)
    await vendedores.dar_de_alta(db_prueba, maquina="mac-rocio", nombre="Rocío")
    await db_prueba["vendedores"].update_one(
        {"maquina": "mac-rocio"},
        {"$set": {"activo": True, "acepto_condiciones_en": datetime.now(UTC)}},
    )
    await configuracion.actualizar(
        db_prueba,
        {"programacion": {"activa": True, "hora": "17:00", "dias": [1, 2, 3, 4, 5, 6, 7]}},
    )
    try:
        yield db_prueba
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


async def corridas_creadas(base) -> list[dict]:
    return await base["corridas"].find({}).to_list(None)


async def terminar_todo(base) -> None:
    """Una corrida está en curso mientras tenga jobs pendientes: se cierran."""
    await base["jobs"].update_many(
        {}, {"$set": {"estado": "listo", "terminado_en": datetime.now(UTC)}}
    )


async def salteadas(base) -> list[dict]:
    return (
        await base["auditoria"]
        .find({"que": str(auditoria.Que.CORRIDA_PROGRAMADA_SALTEADA)})
        .to_list(None)
    )


# ---------------------------------------------------------------------------
# Dispara
# ---------------------------------------------------------------------------


@sin_mongo
async def test_a_la_hora_dispara_una_corrida_de_generacion(base) -> None:
    assert await programacion.revisar(base, ahora=a_las(17, 0)) == "disparada"

    creadas = await corridas_creadas(base)
    assert len(creadas) == 1
    assert creadas[0]["disparada_por"] == "programacion"
    assert creadas[0]["tipo"] == str(corridas.TipoCorrida.GENERACION)


@sin_mongo
async def test_el_loop_llega_unos_minutos_tarde_y_dispara_igual(base) -> None:
    """El mantenimiento pregunta cada cinco minutos: 17:04 es "a las 17"."""
    assert await programacion.revisar(base, ahora=a_las(17, 4)) == "disparada"


@sin_mongo
async def test_un_backend_que_estaba_caido_a_las_17_dispara_al_volver(base) -> None:
    assert await programacion.revisar(base, ahora=a_las(18, 30)) == "disparada"


# ---------------------------------------------------------------------------
# No dispara
# ---------------------------------------------------------------------------


@sin_mongo
async def test_antes_de_la_hora_no_pasa_nada(base) -> None:
    assert await programacion.revisar(base, ahora=a_las(16, 59)) is None
    assert await corridas_creadas(base) == []


@sin_mongo
async def test_pasada_la_gracia_ya_no_arranca(base) -> None:
    """A las 19:01 la corrida sería de la noche: eso no es lo que se pidió."""
    assert await programacion.revisar(base, ahora=a_las(19, 1)) is None
    assert await corridas_creadas(base) == []


@sin_mongo
async def test_una_sola_vez_por_dia(base) -> None:
    """Cinco minutos después vuelve a preguntar, y la respuesta es que ya fue."""
    assert await programacion.revisar(base, ahora=a_las(17, 0)) == "disparada"
    #  La primera corrida sigue en curso; se termina para que no sea ése el motivo.
    await terminar_todo(base)
    assert await programacion.revisar(base, ahora=a_las(17, 5)) is None
    assert await programacion.revisar(base, ahora=a_las(18, 0)) is None
    assert len(await corridas_creadas(base)) == 1


@sin_mongo
async def test_al_dia_siguiente_vuelve_a_disparar(base) -> None:
    assert await programacion.revisar(base, ahora=a_las(17, 0)) == "disparada"
    await terminar_todo(base)
    assert await programacion.revisar(base, ahora=a_las(17, 0, dia=DIA + 1)) == "disparada"
    assert len(await corridas_creadas(base)) == 2


@sin_mongo
async def test_un_dia_apagado_no_dispara(base) -> None:
    """Sólo lunes a viernes; el 19/09/2026 es sábado."""
    await configuracion.actualizar(
        base, {"programacion": {"activa": True, "hora": "17:00", "dias": [1, 2, 3, 4, 5]}}
    )
    assert await programacion.revisar(base, ahora=a_las(17, 0, dia=19)) is None
    assert await corridas_creadas(base) == []


@sin_mongo
async def test_apagada_no_dispara_nunca(base) -> None:
    await configuracion.actualizar(
        base, {"programacion": {"activa": False, "hora": "17:00", "dias": [1, 2, 3, 4, 5, 6, 7]}}
    )
    assert await programacion.revisar(base, ahora=a_las(17, 0)) is None
    assert await corridas_creadas(base) == []


@sin_mongo
async def test_de_fabrica_viene_apagada(base) -> None:
    """El deploy no dispara nada: prenderla es un acto del panel."""
    assert configuracion.POR_DEFECTO["programacion"]["activa"] is False


# ---------------------------------------------------------------------------
# Salteada: era la hora y no se pudo, y queda dicho por qué
# ---------------------------------------------------------------------------


@sin_mongo
async def test_con_pausa_global_se_saltea_y_queda_auditado(base) -> None:
    await configuracion.pausar(base, pausado=True, quien="panel")

    assert await programacion.revisar(base, ahora=a_las(17, 0)) == "salteada:pausa_global"
    assert await corridas_creadas(base) == []
    eventos = await salteadas(base)
    assert len(eventos) == 1
    assert eventos[0]["detalle"]["motivo"] == "pausa_global"
    #  Y el día quedó consumido: soltar la pausa a las 17:10 no dispara solo.
    await configuracion.pausar(base, pausado=False, quien="panel")
    assert await programacion.revisar(base, ahora=a_las(17, 10)) is None


@sin_mongo
async def test_con_una_corrida_en_curso_se_saltea_y_queda_auditado(base) -> None:
    await corridas.disparar(base, quien="dueño", tipo=corridas.TipoCorrida.GENERACION)

    assert await programacion.revisar(base, ahora=a_las(17, 0)) == "salteada:corrida_en_curso"
    assert len(await corridas_creadas(base)) == 1
    assert [e["detalle"]["motivo"] for e in await salteadas(base)] == ["corrida_en_curso"]


@sin_mongo
async def test_sin_maquinas_se_saltea_y_queda_auditado(base) -> None:
    await base["vendedores"].update_many({}, {"$set": {"activo": False}})

    assert await programacion.revisar(base, ahora=a_las(17, 0)) == "salteada:sin_maquinas"
    assert await corridas_creadas(base) == []
    assert [e["detalle"]["motivo"] for e in await salteadas(base)] == ["sin_maquinas"]
