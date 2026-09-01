"""El pase único: armar tandas, registrar lo dejado, encadenar y caer al respaldo.

Lo central que se custodia acá: el reporte describe **hechos consumados** — los
borradores ya están en los chats cuando llega—, así que registrarlos no puede
fallar cerrado ni bloquear nada; la idempotencia la da la clave de `mensajes`;
y las listas del payload son R3 en su forma nueva: el backend calcula, el
modelo obedece.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app import db
from app.core import cola, configuracion, corridas, mensajes, pase_unico, vendedores
from app.core.esquema import inicializar
from app.core.estados import Estado
from app.main import app
from app.modelos.jobs import validar_payload

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

AHORA = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)


@pytest.fixture
async def base(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente_mongo = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    db_prueba = cliente_mongo[nombre]
    await inicializar(db_prueba)
    monkeypatch.setattr(db, "obtener_base", lambda: db_prueba)
    try:
        yield db_prueba
    finally:
        await cliente_mongo.drop_database(nombre)
        cliente_mongo.close()


@pytest.fixture
async def cliente():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://prueba") as http:
        yield http


async def maquina_activa(base, nombre: str = "mac-rocio"):
    alta = await vendedores.dar_de_alta(base, maquina=nombre, nombre="Rocío")
    await base["vendedores"].update_one(
        {"maquina": nombre},
        {"$set": {"activo": True, "acepto_condiciones_en": datetime.now(UTC)}},
    )
    return alta


def visitado(**cambios):
    base = {
        "contacto_nombre": "Corralón San Justo",
        "contacto_telefono": "+5491123231151",
        "ultimo_mensaje_resumen": "preguntó por hierro del 8",
        "quien_hablo_ultimo": "contacto",
        "antiguedad_dias": 6,
        "borrador_dejado": True,
        "texto_borrador": "Hola, quedó pendiente lo del hierro del 8. ¿Seguimos?",
        "motivo": None,
    }
    base.update(cambios)
    return base


def job_borradores(corrida_id, *, estado=cola.EstadoJob.LISTO, ya_vistos=None):
    return {
        "_id": ObjectId(),
        "tipo": str(cola.Tipo.BORRADORES),
        "maquina": "mac-rocio",
        "corrida_id": corrida_id,
        "payload": {"n_chats": 6, "run_id": str(corrida_id), "ya_vistos": ya_vistos or []},
        "estado": str(estado),
    }


# ---------------------------------------------------------------------------
# Armar el payload: las listas son datos (R3)
# ---------------------------------------------------------------------------


@sin_mongo
async def test_sin_destinos_no_hay_payload(base) -> None:
    """Lista vacía significa a nadie (R4): un pase que no puede dejar ningún
    borrador no se paga."""
    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )
    assert payload is None


@sin_mongo
async def test_con_asterisco_no_viaja_restriccion(base) -> None:
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload is not None
    assert payload["solo_numeros"] == []
    #  Y es un payload que el esquema acepta tal cual.
    validar_payload("BORRADORES", payload)


@sin_mongo
async def test_con_lista_concreta_los_numeros_viajan(base) -> None:
    await configuracion.actualizar(base, {"destinos_permitidos": ["+5491123231151"]})
    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["solo_numeros"] == ["+5491123231151"]


@sin_mongo
async def test_el_anti_duplicado_viaja_como_nombres_a_no_escribir(base) -> None:
    """El pase ve nombres en la lista de chats, así que el veto viaja por
    nombre. Un DESCARTADO no veta: esa decisión fue sobre un texto, no sobre
    la persona."""
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_vieja = ObjectId()
    reciente = await mensajes.crear_borrador(
        base,
        corrida_id=corrida_vieja,
        maquina="mac-rocio",
        contacto_id="+5491123231151",
        contacto_nombre="Corralón San Justo",
        texto="hola",
        ahora=AHORA - timedelta(days=2),
    )
    del reciente
    descartado = await mensajes.crear_borrador(
        base,
        corrida_id=corrida_vieja,
        maquina="mac-rocio",
        contacto_id="+5491199990000",
        contacto_nombre="Pinturería Sur",
        texto="chau",
        ahora=AHORA - timedelta(days=2),
    )
    from app.core.estados import Motivo

    await mensajes.mover(base, descartado, Estado.DESCARTADO, motivo=Motivo.VETADO)

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert "Corralón San Justo" in payload["no_escribir"]
    assert "Pinturería Sur" not in payload["no_escribir"]


# ---------------------------------------------------------------------------
# El barrido: la misma perilla y el mismo cursor que el circuito viejo (D27)
# ---------------------------------------------------------------------------


@sin_mongo
async def test_con_modo_lectura_barrido_el_payload_lleva_el_cursor(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"], "modo_lectura": "barrido"})
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"},
        {"$set": {"barrido": {"hasta_dias": 200, "ultima_tanda": ["Ferretería Sur"]}}},
    )

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["estrategia"] == "barrido"
    assert payload["barrido_hasta_dias"] == 200
    assert "Ferretería Sur" in payload["ya_vistos"]
    validar_payload("BORRADORES", payload)


@sin_mongo
async def test_sin_cursor_previo_el_barrido_arranca_de_3650(base) -> None:
    """Una máquina que nunca barrió: `hasta_dias` empieza en el techo, como el
    circuito viejo."""
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"], "modo_lectura": "barrido"})

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["barrido_hasta_dias"] == 3650


@sin_mongo
async def test_con_modo_lectura_recientes_no_hay_cursor_en_el_payload(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["estrategia"] == "recientes"
    assert "barrido_hasta_dias" not in payload


@sin_mongo
async def test_procesar_reporte_avanza_el_cursor_de_la_maquina(base) -> None:
    """El corazón del pedido del dueño: que el pase único recorra del más
    viejo al más nuevo, igual que hacía el circuito con Playwright."""
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"], "modo_lectura": "barrido"})
    job = job_borradores(ObjectId())
    job["payload"]["estrategia"] = "barrido"

    await pase_unico.procesar_reporte(
        base,
        job=job,
        detalle={
            "chats": [visitado(antiguedad_dias=400), visitado(antiguedad_dias=380)],
            "fin_de_ventana": False,
        },
        ahora=AHORA,
    )

    vendedor = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    #  El MÁS NUEVO de la tanda es el próximo "hasta": 380, no 400.
    assert vendedor["barrido"]["hasta_dias"] == 380
    assert vendedor["barrido"]["completado_en"] is None


@sin_mongo
async def test_fin_de_ventana_en_barrido_marca_el_historial_completado(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"], "modo_lectura": "barrido"})
    job = job_borradores(ObjectId())
    job["payload"]["estrategia"] = "barrido"

    await pase_unico.procesar_reporte(
        base,
        job=job,
        detalle={"chats": [visitado(antiguedad_dias=900)], "fin_de_ventana": True},
        ahora=AHORA,
    )

    vendedor = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert vendedor["barrido"]["completado_en"] is not None


@sin_mongo
async def test_en_recientes_el_cursor_no_se_toca(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"}, {"$set": {"barrido": {"hasta_dias": 200}}}
    )

    await pase_unico.procesar_reporte(
        base,
        job=job_borradores(ObjectId()),
        detalle={"chats": [visitado()], "fin_de_ventana": False},
        ahora=AHORA,
    )

    vendedor = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert vendedor["barrido"]["hasta_dias"] == 200, "no lo tocó una corrida en recientes"


@sin_mongo
async def test_una_tanda_fallida_igual_avanza_el_cursor(base) -> None:
    """Los chats parciales de una tanda que falló ya se recorrieron —varios con
    borrador dejado— y releerlos en el reintento sería trabajo perdido."""
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"], "modo_lectura": "barrido"})
    job = job_borradores(ObjectId(), estado=cola.EstadoJob.FALLIDO)
    job["payload"]["estrategia"] = "barrido"

    await pase_unico.procesar_reporte(
        base,
        job=job,
        detalle={"chats": [visitado(antiguedad_dias=500)]},
        ahora=AHORA,
    )

    vendedor = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert vendedor["barrido"]["hasta_dias"] == 500


def test_los_nombres_repetidos_no_gastan_el_tope() -> None:
    from app.core.pase_unico import _sin_repetidos

    assert _sin_repetidos(["A", "B", "A", "C", "B"]) == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Disparar: la perilla decide qué job sale
# ---------------------------------------------------------------------------


@sin_mongo
async def test_con_la_perilla_en_playwright_todo_sigue_igual(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})

    await corridas.disparar(base, quien="panel", tipo=corridas.TipoCorrida.GENERACION)

    tipos = await base["jobs"].distinct("tipo")
    assert tipos == [str(cola.Tipo.LISTAR)]


@sin_mongo
async def test_con_la_perilla_en_extension_sale_una_tanda(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(
        base, {"destinos_permitidos": ["*"], "modo_borrador": "extension"}
    )

    await corridas.disparar(base, quien="panel", tipo=corridas.TipoCorrida.GENERACION)

    job = await base["jobs"].find_one({"tipo": str(cola.Tipo.BORRADORES)})
    assert job is not None
    assert job["payload"]["n_chats"] == 6
    validar_payload("BORRADORES", job["payload"])


@sin_mongo
async def test_extension_sin_destinos_cae_al_circuito_de_siempre(base) -> None:
    """Destinos vacíos = a nadie (R4). El botón igual hace su recorrido normal
    —que tampoco va a escribirle a nadie— en vez de no hacer nada en silencio."""
    await maquina_activa(base)
    await configuracion.actualizar(base, {"modo_borrador": "extension"})

    await corridas.disparar(base, quien="panel", tipo=corridas.TipoCorrida.GENERACION)

    tipos = await base["jobs"].distinct("tipo")
    assert tipos == [str(cola.Tipo.LISTAR)]


# ---------------------------------------------------------------------------
# Procesar el reporte: hechos consumados, idempotentes
# ---------------------------------------------------------------------------


@sin_mongo
async def test_lo_dejado_queda_en_borrador_dejado_con_su_texto(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={"chats": [visitado()], "fin_de_ventana": True},
        ahora=AHORA,
    )

    assert len(procesado.registrados) == 1
    mensaje = await base["mensajes"].find_one({"_id": procesado.registrados[0]})
    assert mensaje["estado"] == str(Estado.BORRADOR_DEJADO)
    assert mensaje["texto"] == visitado()["texto_borrador"]
    assert mensaje["contacto_id"] == "+5491123231151"
    #  El número visto alimenta la memoria: la próxima corrida lo conoce.
    assert await base["telefonos"].find_one({"nombre": "Corralón San Justo"}) is not None


@sin_mongo
async def test_el_reporte_dos_veces_no_duplica_nada(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()
    detalle = {"chats": [visitado()], "fin_de_ventana": True}

    await pase_unico.procesar_reporte(
        base, job=job_borradores(corrida_id), detalle=detalle, ahora=AHORA
    )
    repetido = await pase_unico.procesar_reporte(
        base, job=job_borradores(corrida_id), detalle=detalle, ahora=AHORA
    )

    assert repetido.repetidos == 1
    assert await base["mensajes"].count_documents({"corrida_id": corrida_id}) == 1


@sin_mongo
async def test_un_chat_sin_numero_se_registra_por_nombre_sin_inventar(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(ObjectId()),
        detalle={"chats": [visitado(contacto_telefono=None)], "fin_de_ventana": True},
        ahora=AHORA,
    )

    mensaje = await base["mensajes"].find_one({"_id": procesado.registrados[0]})
    assert mensaje["contacto_id"] == "nombre:Corralón San Justo"


@sin_mongo
async def test_las_senales_de_guardrails_quedan_pero_no_bloquean(base) -> None:
    """El borrador YA está en el chat: bloquear el registro no lo des-escribe.
    La violación queda como señal para que alguien decida si va a borrarlo."""
    await maquina_activa(base)
    #  Destino restringido a OTRO número: G2 tendría que sonar.
    await configuracion.actualizar(base, {"destinos_permitidos": ["+5491100000000"]})

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(ObjectId()),
        detalle={"chats": [visitado()], "fin_de_ventana": True},
        ahora=AHORA,
    )

    assert len(procesado.registrados) == 1, "se registra igual"
    mensaje = await base["mensajes"].find_one({"_id": procesado.registrados[0]})
    assert mensaje["estado"] == str(Estado.BORRADOR_DEJADO)
    assert any("G2" in s for s in mensaje["senales"])


@sin_mongo
async def test_una_tanda_buena_encadena_la_siguiente_con_lo_visto(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id, ya_vistos=["Ferretería Sur"]),
        detalle={"chats": [visitado()], "fin_de_ventana": False},
        ahora=AHORA,
    )

    assert procesado.tanda_siguiente is not None
    siguiente = await base["jobs"].find_one({"_id": procesado.tanda_siguiente})
    assert siguiente["tipo"] == str(cola.Tipo.BORRADORES)
    assert "Ferretería Sur" in siguiente["payload"]["ya_vistos"]
    assert "Corralón San Justo" in siguiente["payload"]["ya_vistos"]
    #  Y el recién dejado entra al anti-duplicado de la tanda que sigue.
    assert "Corralón San Justo" in siguiente["payload"]["no_escribir"]


@sin_mongo
async def test_fin_de_ventana_termina_la_corrida(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    resultado = await base["corridas"].insert_one(
        {
            "tipo": str(corridas.TipoCorrida.GENERACION),
            "modo": "prueba",
            "estado": str(corridas.EstadoCorrida.GENERANDO),
            "maquinas": ["mac-rocio"],
            "creada_en": AHORA,
            "terminada_en": None,
        }
    )
    corrida_id = resultado.inserted_id

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={"chats": [visitado()], "fin_de_ventana": True},
        ahora=AHORA,
    )

    assert procesado.tanda_siguiente is None
    assert procesado.fin == "fin_de_ventana"
    corrida = await base["corridas"].find_one({"_id": corrida_id})
    assert corrida["estado"] == str(corridas.EstadoCorrida.TERMINADA)


@sin_mongo
async def test_el_tope_por_corrida_frena_el_encadenado(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"], "tope_por_corrida": 1})
    corrida_id = ObjectId()

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={"chats": [visitado()], "fin_de_ventana": False},
        ahora=AHORA,
    )

    assert procesado.tanda_siguiente is None


@sin_mongo
async def test_una_tanda_fallida_registra_lo_parcial_y_no_encadena(base) -> None:
    """Los borradores dejados antes del error ya están en WhatsApp: no
    registrarlos sería tener borradores que el panel no conoce. La continuación
    es de los reintentos del job (B2), no de una tanda nueva."""
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id, estado=cola.EstadoJob.FALLIDO),
        detalle={"chats": [visitado()]},
        ahora=AHORA,
    )

    assert len(procesado.registrados) == 1
    assert procesado.tanda_siguiente is None


# ---------------------------------------------------------------------------
# B3: el respaldo
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_respaldo_solo_corre_si_esta_configurado(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(
        base, {"destinos_permitidos": ["*"], "modo_borrador": "extension"}
    )

    encolado = await pase_unico.activar_respaldo(
        base, job=job_borradores(ObjectId(), estado=cola.EstadoJob.FALLIDO)
    )

    assert encolado is None


@sin_mongo
async def test_tras_un_texto_enviado_no_hay_respaldo_automatico(base) -> None:
    """Un texto salió enviado en vez de quedar escrito: ahí tiene que mirar
    una persona antes de que el sistema siga solo por ningún camino."""
    await maquina_activa(base)
    await configuracion.actualizar(
        base, {"destinos_permitidos": ["*"], "modo_borrador": "extension_con_respaldo"}
    )
    job = job_borradores(ObjectId(), estado=cola.EstadoJob.FALLIDO)
    job["codigo"] = str(cola.Codigo.TEXTO_ENVIADO)

    encolado = await pase_unico.activar_respaldo(base, job=job)

    assert encolado is None
    assert await base["jobs"].count_documents({"tipo": str(cola.Tipo.LISTAR)}) == 0


@sin_mongo
async def test_el_respaldo_encola_el_listar_una_sola_vez(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(
        base, {"destinos_permitidos": ["*"], "modo_borrador": "extension_con_respaldo"}
    )
    corrida_id = ObjectId()
    job = job_borradores(corrida_id, estado=cola.EstadoJob.FALLIDO)

    primero = await pase_unico.activar_respaldo(base, job=job)
    segundo = await pase_unico.activar_respaldo(base, job=job)

    assert primero is not None
    assert segundo is None
    assert await base["jobs"].count_documents({"tipo": str(cola.Tipo.LISTAR)}) == 1


# ---------------------------------------------------------------------------
# El código nuevo de la cola
# ---------------------------------------------------------------------------


def test_texto_enviado_no_se_reintenta() -> None:
    """Reintentar después de un envío accidental sería arriesgar otro."""
    assert cola.Codigo.TEXTO_ENVIADO.reintenta is False
    assert cola.Codigo.TEXTO_ENVIADO.frena_corrida is False


def test_borrador_puede_pasar_a_borrador_dejado() -> None:
    """La transición del pase único: el estado se pone al día con la realidad."""
    from app.core import estados

    assert estados.puede(Estado.BORRADOR, Estado.BORRADOR_DEJADO)


# ---------------------------------------------------------------------------
# De punta a punta, por el endpoint real
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@sin_mongo
async def test_el_reporte_del_agente_registra_y_encadena(base, cliente) -> None:
    alta = await maquina_activa(base)
    await configuracion.actualizar(
        base, {"destinos_permitidos": ["*"], "modo_borrador": "extension"}
    )
    disparo = await corridas.disparar(base, quien="panel", tipo=corridas.TipoCorrida.GENERACION)

    tomado = (await cliente.get("/api/agente/jobs/proximo", headers=_auth(alta.token))).json()
    assert tomado["tipo"] == str(cola.Tipo.BORRADORES)

    respuesta = await cliente.post(
        f"/api/agente/jobs/{tomado['id']}/resultado",
        json={
            "ok": True,
            "detalle": {
                "chats": [visitado()],
                "visitados": 1,
                "dejados": 1,
                "fin_de_ventana": False,
            },
            "raw": "{}",
        },
        headers=_auth(alta.token),
    )

    assert respuesta.status_code == 200
    mensaje = await base["mensajes"].find_one({"corrida_id": disparo.corrida_id})
    assert mensaje is not None
    assert mensaje["estado"] == str(Estado.BORRADOR_DEJADO)
    siguiente = await base["jobs"].find_one(
        {
            "corrida_id": disparo.corrida_id,
            "tipo": str(cola.Tipo.BORRADORES),
            "estado": str(cola.EstadoJob.PENDIENTE),
        }
    )
    assert siguiente is not None, "la tanda siguiente quedó encolada"
    assert "Corralón San Justo" in siguiente["payload"]["ya_vistos"]
