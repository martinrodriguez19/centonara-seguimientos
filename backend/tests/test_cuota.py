"""Sin tokens de Claude, la máquina se pausa sola hasta que vuelvan (D60).

Lo que se custodia: que `LIMITE_USO` no se reintente, que pause a esa máquina
y a ninguna otra, que la pausa dure lo que dice Claude (o lo configurado), que
la corrida pueda terminar con las demás, y que se vea en el panel.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app import db
from app.core import alertas, cola, configuracion, corridas, cuota, pase_unico, vendedores
from app.core.esquema import inicializar
from app.main import app

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

AHORA = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)
CONFIG = {"horas_pausa_cuota": 4}


# ---------------------------------------------------------------------------
# Hasta cuándo — puro
# ---------------------------------------------------------------------------


def test_si_claude_dice_cuando_vuelve_se_le_cree_con_margen() -> None:
    reinicio = AHORA + timedelta(hours=2)
    hasta = cuota.hasta_cuando({"reinicia_en": reinicio.isoformat()}, CONFIG, AHORA)
    assert hasta == reinicio + cuota.MARGEN_REINICIO


def test_acepta_la_z_de_utc() -> None:
    hasta = cuota.hasta_cuando({"reinicia_en": "2026-10-02T23:00:00Z"}, CONFIG, AHORA)
    assert hasta == datetime(2026, 10, 2, 23, 10, tzinfo=UTC)


def test_si_no_lo_dice_se_usan_las_horas_configuradas() -> None:
    assert cuota.hasta_cuando({}, CONFIG, AHORA) == AHORA + timedelta(hours=4)
    assert cuota.hasta_cuando({}, {"horas_pausa_cuota": 2}, AHORA) == AHORA + timedelta(hours=2)


@pytest.mark.parametrize(
    "reinicia_en",
    [
        (AHORA - timedelta(minutes=5)).isoformat(),  # ya pasó
        (AHORA + timedelta(days=9)).isoformat(),  # absurdo
        "mañana a la tarde",  # no se pudo leer
        "",
    ],
)
def test_una_hora_que_no_cierra_cae_a_lo_configurado(reinicia_en: str) -> None:
    hasta = cuota.hasta_cuando({"reinicia_en": reinicia_en}, CONFIG, AHORA)
    assert hasta == AHORA + timedelta(hours=4)


def test_limite_uso_no_se_reintenta() -> None:
    assert not cola.Codigo.LIMITE_USO.reintenta


# ---------------------------------------------------------------------------
# De punta a punta, por la API del agente
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


async def maquina(base, nombre: str) -> str:
    alta = await vendedores.dar_de_alta(base, maquina=nombre, nombre=nombre.title())
    await base["vendedores"].update_one(
        {"maquina": nombre},
        {
            "$set": {
                "activo": True,
                "acepto_condiciones_en": datetime.now(UTC),
                "ultimo_latido": datetime.now(UTC),
            }
        },
    )
    return alta.token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def sin_cuota(http, token: str, detalle: dict | None = None):
    job = (await http.get("/api/agente/jobs/proximo", headers=auth(token))).json()
    return await http.post(
        f"/api/agente/jobs/{job['id']}/resultado",
        headers=auth(token),
        json={
            "ok": False,
            "codigo": "LIMITE_USO",
            "detalle": {"motivo": "Claude AI usage limit reached", **(detalle or {})},
        },
    )


@sin_mongo
async def test_el_reporte_pausa_a_todas_las_activas(base, http) -> None:
    """D65.2: la cuenta de Claude es una; la segunda máquina no tiene que
    enterarse pagando una llamada fallida."""
    token = await maquina(base, "pc-sin-cuota")
    await maquina(base, "pc-con-cuota")
    await maquina(base, "pc-de-baja")
    await base["vendedores"].update_one({"maquina": "pc-de-baja"}, {"$set": {"activo": False}})
    await corridas.disparar(base, quien="panel")

    reinicio = datetime.now(UTC) + timedelta(hours=1)
    respuesta = await sin_cuota(http, token, {"reinicia_en": reinicio.isoformat()})

    assert respuesta.json() == {"estado": "fallido", "reintenta": False, "frena_corrida": False}
    for nombre in ("pc-sin-cuota", "pc-con-cuota"):
        pausada = await base["vendedores"].find_one({"maquina": nombre})
        esperado = reinicio + cuota.MARGEN_REINICIO
        assert abs(pausada["pausa_cuota_hasta"] - esperado) < timedelta(seconds=1)
    #  La que el dueño dio de baja no se toca: no es del sistema pausarla.
    de_baja = await base["vendedores"].find_one({"maquina": "pc-de-baja"})
    assert de_baja.get("pausa_cuota_hasta") is None
    #  No es la pausa global del dueño: se va sola.
    assert not await configuracion.esta_pausado(base)

    # Durante la pausa no recibe nada.
    proximo = await http.get("/api/agente/jobs/proximo", headers=auth(token))
    assert proximo.status_code == 423

    evento = await base["auditoria"].find_one({"que": "cuota_agotada"})
    assert evento["detalle"]["maquina"] == "pc-sin-cuota"
    assert evento["detalle"]["pausadas"] == ["pc-con-cuota", "pc-sin-cuota"]
    assert evento["detalle"]["dijo_cuando"] is True


@sin_mongo
async def test_una_pausa_mas_larga_no_se_acorta(base) -> None:
    await maquina(base, "pc-1")
    await maquina(base, "pc-2")
    larga = datetime.now(UTC) + timedelta(days=2)
    await vendedores.pausar_por_cuota(base, "pc-2", hasta=larga)

    hasta = await cuota.registrar(base, maquina="pc-1", detalle={})

    assert hasta < larga
    pc2 = await base["vendedores"].find_one({"maquina": "pc-2"})
    assert abs(pc2["pausa_cuota_hasta"] - larga) < timedelta(seconds=1)
    marca = await base["programacion"].find_one({"_id": cuota.MARCA})
    assert abs(marca["vuelve_en"] - hasta) < timedelta(seconds=1)


@sin_mongo
async def test_lo_vivo_de_esa_maquina_se_cierra_y_la_corrida_termina(base, http) -> None:
    token = await maquina(base, "pc-1")
    disparo = await corridas.disparar(base, quien="panel")
    #  Un segundo job vivo de la misma máquina en la misma corrida.
    await cola.encolar(
        base, tipo=cola.Tipo.DIAGNOSTICO, maquina="pc-1", corrida_id=disparo.corrida_id, payload={}
    )

    await sin_cuota(http, token)

    jobs = await base["jobs"].find({"maquina": "pc-1"}).to_list(None)
    assert {j["estado"] for j in jobs} == {"fallido"}
    assert {j["codigo"] for j in jobs} == {"LIMITE_USO"}
    assert (await corridas.progreso(base, disparo.corrida_id))["terminada"] is True
    assert await corridas.en_curso(base) is None


@sin_mongo
async def test_sin_hora_la_pausa_es_la_configurada(base, http) -> None:
    await configuracion.actualizar(base, {"horas_pausa_cuota": 3})
    token = await maquina(base, "pc-1")
    await corridas.disparar(base, quien="panel")
    antes = datetime.now(UTC)

    await sin_cuota(http, token)

    hasta = (await base["vendedores"].find_one({"maquina": "pc-1"}))["pausa_cuota_hasta"]
    assert antes + timedelta(hours=3) <= hasta <= datetime.now(UTC) + timedelta(hours=3)


@sin_mongo
async def test_sin_cuota_no_entra_a_la_corrida_siguiente(base) -> None:
    await maquina(base, "pc-1")
    await maquina(base, "pc-2")
    await vendedores.pausar_por_cuota(base, "pc-1", hasta=datetime.now(UTC) + timedelta(hours=1))

    disparo = await corridas.disparar(base, quien="panel")

    assert disparo.maquinas == ["pc-2"]
    progreso = await corridas.progreso(base, disparo.corrida_id)
    assert progreso["maquinas_excluidas"] == [{"maquina": "pc-1", "motivo": "sin_cuota"}]


@sin_mongo
async def test_la_pausa_vence_sola(base) -> None:
    await maquina(base, "pc-1")
    vence = datetime.now(UTC) + timedelta(hours=1)
    await vendedores.pausar_por_cuota(base, "pc-1", hasta=vence)
    vendedor = await base["vendedores"].find_one({"maquina": "pc-1"})

    assert vendedores.esta_pausada(vendedor, ahora=vence - timedelta(minutes=1))
    assert not vendedores.esta_pausada(vendedor, ahora=vence + timedelta(minutes=1))
    assert vendedores.sin_cuota_hasta(vendedor, ahora=vence + timedelta(minutes=1)) is None


@sin_mongo
async def test_sin_cuota_no_activa_el_respaldo(base) -> None:
    await configuracion.actualizar(base, {"modo_borrador": "extension_con_respaldo"})
    await maquina(base, "pc-1")
    disparo = await corridas.disparar(base, quien="panel")

    encolado = await pase_unico.activar_respaldo(
        base,
        job={"corrida_id": disparo.corrida_id, "maquina": "pc-1", "codigo": "LIMITE_USO"},
    )

    assert encolado is None
    assert await base["jobs"].count_documents({"tipo": "LISTAR"}) == 0


@sin_mongo
async def test_aviso_propio_y_no_urgente(base) -> None:
    await maquina(base, "pc-1")
    await vendedores.pausar_por_cuota(base, "pc-1", hasta=datetime.now(UTC) + timedelta(hours=1))

    hay = await alertas.revisar(base)

    [aviso] = [a for a in hay if a.codigo == "maquina_sin_cuota"]
    assert aviso.nivel is alertas.Nivel.AVISO
    assert aviso.maquina == "pc-1"
    #  Pausada por cuota no es "caída" ni "pausada" a secas.
    assert not [a for a in hay if a.codigo in ("maquina_caida", "maquina_degradada")]


@sin_mongo
async def test_el_panel_la_muestra_y_la_puede_soltar(base, http, monkeypatch) -> None:
    from app.config import obtener_configuracion

    monkeypatch.setenv("PANEL_PASSWORD", "clave-de-prueba")
    monkeypatch.setenv("SESION_SECRET", "secreto-de-prueba-largo")
    obtener_configuracion.cache_clear()
    await maquina(base, "pc-1")
    await vendedores.pausar_por_cuota(base, "pc-1", hasta=datetime.now(UTC) + timedelta(hours=1))
    assert (await http.post("/api/sesion", json={"clave": "clave-de-prueba"})).status_code == 200

    [resumen] = (await http.get("/api/estado")).json()["maquinas"]
    assert resumen["sin_cuota_hasta"] is not None
    assert resumen["pausada"] is True

    respuesta = await http.patch("/api/vendedores/pc-1", json={"quitar_pausa_cuota": True})
    assert respuesta.status_code == 200
    [resumen] = (await http.get("/api/estado")).json()["maquinas"]
    assert resumen["sin_cuota_hasta"] is None
    assert resumen["pausada"] is False
    obtener_configuracion.cache_clear()
