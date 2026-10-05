"""El descanso (D64): cuándo descansan las máquinas, hasta cuándo, y qué hace el sistema.

Las horas están en hora argentina (`ar`). El 02/10/2026 es viernes; el 04/10,
domingo; el 05/10, lunes.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from conftest import ar
from httpx import ASGITransport, AsyncClient

from app import db
from app.config import obtener_configuracion
from app.core import alertas, configuracion, corridas, horarios, programacion, vendedores
from app.core.esquema import inicializar
from app.main import app

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

MES = 10
DE_FABRICA = {
    "descanso": {
        "activa": True,
        "desde": "00:00",
        "hasta": "08:00",
        "dias": [1, 2, 3, 4, 5, 6],
        "dia_libre": [7],
        "suspender": True,
    }
}


def a_las(dia: int, hora: int, minuto: int = 0) -> datetime:
    return ar(dia, hora, minuto, mes=MES)


# ---------------------------------------------------------------------------
# Cuándo — puro
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("dia", "hora", "minuto", "descansa"),
    [
        (2, 3, 0, True),  # viernes de madrugada
        (2, 9, 0, False),  # viernes de día
        (3, 3, 0, True),  # sábado de madrugada
        (3, 23, 59, False),  # sábado a la noche: todavía no
        (4, 0, 0, True),  # domingo: libre
        (4, 15, 0, True),
        (5, 7, 59, True),  # lunes antes de las 8
        (5, 8, 0, False),
    ],
)
def test_cuando_se_descansa(dia: int, hora: int, minuto: int, descansa: bool) -> None:
    assert horarios.en_descanso(DE_FABRICA, a_las(dia, hora, minuto)) is descansa


def test_apagado_nunca_se_descansa() -> None:
    config = {"descanso": {**DE_FABRICA["descanso"], "activa": False}}
    assert not horarios.en_descanso(config, a_las(4, 15))
    assert horarios.ultimo_fin_de_descanso(config, a_las(5, 10)) is None


def test_una_noche_que_cruza_la_medianoche() -> None:
    config = {
        "descanso": {
            "activa": True,
            "desde": "23:00",
            "hasta": "07:00",
            "dias": [1, 2, 3, 4, 5],
            "dia_libre": [],
        }
    }
    assert horarios.en_descanso(config, a_las(5, 23, 30))  # lunes 23:30
    assert horarios.en_descanso(config, a_las(6, 6, 0))  # martes 06:00
    assert horarios.en_descanso(config, a_las(3, 6, 0))  # sábado 06:00: viene del viernes
    assert not horarios.en_descanso(config, a_las(3, 23, 30))  # sábado no es noche de descanso
    assert horarios.descanso_hasta(config, a_las(5, 23, 30)) == a_las(6, 7, 0)


def test_hasta_cuando_dura() -> None:
    assert horarios.descanso_hasta(DE_FABRICA, a_las(2, 3)) == a_las(2, 8)
    #  El domingo empalma con la noche del lunes: un solo descanso largo.
    assert horarios.descanso_hasta(DE_FABRICA, a_las(4, 0)) == a_las(5, 8)
    assert horarios.descanso_hasta(DE_FABRICA, a_las(4, 15)) == a_las(5, 8)
    assert horarios.descanso_hasta(DE_FABRICA, a_las(2, 12)) is None


def test_cuando_termino_el_ultimo() -> None:
    assert horarios.ultimo_fin_de_descanso(DE_FABRICA, a_las(2, 10)) == a_las(2, 8)
    assert horarios.ultimo_fin_de_descanso(DE_FABRICA, a_las(5, 9)) == a_las(5, 8)
    assert horarios.ultimo_fin_de_descanso(DE_FABRICA, a_las(3, 23)) == a_las(3, 8)
    assert horarios.ultimo_fin_de_descanso(DE_FABRICA, a_las(4, 12)) is None


def test_cuando_empezo() -> None:
    assert horarios.inicio_del_descanso(DE_FABRICA, a_las(2, 8)) == a_las(2, 0)
    #  El del fin de semana empieza el domingo a la medianoche.
    assert horarios.inicio_del_descanso(DE_FABRICA, a_las(5, 8)) == a_las(4, 0)


def test_dormida_es_la_que_se_callo_durante_el_descanso() -> None:
    ahora = a_las(2, 10)
    assert horarios.dormida_desde_el_descanso(DE_FABRICA, a_las(2, 0, 1), ahora)
    assert horarios.dormida_desde_el_descanso(DE_FABRICA, a_las(1, 23, 55), ahora)
    #  Callada desde antes del descanso: caída, no dormida.
    assert not horarios.dormida_desde_el_descanso(DE_FABRICA, a_las(1, 18), ahora)
    #  Ya la despertaron.
    assert not horarios.dormida_desde_el_descanso(DE_FABRICA, a_las(2, 9), ahora)
    assert not horarios.dormida_desde_el_descanso(DE_FABRICA, None, ahora)


def test_de_noche_no_se_actualiza_ni_con_el_horario_apagado() -> None:
    assert not horarios.toca_actualizar(DE_FABRICA, a_las(2, 3))
    assert horarios.toca_actualizar(DE_FABRICA, a_las(2, 12))


def test_el_agente_recibe_el_descanso() -> None:
    para = horarios.para_agente(DE_FABRICA, a_las(4, 15))
    assert para["descanso_hasta"] == a_las(5, 8).isoformat()
    assert para["suspender"] is True
    assert "despertar" not in para
    assert horarios.para_agente(DE_FABRICA, a_las(2, 12))["descanso_hasta"] is None


# ---------------------------------------------------------------------------
# Lo que hace el sistema
# ---------------------------------------------------------------------------


@pytest.fixture
async def base(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    db_prueba = cliente[nombre]
    await inicializar(db_prueba)
    monkeypatch.setattr(db, "obtener_base", lambda: db_prueba)
    await configuracion.actualizar(db_prueba, DE_FABRICA)
    try:
        yield db_prueba
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


@pytest.fixture
async def http():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://prueba") as cliente:
        yield cliente


def a_la_hora(monkeypatch, momento: datetime) -> None:
    import app.api.agente as api_agente

    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return momento if tz is None else momento.astimezone(tz)

    monkeypatch.setattr(api_agente, "datetime", Reloj)


async def maquina(base, *, latido: datetime | None = None) -> dict[str, str]:
    alta = await vendedores.dar_de_alta(base, maquina="pc-1", nombre="Prueba")
    await base["vendedores"].update_one(
        {"maquina": "pc-1"}, {"$set": {"activo": True, "ultimo_latido": latido}}
    )
    return {"Authorization": f"Bearer {alta.token}"}


@sin_mongo
async def test_de_noche_el_agente_no_recibe_trabajo(base, http, monkeypatch) -> None:
    auth = await maquina(base)
    a_la_hora(monkeypatch, a_las(2, 3))
    respuesta = await http.get("/api/agente/jobs/proximo", headers=auth)
    assert respuesta.status_code == 423
    assert "descanso" in respuesta.text


@sin_mongo
async def test_de_dia_si(base, http, monkeypatch) -> None:
    auth = await maquina(base)
    a_la_hora(monkeypatch, a_las(2, 12))
    respuesta = await http.get("/api/agente/jobs/proximo", headers=auth)
    assert respuesta.status_code == 204


@sin_mongo
async def test_de_noche_no_se_entrega_version(base, http, monkeypatch) -> None:
    auth = await maquina(base)
    a_la_hora(monkeypatch, a_las(2, 3))
    respuesta = (await http.get("/api/agente/version-esperada", headers=auth)).json()
    assert (respuesta["sha"], respuesta["origen"]) == ("", "descanso")


@sin_mongo
async def test_el_latido_dice_hasta_cuando_y_guarda_como_le_fue(base, http, monkeypatch) -> None:
    auth = await maquina(base)
    a_la_hora(monkeypatch, a_las(4, 15))
    respuesta = await http.post(
        "/api/agente/latido", headers=auth, json={"diagnostico": {}, "descanso": "suspende"}
    )
    assert respuesta.json()["horarios"]["descanso_hasta"] == a_las(5, 8).isoformat()
    vendedor = await base["vendedores"].find_one({"maquina": "pc-1"})
    assert vendedor["descanso_estado"] == "suspende"


@sin_mongo
async def test_una_corrida_programada_a_la_hora_del_descanso_no_sale(base) -> None:
    await maquina(base, latido=a_las(4, 15))
    await configuracion.actualizar(
        base, {"programacion": {"activa": True, "hora": "15:00", "dias": [7]}}
    )
    assert await programacion.revisar(base, ahora=a_las(4, 15)) is None
    assert await base["corridas"].count_documents({}) == 0


async def con_corrida_a_las_17(base) -> None:
    await configuracion.actualizar(
        base, {"programacion": {"activa": True, "hora": "17:00", "dias": [1, 2, 3, 4, 5, 6]}}
    )


@sin_mongo
async def test_a_la_mañana_dormida_no_alerta(base) -> None:
    """La despierta el vendedor cuando llega: dormida a las 10 es lo esperado."""
    await con_corrida_a_las_17(base)
    await maquina(base, latido=a_las(2, 0, 1))
    hay = await alertas.revisar(base, ahora=a_las(2, 10))
    assert not [a for a in hay if a.codigo == "maquina_dormida_antes_de_la_corrida"]


@sin_mongo
async def test_una_hora_antes_de_la_corrida_dormida_es_urgente(base) -> None:
    await con_corrida_a_las_17(base)
    await maquina(base, latido=a_las(2, 0, 1))
    hay = await alertas.revisar(base, ahora=a_las(2, 16, 10))
    [alerta] = [a for a in hay if a.codigo == "maquina_dormida_antes_de_la_corrida"]
    assert alerta.nivel is alertas.Nivel.URGENTE
    assert "17:00" in alerta.detalle


@sin_mongo
async def test_despierta_o_sin_corrida_hoy_no_alerta(base) -> None:
    await con_corrida_a_las_17(base)
    await maquina(base, latido=a_las(2, 9))
    hay = await alertas.revisar(base, ahora=a_las(2, 16, 10))
    assert not [a for a in hay if a.codigo == "maquina_dormida_antes_de_la_corrida"]

    await configuracion.actualizar(
        base, {"programacion": {"activa": True, "hora": "17:00", "dias": [1]}}
    )
    await base["vendedores"].update_one(
        {"maquina": "pc-1"}, {"$set": {"ultimo_latido": a_las(2, 0, 1)}}
    )
    hay = await alertas.revisar(base, ahora=a_las(2, 16, 10))
    assert not [a for a in hay if a.codigo == "maquina_dormida_antes_de_la_corrida"]


@sin_mongo
async def test_el_panel_la_muestra_dormida_y_no_sin_conexion(base) -> None:
    from app.api import panel

    await maquina(base, latido=a_las(2, 0, 1))
    config = await configuracion.obtener(base)
    vendedor = await base["vendedores"].find_one({"maquina": "pc-1"})

    resumen = panel._resumir_maquina(vendedor, a_las(2, 10), config=config)
    assert resumen["online"] is False
    assert resumen["dormida"] is True

    despierta = {**vendedor, "ultimo_latido": a_las(2, 9, 59)}
    assert panel._resumir_maquina(despierta, a_las(2, 10), config=config)["dormida"] is False


@sin_mongo
async def test_de_noche_no_avisa_que_quedo_afuera(base) -> None:
    await maquina(base, latido=a_las(1, 17))
    await corridas.disparar(base, quien="panel", ahora=a_las(1, 17))
    await base["vendedores"].update_one({"maquina": "pc-1"}, {"$set": {"ultimo_latido": None}})
    await corridas.cerrar_ausentes(base, ahora=a_las(1, 17) + timedelta(minutes=30))

    hay = await alertas.revisar(base, ahora=a_las(2, 3))
    assert not [a for a in hay if a.codigo == "maquina_fuera_de_corrida"]


@sin_mongo
async def test_un_descanso_sin_sentido_no_se_guarda(base, http, monkeypatch) -> None:
    monkeypatch.setenv("PANEL_PASSWORD", "clave-de-prueba")
    monkeypatch.setenv("SESION_SECRET", "secreto-de-prueba-largo")
    obtener_configuracion.cache_clear()
    try:
        assert (
            await http.post("/api/sesion", json={"clave": "clave-de-prueba"})
        ).status_code == 200
        malo = {**DE_FABRICA["descanso"], "desde": "08:00"}
        respuesta = await http.patch("/api/configuracion", json={"descanso": malo})
        assert respuesta.status_code == 422
        todos_libres = {**DE_FABRICA["descanso"], "dia_libre": [1, 2, 3, 4, 5, 6, 7]}
        respuesta = await http.patch("/api/configuracion", json={"descanso": todos_libres})
        assert respuesta.status_code == 422
    finally:
        obtener_configuracion.cache_clear()
