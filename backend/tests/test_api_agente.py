"""Tests de los cuatro endpoints que consume el agente.

Van contra la aplicación real y una base real: es la primera superficie HTTP del
sistema, y lo que se quiere verificar —que un token de otra máquina no sirve,
que la pausa devuelve 423, que el esquema rechaza texto arbitrario— no se
prueba llamando funciones sueltas.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app import db
from app.core import cola, configuracion, vendedores
from app.core.esquema import inicializar
from app.main import app

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)


@pytest.fixture
async def base(monkeypatch):
    """Una base limpia, enchufada al módulo `db` que usan los endpoints."""
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
async def cliente():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://prueba") as http:
        yield http


@pytest.fixture
async def maquina_activa(base):
    """Una máquina lista para trabajar, con su token."""
    alta = await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"},
        {"$set": {"activo": True, "acepto_condiciones_en": datetime.now(UTC)}},
    )
    return alta


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "encabezados",
    [
        {},
        {"Authorization": "Bearer sgc_inventado"},
        {"Authorization": "sgc_sin_bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic dXN1YXJpbzpjbGF2ZQ=="},
    ],
)
@sin_mongo
async def test_sin_token_valido_todo_es_401(cliente, base, encabezados) -> None:
    for ruta in ("/api/agente/jobs/proximo",):
        respuesta = await cliente.get(ruta, headers=encabezados)
        assert respuesta.status_code == 401


@sin_mongo
async def test_el_401_no_dice_en_que_se_equivoco(cliente, base) -> None:
    """Distinguirlos le diría a quien prueba tokens cuál se acercó más."""
    uno = await cliente.get("/api/agente/jobs/proximo", headers=auth("sgc_a"))
    otro = await cliente.get("/api/agente/jobs/proximo", headers=auth("sgc_b"))
    assert uno.json() == otro.json()


# ---------------------------------------------------------------------------
# Registro y latido
# ---------------------------------------------------------------------------


@sin_mongo
async def test_registrar_devuelve_la_situacion_de_la_maquina(cliente, maquina_activa) -> None:
    respuesta = await cliente.post(
        "/api/agente/registrar",
        json={"version": "0.2.0", "diagnostico": {"chrome": "ok"}},
        headers=auth(maquina_activa.token),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["maquina"] == "mac-rocio"
    assert cuerpo["pausada"] is False
    assert cuerpo["puede_enviar"] is True


@sin_mongo
async def test_una_maquina_recien_dada_de_alta_se_reporta_pausada(cliente, base) -> None:
    alta = await vendedores.dar_de_alta(base, maquina="mac-nueva", nombre="Nueva")
    respuesta = await cliente.post(
        "/api/agente/registrar", json={"version": "0.2.0"}, headers=auth(alta.token)
    )

    cuerpo = respuesta.json()
    assert cuerpo["pausada"] is True
    assert cuerpo["puede_enviar"] is False


@sin_mongo
async def test_el_registro_rechaza_campos_que_no_declaramos(cliente, maquina_activa) -> None:
    """`extra="forbid"`: el agente no puede mandar lo que se le ocurra."""
    respuesta = await cliente.post(
        "/api/agente/registrar",
        json={"version": "0.2.0", "sorpresa": "hola"},
        headers=auth(maquina_activa.token),
    )
    assert respuesta.status_code == 422


@sin_mongo
async def test_el_latido_actualiza_el_diagnostico(cliente, base, maquina_activa) -> None:
    respuesta = await cliente.post(
        "/api/agente/latido",
        json={"diagnostico": {"whatsapp_sesion": "pide_qr"}},
        headers=auth(maquina_activa.token),
    )

    assert respuesta.status_code == 200
    documento = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert documento["diagnostico"]["whatsapp_sesion"] == "pide_qr"


# ---------------------------------------------------------------------------
# Pedir trabajo
# ---------------------------------------------------------------------------


@sin_mongo
async def test_sin_trabajo_devuelve_204(cliente, maquina_activa) -> None:
    respuesta = await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))
    assert respuesta.status_code == 204


@sin_mongo
async def test_entrega_un_job_encolado(cliente, base, maquina_activa) -> None:
    await cola.encolar(base, tipo=cola.Tipo.DIAGNOSTICO, maquina="mac-rocio")

    respuesta = await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))

    assert respuesta.status_code == 200
    assert respuesta.json()["tipo"] == "DIAGNOSTICO"


@sin_mongo
async def test_no_entrega_el_job_de_otra_maquina(cliente, base, maquina_activa) -> None:
    await cola.encolar(base, tipo=cola.Tipo.DIAGNOSTICO, maquina="mac-juan")

    respuesta = await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))
    assert respuesta.status_code == 204


@sin_mongo
async def test_preguntar_por_trabajo_cuenta_como_latido(cliente, base, maquina_activa) -> None:
    """Una Mac sana sin nada que hacer no puede aparecer caída en el panel."""
    await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))

    documento = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert documento["ultimo_latido"] is not None


# ---------------------------------------------------------------------------
# El kill switch
# ---------------------------------------------------------------------------


@sin_mongo
async def test_la_pausa_global_devuelve_423(cliente, base, maquina_activa) -> None:
    """Es lo que hace que el kill switch tenga efecto sin empujar nada."""
    await cola.encolar(base, tipo=cola.Tipo.DIAGNOSTICO, maquina="mac-rocio")
    await configuracion.pausar(base, pausado=True, quien="martin")

    respuesta = await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))
    assert respuesta.status_code == 423


@sin_mongo
async def test_al_soltar_la_pausa_el_trabajo_vuelve_sin_reiniciar_nada(
    cliente, base, maquina_activa
) -> None:
    await cola.encolar(base, tipo=cola.Tipo.DIAGNOSTICO, maquina="mac-rocio")
    await configuracion.pausar(base, pausado=True, quien="martin")
    await configuracion.pausar(base, pausado=False, quien="martin")

    respuesta = await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))
    assert respuesta.status_code == 200


@sin_mongo
async def test_una_maquina_pausada_por_su_vendedor_recibe_423(
    cliente, base, maquina_activa
) -> None:
    await cola.encolar(base, tipo=cola.Tipo.DIAGNOSTICO, maquina="mac-rocio")
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"},
        {"$set": {"pausado_hasta": datetime.now(UTC) + timedelta(hours=4)}},
    )

    respuesta = await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))
    assert respuesta.status_code == 423


# ---------------------------------------------------------------------------
# Reportar
# ---------------------------------------------------------------------------


@sin_mongo
async def test_reportar_cierra_el_job(cliente, base, maquina_activa) -> None:
    await cola.encolar(base, tipo=cola.Tipo.LISTAR, maquina="mac-rocio")
    job = (await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))).json()

    respuesta = await cliente.post(
        f"/api/agente/jobs/{job['id']}/resultado",
        json={"ok": True, "raw": '{"chats": []}', "costo_usd": 0.03},
        headers=auth(maquina_activa.token),
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "listo"


@sin_mongo
async def test_una_maquina_no_puede_cerrar_el_job_de_otra(cliente, base, maquina_activa) -> None:
    """Sin esto, un token filtrado daría por enviado algo que no salió."""
    otra = await vendedores.dar_de_alta(base, maquina="mac-juan", nombre="Juan")
    job_id = await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio")

    respuesta = await cliente.post(
        f"/api/agente/jobs/{job_id}/resultado",
        json={"ok": True},
        headers=auth(otra.token),
    )
    assert respuesta.status_code == 404


@sin_mongo
async def test_reportar_un_job_id_que_no_es_un_id_da_404(cliente, maquina_activa) -> None:
    respuesta = await cliente.post(
        "/api/agente/jobs/no-es-un-objectid/resultado",
        json={"ok": True},
        headers=auth(maquina_activa.token),
    )
    assert respuesta.status_code == 404


@sin_mongo
async def test_un_selector_roto_aprieta_el_kill_switch(cliente, base, maquina_activa) -> None:
    """Si el DOM cambió, los envíos siguientes tienen el mismo problema."""
    job_id = await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio")
    await cola.tomar(base, "mac-rocio")

    respuesta = await cliente.post(
        f"/api/agente/jobs/{job_id}/resultado",
        json={"ok": False, "codigo": "SELECTOR_ROTO"},
        headers=auth(maquina_activa.token),
    )

    assert respuesta.json()["frena_corrida"] is True
    assert await configuracion.esta_pausado(base) is True


@sin_mongo
async def test_un_codigo_que_no_existe_lo_rechaza_el_esquema(cliente, base, maquina_activa) -> None:
    job_id = await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio")

    respuesta = await cliente.post(
        f"/api/agente/jobs/{job_id}/resultado",
        json={"ok": False, "codigo": "ME_LO_INVENTE"},
        headers=auth(maquina_activa.token),
    )
    assert respuesta.status_code == 422


@sin_mongo
async def test_el_enviar_entregado_trae_los_destinos_vigentes(
    cliente, base, maquina_activa
) -> None:
    """⚠️ R4, la segunda verificación, que hasta acá era imposible.

    El agente revalida `destinos_permitidos` antes de escribir. Pero nadie se los
    pasaba: no están en `PayloadEnviar` —y no deben estar, porque congelados al
    encolar mirarían lo mismo que la primera verificación— y no había endpoint
    que los devolviera. `enviar()` recibía `None`, que significa a nadie, y con
    eso la segunda verificación rechazaba todo.

    Ahora viajan en `vigente`, leídos **al entregar el job**. Ese es el momento
    que importa: entre encolar y entregar pueden pasar minutos, y alguien pudo
    cerrar la lista desde el panel.
    """
    from app.core import cola, configuracion

    await configuracion.actualizar(base, {"destinos_permitidos": ["+5491123231151"]})
    await cola.encolar(
        base,
        tipo=cola.Tipo.ENVIAR,
        maquina="mac-rocio",
        payload={
            "mensaje_id": str(ObjectId()),
            "contacto_id": "+5491123231151",
            "contacto_nombre": "Corralón",
            "texto": "hola",
            "modo": "prueba",
        },
    )

    entregado = (
        await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))
    ).json()

    assert entregado["vigente"]["destinos_permitidos"] == ["+5491123231151"]
    #  Y no se cuela en el payload, que es lo que el esquema valida.
    assert "destinos_permitidos" not in entregado["payload"]


@sin_mongo
async def test_un_reporte_con_borrador_no_marca_el_mensaje_como_enviado(
    cliente, base, maquina_activa
) -> None:
    """⚠️ D30: el bug que quemaba los borradores.

    Un ensayo terminaba en `ENVIADO`: se auditaba como enviado, consumía el
    tope diario, y esos mensajes ya no se podían enviar de verdad. Con el flag
    `borrador` en el reporte, terminan en `BORRADOR_DEJADO`.
    """
    from app.core import mensajes
    from app.core.estados import Estado

    corrida_id = ObjectId()
    mensaje_id = await mensajes.crear_borrador(
        base,
        corrida_id=corrida_id,
        maquina="mac-rocio",
        contacto_id="+5491123231151",
        contacto_nombre="Corralón",
        texto="hola, ¿seguimos?",
    )
    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA)
    await cola.encolar(
        base,
        tipo=cola.Tipo.ENVIAR,
        maquina="mac-rocio",
        corrida_id=corrida_id,
        payload={
            "mensaje_id": str(mensaje_id),
            "contacto_id": "+5491123231151",
            "contacto_nombre": "Corralón",
            "texto": "hola, ¿seguimos?",
            "modo": "prueba",
        },
    )
    #  Entregarlo lo marca ENVIANDO; el reporte con `borrador` lo resuelve.
    job = (await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))).json()
    respuesta = await cliente.post(
        f"/api/agente/jobs/{job['id']}/resultado",
        json={"ok": True, "raw": "hola, ¿seguimos?", "borrador": True},
        headers=auth(maquina_activa.token),
    )

    assert respuesta.status_code == 200
    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == str(Estado.BORRADOR_DEJADO)
    assert await base["auditoria"].find_one({"que": "borrador_dejado"}) is not None
    assert await base["auditoria"].find_one({"que": "mensaje_enviado"}) is None


@sin_mongo
async def test_lo_vigente_se_lee_al_entregar_y_no_al_encolar(cliente, base, maquina_activa) -> None:
    """Cerrar la lista desde el panel tiene efecto sobre lo ya encolado."""
    from app.core import cola, configuracion

    await configuracion.actualizar(base, {"destinos_permitidos": ["+5491123231151"]})
    await cola.encolar(
        base,
        tipo=cola.Tipo.ENVIAR,
        maquina="mac-rocio",
        payload={
            "mensaje_id": str(ObjectId()),
            "contacto_id": "+5491123231151",
            "contacto_nombre": "Corralón",
            "texto": "hola",
            "modo": "prueba",
        },
    )

    #  Alguien la cierra DESPUÉS de encolar y ANTES de que el agente lo tome.
    await configuracion.actualizar(base, {"destinos_permitidos": []})

    entregado = (
        await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))
    ).json()

    assert entregado["vigente"]["destinos_permitidos"] == []


@sin_mongo
async def test_los_otros_tipos_no_cargan_configuracion_de_mas(
    cliente, base, maquina_activa
) -> None:
    """Leerla en cada entrega sería una consulta por cada vuelta de cada máquina."""
    from app.core import cola

    await cola.encolar(base, tipo=cola.Tipo.DIAGNOSTICO, maquina="mac-rocio", payload={})

    entregado = (
        await cliente.get("/api/agente/jobs/proximo", headers=auth(maquina_activa.token))
    ).json()

    assert entregado["vigente"] == {}
