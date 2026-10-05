"""El actualizador a horario (D63): cuándo se entrega la versión nueva, y qué
disparadores se le mandan a cada máquina.

Lo que se custodia: con la actualización programada apagada nada cambia; con
ella prendida, la versión nueva sólo sale en la ventana del día o con
"Actualizar ahora", y cada agente se entera de sus horarios en el latido.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import SHA_DE_LA_RAMA, ar
from httpx import ASGITransport, AsyncClient

from app import db
from app.config import obtener_configuracion
from app.core import alertas, configuracion, horarios, vendedores, versiones
from app.core.esquema import inicializar
from app.main import app

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

MES = 10
PRENDIDA = {
    "actualizacion": {"activa": True, "hora": "15:00"},
    "actualizar_ya_hasta": None,
    "programacion": {"activa": True, "hora": "17:00", "dias": [1, 2, 3, 4, 5, 6]},
    "repesca": {"activa": True, "hora": "21:00", "dias": [1, 2, 3, 4, 5]},
}


# ---------------------------------------------------------------------------
# Puro
# ---------------------------------------------------------------------------


def test_apagada_siempre_toca() -> None:
    config = {"actualizacion": {"activa": False, "hora": "15:00"}}
    assert horarios.toca_actualizar(config, ar(2, 3, 0, mes=MES))
    assert horarios.para_agente(config, ar(2, 3, 0, mes=MES))["disparadores"] == []


@pytest.mark.parametrize(
    ("hora", "minuto", "toca"),
    [(14, 59, False), (15, 0, True), (16, 59, True), (17, 0, False), (3, 0, False)],
)
def test_prendida_toca_solo_en_la_ventana(hora: int, minuto: int, toca: bool) -> None:
    assert horarios.toca_actualizar(PRENDIDA, ar(2, hora, minuto, mes=MES)) is toca


def test_actualizar_ahora_abre_fuera_de_la_ventana() -> None:
    ahora = ar(2, 10, 0, mes=MES)
    config = {**PRENDIDA, "actualizar_ya_hasta": ahora + timedelta(minutes=30)}
    assert horarios.toca_actualizar(config, ahora)
    assert horarios.para_agente(config, ahora)["actualizar_ya"] is True
    vencido = {**PRENDIDA, "actualizar_ya_hasta": ahora - timedelta(minutes=1)}
    assert not horarios.toca_actualizar(vencido, ahora)


def test_la_ultima_ventana_es_la_de_hoy_o_la_de_ayer() -> None:
    inicio, fin = horarios.ultima_ventana(PRENDIDA, ar(2, 18, 0, mes=MES))
    assert inicio == ar(2, 15, 0, mes=MES)
    assert fin == ar(2, 17, 0, mes=MES)
    inicio, _ = horarios.ultima_ventana(PRENDIDA, ar(2, 9, 0, mes=MES))
    assert inicio == ar(1, 15, 0, mes=MES)


def test_los_disparadores_quince_minutos_antes() -> None:
    disparadores = horarios.para_agente(PRENDIDA, ar(2, 10, 0, mes=MES))["disparadores"]
    assert disparadores == [
        {"hora": "15:00", "dias": [1, 2, 3, 4, 5, 6, 7], "para": "actualizar"},
        {"hora": "16:45", "dias": [1, 2, 3, 4, 5, 6], "para": "revisar_antes_de_corrida"},
        {"hora": "20:45", "dias": [1, 2, 3, 4, 5], "para": "revisar_antes_de_repesca"},
    ]


def test_una_corrida_apagada_no_tiene_revision_previa() -> None:
    config = {**PRENDIDA, "repesca": {"activa": False, "hora": "21:00", "dias": [1]}}
    para = [d["para"] for d in horarios.para_agente(config, ar(2, 10, 0, mes=MES))["disparadores"]]
    assert para == ["actualizar", "revisar_antes_de_corrida"]


def test_una_corrida_a_medianoche_revisa_el_dia_anterior_a_las_23_45() -> None:
    config = {**PRENDIDA, "programacion": {"activa": True, "hora": "00:00", "dias": [1]}}
    disparadores = horarios.para_agente(config, ar(2, 10, 0, mes=MES))["disparadores"]
    assert disparadores[1]["hora"] == "23:45"


# ---------------------------------------------------------------------------
# Por la API
# ---------------------------------------------------------------------------


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


@pytest.fixture
async def http():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://prueba") as cliente:
        yield cliente


async def maquina(base) -> dict[str, str]:
    alta = await vendedores.dar_de_alta(base, maquina="pc-1", nombre="Prueba")
    await base["vendedores"].update_one({"maquina": "pc-1"}, {"$set": {"activo": True}})
    return {"Authorization": f"Bearer {alta.token}"}


def a_la_hora(monkeypatch, momento: datetime) -> None:
    """Fija el reloj de los endpoints del agente."""
    import app.api.agente as api_agente

    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return momento if tz is None else momento.astimezone(tz)

    monkeypatch.setattr(api_agente, "datetime", Reloj)


@sin_mongo
async def test_apagada_el_actualizador_recibe_la_version_como_siempre(base, http) -> None:
    auth = await maquina(base)
    respuesta = (await http.get("/api/agente/version-esperada", headers=auth)).json()
    assert respuesta["sha"] == SHA_DE_LA_RAMA


@sin_mongo
async def test_prendida_fuera_de_hora_contesta_vacio(base, http, monkeypatch) -> None:
    auth = await maquina(base)
    await configuracion.actualizar(base, {"actualizacion": {"activa": True, "hora": "15:00"}})
    a_la_hora(monkeypatch, ar(2, 10, 0, mes=MES))

    respuesta = (await http.get("/api/agente/version-esperada", headers=auth)).json()

    assert respuesta["sha"] == ""
    assert respuesta["origen"] == "fuera_de_horario"
    assert respuesta["maquina"] == "pc-1"


@sin_mongo
async def test_prendida_en_hora_entrega_la_version(base, http, monkeypatch) -> None:
    auth = await maquina(base)
    await configuracion.actualizar(base, {"actualizacion": {"activa": True, "hora": "15:00"}})
    a_la_hora(monkeypatch, ar(2, 15, 20, mes=MES))
    respuesta = (await http.get("/api/agente/version-esperada", headers=auth)).json()
    assert respuesta["sha"] == SHA_DE_LA_RAMA


@sin_mongo
async def test_el_latido_lleva_los_horarios_y_guarda_como_quedo(base, http) -> None:
    auth = await maquina(base)
    await configuracion.actualizar(base, {"actualizacion": {"activa": True, "hora": "15:00"}})

    respuesta = await http.post(
        "/api/agente/latido",
        headers=auth,
        json={"diagnostico": {}, "horario_actualizador": "ok"},
    )

    cuerpo = respuesta.json()
    assert cuerpo["horarios"]["disparadores"][0] == {
        "hora": "15:00",
        "dias": [1, 2, 3, 4, 5, 6, 7],
        "para": "actualizar",
    }
    assert cuerpo["horarios"]["actualizar_ya"] is False
    vendedor = await base["vendedores"].find_one({"maquina": "pc-1"})
    assert vendedor["horario_actualizador"] == "ok"


@sin_mongo
async def test_un_latido_de_un_agente_viejo_sigue_andando(base, http) -> None:
    auth = await maquina(base)
    respuesta = await http.post("/api/agente/latido", headers=auth, json={"diagnostico": {}})
    assert respuesta.status_code == 200
    horarios_de_respuesta = respuesta.json()["horarios"]
    assert horarios_de_respuesta["disparadores"] == []
    assert horarios_de_respuesta["actualizar_ya"] is False
    assert horarios_de_respuesta["descanso_hasta"] is None


@sin_mongo
async def test_el_registro_tambien_lleva_los_horarios(base, http) -> None:
    auth = await maquina(base)
    respuesta = await http.post(
        "/api/agente/registrar", headers=auth, json={"version": "abc1234 2026-10-02"}
    )
    horarios_de_respuesta = respuesta.json()["horarios"]
    assert horarios_de_respuesta["disparadores"] == []
    assert horarios_de_respuesta["actualizar_ya"] is False
    assert horarios_de_respuesta["descanso_hasta"] is None


@sin_mongo
async def test_actualizar_ahora_desde_el_panel(base, http, monkeypatch) -> None:
    monkeypatch.setenv("PANEL_PASSWORD", "clave-de-prueba")
    monkeypatch.setenv("SESION_SECRET", "secreto-de-prueba-largo")
    obtener_configuracion.cache_clear()
    try:
        auth = await maquina(base)
        await configuracion.actualizar(base, {"actualizacion": {"activa": True, "hora": "15:00"}})
        assert (
            await http.post("/api/sesion", json={"clave": "clave-de-prueba"})
        ).status_code == 200

        assert (await http.post("/api/sistema/actualizar-ahora")).status_code == 200

        latido = await http.post("/api/agente/latido", headers=auth, json={"diagnostico": {}})
        assert latido.json()["horarios"]["actualizar_ya"] is True
        version = (await http.get("/api/agente/version-esperada", headers=auth)).json()
        assert version["sha"] == SHA_DE_LA_RAMA
        assert await base["auditoria"].count_documents({"que": "configuracion_cambiada"}) >= 1
    finally:
        obtener_configuracion.cache_clear()


# ---------------------------------------------------------------------------
# La alerta de atrasada
# ---------------------------------------------------------------------------


async def atrasada(base, ahora: datetime) -> None:
    await vendedores.dar_de_alta(base, maquina="pc-1", nombre="Prueba")
    await base["vendedores"].update_one(
        {"maquina": "pc-1"},
        {
            "$set": {
                "activo": True,
                "ultimo_latido": ahora,
                "version_agente": "0000000 2026-09-01",
                "version_registrada_en": ahora - timedelta(days=2),
            }
        },
    )


@sin_mongo
async def test_con_horario_no_esta_atrasada_antes_de_su_ventana(base) -> None:
    ahora = ar(2, 12, 0, mes=MES)
    await atrasada(base, ahora)
    await configuracion.actualizar(base, {"actualizacion": {"activa": True, "hora": "15:00"}})
    versiones._visto[SHA_DE_LA_RAMA] = ahora - timedelta(hours=1)

    hay = await alertas.revisar(base, ahora=ahora, version_esperada=SHA_DE_LA_RAMA)

    assert not [a for a in hay if a.codigo == "maquina_desactualizada"]


@sin_mongo
async def test_con_horario_esta_atrasada_si_paso_su_ventana_con_la_version_conocida(base) -> None:
    ahora = ar(2, 18, 0, mes=MES)
    await atrasada(base, ahora)
    await configuracion.actualizar(base, {"actualizacion": {"activa": True, "hora": "15:00"}})
    versiones._visto[SHA_DE_LA_RAMA] = ar(2, 9, 0, mes=MES)

    hay = await alertas.revisar(base, ahora=ahora, version_esperada=SHA_DE_LA_RAMA)

    assert [a.maquina for a in hay if a.codigo == "maquina_desactualizada"] == ["pc-1"]


@sin_mongo
async def test_una_version_que_aparecio_despues_de_la_ventana_espera_a_manana(base) -> None:
    ahora = ar(2, 18, 0, mes=MES)
    await atrasada(base, ahora)
    await configuracion.actualizar(base, {"actualizacion": {"activa": True, "hora": "15:00"}})
    versiones._visto[SHA_DE_LA_RAMA] = ar(2, 17, 30, mes=MES)

    hay = await alertas.revisar(base, ahora=ahora, version_esperada=SHA_DE_LA_RAMA)

    assert not [a for a in hay if a.codigo == "maquina_desactualizada"]


def test_el_backend_recuerda_desde_cuando_conoce_cada_version() -> None:
    versiones.olvidar_cache()
    assert versiones.vista_desde("abc1234") is None
    versiones._anotar_visto("abc1234")
    primera = versiones.vista_desde("abc1234")
    versiones._anotar_visto("abc1234")
    assert versiones.vista_desde("abc1234") == primera
    assert primera is not None and primera <= datetime.now(UTC)
    versiones.olvidar_cache()
