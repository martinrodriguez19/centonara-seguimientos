"""Una máquina que no da señales queda afuera, y una corrida siempre termina (D59).

Lo que se custodia: que una PC apagada no entre a la corrida, que la que se
apaga a mitad de camino no la deje abierta, que el techo cierre lo que nadie
cierra, y que nada de esto toque a las máquinas que sí están trabajando.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app import db
from app.core import alertas, auditoria, cola, configuracion, corridas, vendedores
from app.core.esquema import inicializar

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

AHORA = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)


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


async def maquina(base, nombre: str, *, latido: datetime | None, **extra) -> None:
    await vendedores.dar_de_alta(base, maquina=nombre, nombre=nombre.title())
    await base["vendedores"].update_one(
        {"maquina": nombre},
        {
            "$set": {
                "activo": True,
                "acepto_condiciones_en": AHORA,
                "ultimo_latido": latido,
                **extra,
            }
        },
    )


async def latir(base, nombre: str, cuando: datetime) -> None:
    await base["vendedores"].update_one({"maquina": nombre}, {"$set": {"ultimo_latido": cuando}})


async def jobs_de(base, nombre: str) -> list[dict]:
    return await base["jobs"].find({"maquina": nombre}).to_list(None)


# ---------------------------------------------------------------------------
# Al largar
# ---------------------------------------------------------------------------


@sin_mongo
async def test_la_que_no_da_senales_no_entra_y_queda_anotada(base) -> None:
    await maquina(base, "pc-viva", latido=AHORA - timedelta(minutes=2))
    await maquina(base, "pc-apagada", latido=AHORA - timedelta(hours=3))
    await maquina(base, "pc-nueva", latido=None)

    disparo = await corridas.disparar(base, quien="panel", ahora=AHORA)

    assert disparo.maquinas == ["pc-viva"]
    assert [j["maquina"] for j in await base["jobs"].find().to_list(None)] == ["pc-viva"]
    progreso = await corridas.progreso(base, disparo.corrida_id)
    assert progreso["maquinas_excluidas"] == [
        {"maquina": "pc-apagada", "motivo": "sin_latido"},
        {"maquina": "pc-nueva", "motivo": "sin_latido"},
    ]
    assert progreso["maquinas_ausentes"] == []


@sin_mongo
async def test_pausada_y_frenada_se_anotan_y_la_inactiva_no(base) -> None:
    fresco = AHORA - timedelta(minutes=1)
    await maquina(base, "pc-viva", latido=fresco)
    await maquina(base, "pc-pausada", latido=fresco, pausado_hasta=AHORA + timedelta(hours=2))
    await maquina(base, "pc-frenada", latido=fresco, frenado_por_canario_en=AHORA)
    await maquina(base, "pc-de-baja", latido=fresco)
    await base["vendedores"].update_one({"maquina": "pc-de-baja"}, {"$set": {"activo": False}})

    disparo = await corridas.disparar(base, quien="panel", ahora=AHORA)

    progreso = await corridas.progreso(base, disparo.corrida_id)
    assert sorted(progreso["maquinas_excluidas"], key=lambda e: e["maquina"]) == [
        {"maquina": "pc-frenada", "motivo": "frenada"},
        {"maquina": "pc-pausada", "motivo": "pausada"},
    ]


@sin_mongo
async def test_justo_en_el_borde_de_los_diez_minutos_entra(base) -> None:
    await maquina(base, "pc-1", latido=AHORA - timedelta(minutes=corridas.MINUTOS_SIN_LATIDO))
    disparo = await corridas.disparar(base, quien="panel", ahora=AHORA)
    assert disparo.maquinas == ["pc-1"]


@sin_mongo
async def test_si_ninguna_da_senales_no_se_larga_nada(base) -> None:
    await maquina(base, "pc-apagada", latido=AHORA - timedelta(hours=1))
    with pytest.raises(corridas.NoHayMaquinas):
        await corridas.disparar(base, quien="panel", ahora=AHORA)
    assert await base["corridas"].count_documents({}) == 0


@sin_mongo
async def test_con_una_corrida_en_curso_no_se_larga_otra(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    await corridas.disparar(base, quien="panel", ahora=AHORA)
    with pytest.raises(corridas.CorridaEnCurso):
        await corridas.disparar(base, quien="programacion", ahora=AHORA)
    assert await base["corridas"].count_documents({}) == 1


@sin_mongo
async def test_terminada_la_anterior_se_puede_largar_otra(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    primera = await corridas.disparar(base, quien="panel", ahora=AHORA)
    for job in await jobs_de(base, "pc-1"):
        await cola.reportar(base, job["_id"], ok=True)
    segunda = await corridas.disparar(base, quien="panel", ahora=AHORA)
    assert segunda.corrida_id != primera.corrida_id


# ---------------------------------------------------------------------------
# Durante
# ---------------------------------------------------------------------------


@sin_mongo
async def test_la_que_se_apaga_a_mitad_se_corta_y_las_demas_siguen(base) -> None:
    await maquina(base, "pc-viva", latido=AHORA)
    await maquina(base, "pc-se-apaga", latido=AHORA)
    disparo = await corridas.disparar(base, quien="panel", ahora=AHORA)

    despues = AHORA + timedelta(minutes=corridas.MINUTOS_AUSENTE + 5)
    await latir(base, "pc-viva", despues - timedelta(seconds=30))

    assert await corridas.cerrar_ausentes(base, ahora=despues) == 1

    [cortado] = await jobs_de(base, "pc-se-apaga")
    assert cortado["estado"] == "fallido"
    assert cortado["codigo"] == "MAQUINA_AUSENTE"
    [vivo] = await jobs_de(base, "pc-viva")
    assert vivo["estado"] == "pendiente"

    progreso = await corridas.progreso(base, disparo.corrida_id)
    assert [a["maquina"] for a in progreso["maquinas_ausentes"]] == ["pc-se-apaga"]
    assert progreso["terminada"] is False
    evento = await base["auditoria"].find_one({"que": str(auditoria.Que.MAQUINA_AUSENTE)})
    assert evento["detalle"]["maquina"] == "pc-se-apaga"

    # La que sigue viva termina lo suyo, y la corrida termina con ella.
    await cola.reportar(base, vivo["_id"], ok=True)
    assert (await corridas.progreso(base, disparo.corrida_id))["terminada"] is True


@sin_mongo
async def test_un_rato_sin_latido_no_alcanza_para_cortar(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    await corridas.disparar(base, quien="panel", ahora=AHORA)
    casi = AHORA + timedelta(minutes=corridas.MINUTOS_AUSENTE - 1)
    assert await corridas.cerrar_ausentes(base, ahora=casi) == 0
    [job] = await jobs_de(base, "pc-1")
    assert job["estado"] == "pendiente"


@sin_mongo
async def test_un_job_tomado_por_una_maquina_que_murio_tambien_se_corta(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    disparo = await corridas.disparar(base, quien="panel", ahora=AHORA)
    await cola.tomar(base, "pc-1", ahora=AHORA)

    despues = AHORA + timedelta(minutes=corridas.MINUTOS_AUSENTE + 1)
    assert await corridas.cerrar_ausentes(base, ahora=despues) == 1

    corrida = await base["corridas"].find_one({"_id": disparo.corrida_id})
    assert corrida["estado"] == "terminada"
    assert corrida["terminada_en"] == despues


@sin_mongo
async def test_una_maquina_ausente_que_ya_termino_no_molesta(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    await corridas.disparar(base, quien="panel", ahora=AHORA)
    for job in await jobs_de(base, "pc-1"):
        await cola.reportar(base, job["_id"], ok=True)

    assert await corridas.cerrar_ausentes(base, ahora=AHORA + timedelta(hours=2)) == 0
    assert await base["auditoria"].count_documents({"que": "maquina_ausente"}) == 0


@sin_mongo
async def test_el_envio_de_una_maquina_ausente_no_queda_enviando(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    disparo = await corridas.disparar(base, quien="panel", ahora=AHORA)
    mensaje = await base["mensajes"].insert_one(
        {
            "corrida_id": disparo.corrida_id,
            "maquina": "pc-1",
            "estado": "ENVIANDO",
            "texto": "hola",
            "creado_en": AHORA,
        }
    )

    await corridas.cerrar_ausentes(base, ahora=AHORA + timedelta(hours=1))

    resuelto = await base["mensajes"].find_one({"_id": mensaje.inserted_id})
    assert resuelto["estado"] == "DESCARTADO"
    assert resuelto["motivo"] == "fallido"


# ---------------------------------------------------------------------------
# El techo
# ---------------------------------------------------------------------------


@sin_mongo
async def test_a_las_cinco_horas_lo_vivo_se_cierra_y_la_corrida_termina(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    disparo = await corridas.disparar(base, quien="panel", ahora=AHORA)

    #  Viva todo el tiempo: el techo cubre lo que la ausencia no ve.
    tarde = AHORA + timedelta(hours=5, minutes=1)
    await latir(base, "pc-1", tarde)
    assert await corridas.cerrar_ausentes(base, ahora=tarde) == 0
    assert await corridas.vencer_largas(base, ahora=tarde) == 1

    [job] = await jobs_de(base, "pc-1")
    assert job["codigo"] == "VENCIDO"
    corrida = await base["corridas"].find_one({"_id": disparo.corrida_id})
    assert corrida["estado"] == "terminada"
    assert await base["auditoria"].count_documents({"que": "corrida_vencida"}) == 1
    assert await corridas.en_curso(base) is None


@sin_mongo
async def test_antes_del_techo_no_se_toca_nada(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    await corridas.disparar(base, quien="panel", ahora=AHORA)
    assert await corridas.vencer_largas(base, ahora=AHORA + timedelta(hours=4, minutes=59)) == 0


@sin_mongo
async def test_el_techo_sale_de_la_configuracion(base) -> None:
    await configuracion.actualizar(base, {"horas_max_corrida": 2})
    await maquina(base, "pc-1", latido=AHORA)
    await corridas.disparar(base, quien="panel", ahora=AHORA)
    assert await corridas.vencer_largas(base, ahora=AHORA + timedelta(hours=2, minutes=1)) == 1


@sin_mongo
async def test_el_techo_suelta_una_corrida_frenada_y_su_freno(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    disparo = await corridas.disparar(base, quien="panel", ahora=AHORA)
    await base["corridas"].update_one({"_id": disparo.corrida_id}, {"$set": {"estado": "frenada"}})
    await vendedores.frenar_por_canario(base, "pc-1", ahora=AHORA)

    await corridas.vencer_largas(base, ahora=AHORA + timedelta(hours=6))

    corrida = await base["corridas"].find_one({"_id": disparo.corrida_id})
    assert corrida["estado"] == "terminada"
    vendedor = await base["vendedores"].find_one({"maquina": "pc-1"})
    assert vendedor["frenado_por_canario_en"] is None


@sin_mongo
async def test_una_ausencia_no_cierra_una_corrida_frenada(base) -> None:
    """Frenada espera una decisión (D31): la ausencia corta los jobs, no la decisión."""
    await maquina(base, "pc-1", latido=AHORA)
    disparo = await corridas.disparar(base, quien="panel", ahora=AHORA)
    await base["corridas"].update_one({"_id": disparo.corrida_id}, {"$set": {"estado": "frenada"}})
    await corridas.cerrar_ausentes(base, ahora=AHORA + timedelta(hours=1))
    corrida = await base["corridas"].find_one({"_id": disparo.corrida_id})
    assert corrida["estado"] == "frenada"


# ---------------------------------------------------------------------------
# Lo que ve el panel
# ---------------------------------------------------------------------------


@sin_mongo
async def test_la_alerta_dice_quien_quedo_afuera_mientras_siga_callada(base) -> None:
    await maquina(base, "pc-viva", latido=AHORA)
    await maquina(base, "pc-apagada", latido=AHORA - timedelta(hours=3))
    await corridas.disparar(base, quien="panel", ahora=AHORA)

    hay = await alertas.revisar(base, ahora=AHORA + timedelta(minutes=1))
    [afuera] = [a for a in hay if a.codigo == "maquina_fuera_de_corrida"]
    assert afuera.maquina == "pc-apagada"
    assert afuera.nivel is alertas.Nivel.AVISO

    # Vuelve: la alerta ya no pide nada.
    await latir(base, "pc-apagada", AHORA + timedelta(minutes=2))
    hay = await alertas.revisar(base, ahora=AHORA + timedelta(minutes=3))
    assert not [a for a in hay if a.codigo == "maquina_fuera_de_corrida"]


@sin_mongo
async def test_la_alerta_tambien_cubre_a_la_que_se_apago_a_mitad(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    await corridas.disparar(base, quien="panel", ahora=AHORA)
    despues = AHORA + timedelta(minutes=30)
    await corridas.cerrar_ausentes(base, ahora=despues)

    hay = await alertas.revisar(base, ahora=despues)
    assert [a.maquina for a in hay if a.codigo == "maquina_fuera_de_corrida"] == ["pc-1"]


@sin_mongo
async def test_cortes_por_ausencia_o_techo_no_son_falla_siempre(base) -> None:
    await maquina(base, "pc-1", latido=AHORA)
    for i in range(3):
        await base["jobs"].insert_one(
            {
                "maquina": "pc-1",
                "tipo": "BORRADORES",
                "estado": "fallido",
                "codigo": "MAQUINA_AUSENTE" if i % 2 else "VENCIDO",
                "terminado_en": AHORA - timedelta(minutes=i),
            }
        )
    hay = await alertas.revisar(base, ahora=AHORA)
    assert not [a for a in hay if a.codigo == "maquina_falla_siempre"]


def test_los_cierres_del_mantenimiento_no_se_reintentan() -> None:
    assert not cola.Codigo.MAQUINA_AUSENTE.reintenta
    assert not cola.Codigo.VENCIDO.reintenta
