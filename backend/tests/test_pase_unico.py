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
    assert job["payload"]["n_chats"] == configuracion.POR_DEFECTO["chats_por_tanda"]
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


# ---------------------------------------------------------------------------
# El volumen (D39): tres topes, el más chico manda, y todos por máquina
# ---------------------------------------------------------------------------


async def _dejar(base, *, maquina: str, corrida_id, i: int, ahora=None):
    """Un borrador ya dejado, que es lo que los topes cuentan."""
    momento = ahora or AHORA
    mensaje_id = await mensajes.crear_borrador(
        base,
        corrida_id=corrida_id,
        maquina=maquina,
        contacto_id=f"+54911{abs(hash(maquina)) % 100:02d}{i:05d}",
        contacto_nombre=f"Cliente {i:03d}",
        texto="Hola, quedó pendiente lo que hablamos. ¿Seguimos?",
        resumen_ultimo="cotización",
        quien_hablo_ultimo="contacto",
        antiguedad_dias=5,
        ahora=momento,
    )
    await mensajes.mover(base, mensaje_id, Estado.BORRADOR_DEJADO, quien=maquina, ahora=momento)
    return mensaje_id


@sin_mongo
async def test_llegar_a_n_chats_sin_fin_de_ventana_encadena(base) -> None:
    """Lo que estaba roto: una tanda llena no es el final del recorrido.

    El prompt marcaba `fin_de_ventana: true` al llegar a `n_chats` porque no le
    decíamos cuándo va `false`, y la corrida terminaba en verde con una sola
    tanda. Ése es el bug de los seis borradores.
    """
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={"chats": [visitado()], "fin_de_ventana": False},
        ahora=AHORA,
    )

    assert procesado.tanda_siguiente is not None
    assert procesado.fin is None


@sin_mongo
async def test_el_tope_diario_frena_el_encadenado(base) -> None:
    """El número que el dueño configura: veinte por día, y basta.

    Vale **entre** corridas, que es lo que lo distingue del tope por corrida:
    dos corridas en la misma tarde no dejan el doble.
    """
    await maquina_activa(base)
    await configuracion.actualizar(
        base, {"destinos_permitidos": ["*"], "tope_diario_borradores": 3}
    )
    corrida_id = ObjectId()
    for i in range(3):
        #  De OTRA corrida, del mismo día: el tope diario los ve igual.
        await _dejar(base, maquina="mac-rocio", corrida_id=ObjectId(), i=i)

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={"chats": [visitado()], "fin_de_ventana": False},
        ahora=AHORA,
    )

    assert procesado.tanda_siguiente is None
    assert procesado.fin == "tope_diario_borradores"


@sin_mongo
async def test_el_tope_de_tandas_corta_aunque_sobre_presupuesto(base) -> None:
    """El único tope que frena una cadena de tandas que no deja nada.

    Una tanda que visita chats y los saltea a todos —campo ocupado, sin tema—
    no mueve los topes de borradores. Sin éste, encadenaría hasta que el modelo
    se quedara sin chats.
    """
    await maquina_activa(base)
    await configuracion.actualizar(
        base,
        {"destinos_permitidos": ["*"], "tope_diario_borradores": 50, "max_tandas_por_maquina": 1},
    )
    corrida_id = ObjectId()
    job = job_borradores(corrida_id)
    await base["jobs"].insert_one(
        {
            "_id": job["_id"],
            "corrida_id": corrida_id,
            "maquina": "mac-rocio",
            "tipo": str(cola.Tipo.BORRADORES),
            "estado": str(cola.EstadoJob.LISTO),
        }
    )

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job,
        detalle={"chats": [visitado(borrador_dejado=False, motivo="campo_ocupado")]},
        ahora=AHORA,
    )

    assert procesado.tanda_siguiente is None
    assert procesado.fin == "tope_de_tandas"


@sin_mongo
async def test_una_maquina_no_se_come_el_presupuesto_de_la_otra(base) -> None:
    """Los topes son por máquina.

    Un pozo común hace que la primera Mac que reporta se lo lleve y las demás
    queden con tandas recortadas sin que nadie lo haya decidido — y el dueño
    que pide veinte por día los pide para cada vendedor, no entre todos.
    """
    await maquina_activa(base)
    await maquina_activa(base, "mac-diego")
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"], "tope_por_corrida": 2})
    corrida_id = ObjectId()
    for i in range(2):
        await _dejar(base, maquina="mac-diego", corrida_id=corrida_id, i=i)

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={"chats": [visitado()], "fin_de_ventana": False},
        ahora=AHORA,
    )

    assert procesado.tanda_siguiente is not None, "mac-rocio tiene su propio presupuesto"


@sin_mongo
async def test_la_ultima_tanda_se_achica_para_no_pasar_el_tope(base) -> None:
    """`n_chats` ES el tope de la tanda: el modelo frena al llegar.

    El presupuesto sólo **achica**, nunca agranda: `chats_por_tanda` sigue
    siendo el tamaño de la tanda, y lo que queda del día es el techo de la
    última. Con 4 del día y 1 ya dejado, la que viene pide 3 y no 6.
    """
    await maquina_activa(base)
    await configuracion.actualizar(
        base,
        {"destinos_permitidos": ["*"], "tope_diario_borradores": 4, "chats_por_tanda": 6},
    )
    corrida_id = ObjectId()

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={"chats": [visitado()], "fin_de_ventana": False},
        ahora=AHORA,
    )

    tanda = await base["jobs"].find_one({"_id": procesado.tanda_siguiente})
    assert tanda["payload"]["n_chats"] == 3, "quedan 3 del día, aunque la tanda sea de 6"


@sin_mongo
async def test_cada_tanda_deja_su_renglon_en_la_corrida(base) -> None:
    """Para que el panel pueda decir por qué salieron N y no más."""
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

    await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={"chats": [visitado()], "fin_de_ventana": True},
        ahora=AHORA,
    )

    corrida = await base["corridas"].find_one({"_id": corrida_id})
    assert corrida["tandas"] == [
        {
            "maquina": "mac-rocio",
            "pedidos": 6,
            "dejados": 1,
            "salteados": 0,
            "motivos": {},
            "vetados": 0,
            "corte": "otro",
            "fin": "fin_de_ventana",
            "error": None,
        }
    ]


@sin_mongo
async def test_no_escribir_conserva_a_los_mas_recientes_al_truncar(base) -> None:
    """El bug que se agranda con volumen: la lista se cortaba por abecedario.

    Pasando de la cota, los nombres del final del alfabeto se caían en silencio
    y esas personas recibían un segundo borrador. Ahora el que se cae es el que
    se contactó hace más días, que es el que está por salir de la ventana igual.
    """
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    cuantos = pase_unico.MAX_NO_ESCRIBIR + 10

    for i in range(cuantos):
        #  El de índice más alto es el más reciente **y** el último del
        #  abecedario: con el orden viejo se caía justo el que hay que proteger.
        await _dejar(
            base,
            maquina="mac-rocio",
            corrida_id=ObjectId(),
            i=i,
            ahora=AHORA - timedelta(hours=cuantos - i),
        )

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert len(payload["no_escribir"]) == pase_unico.MAX_NO_ESCRIBIR
    assert f"Cliente {cuantos - 1:03d}" in payload["no_escribir"], "el más reciente no se cae"
    assert "Cliente 000" not in payload["no_escribir"], "el más viejo es el que se cae"
    #  Y la cota dura del esquema tiene que dejar pasar la lista larga.
    validar_payload("BORRADORES", payload)


# ---------------------------------------------------------------------------
# La redacción con reglas del dueño (D40, D41, D44)
# ---------------------------------------------------------------------------


@sin_mongo
async def test_las_reglas_del_dueno_viajan_en_el_payload(base) -> None:
    """Datos, no prompt: el modelo obedece la lista que el dueño escribió."""
    await configuracion.actualizar(
        base,
        {
            "destinos_permitidos": ["*"],
            "max_visitas_por_tanda": 15,
            "mensaje_post_compra": False,
            "frases_prohibidas": ["sigue en pie", " sigue en pie ", "", "quedo a disposicion"],
            "palabras_veto_chat": ["estafa"],
        },
    )

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["max_visitas"] == 15
    assert payload["mensaje_post_compra"] is False
    #  Sin repetidos ni vacíos: cada renglón del prompt cuesta.
    assert payload["frases_prohibidas"] == ["sigue en pie", "quedo a disposicion"]
    assert payload["palabras_veto"] == ["estafa"]
    validar_payload("BORRADORES", payload)


@sin_mongo
async def test_las_reglas_por_defecto_pasan_el_esquema_del_payload(base) -> None:
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["max_visitas"] == 20
    assert payload["mensaje_post_compra"] is True
    assert "sigue en pie" in payload["frases_prohibidas"]
    assert "no me interesa" in payload["palabras_veto"]
    validar_payload("BORRADORES", payload)


@sin_mongo
async def test_el_anclaje_se_guarda_con_el_borrador(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()

    await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={
            "chats": [visitado(tema="hierro del 8", cita="me pasas precio del hierro del 8?")]
        },
        ahora=AHORA,
    )

    mensaje = await base["mensajes"].find_one({"corrida_id": corrida_id})
    assert mensaje["tema"] == "hierro del 8"
    assert mensaje["cita"] == "me pasas precio del hierro del 8?"
    assert mensaje["senales"] == []


@sin_mongo
async def test_las_senales_de_redaccion_quedan_en_el_mensaje_sin_bloquear(base) -> None:
    """El borrador ya está en WhatsApp: la señal marca la fila, no lo des-escribe."""
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()

    resultado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={
            "chats": [
                visitado(
                    texto_borrador="Estimado, sigue en pie esa necesidad?",
                    ultimo_mensaje_resumen="hizo un reclamo por la entrega",
                    tema="entrega",
                    cita=None,
                )
            ]
        },
        ahora=AHORA,
    )

    assert len(resultado.registrados) == 1
    mensaje = await base["mensajes"].find_one({"corrida_id": corrida_id})
    assert mensaje["estado"] == str(Estado.BORRADOR_DEJADO)
    assert mensaje["senales"][0] == "CHAT_DISCONFORME"
    assert {"SIN_ANCLAJE", "TONO_FORMAL"} <= set(mensaje["senales"])


@sin_mongo
async def test_el_post_venta_se_registra_con_su_motivo(base) -> None:
    """D41: el mensaje queda, y la venta cerrada queda dicha en el reporte."""
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()

    resultado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={
            "chats": [
                visitado(
                    texto_borrador="Hola, vi que al final lo compraste. Te falto algo?",
                    ultimo_mensaje_resumen="ya compró y pidió la factura",
                    motivo="ya_compro",
                )
            ]
        },
        ahora=AHORA,
    )

    assert len(resultado.registrados) == 1
    assert resultado.salteados == 0
    mensaje = await base["mensajes"].find_one({"corrida_id": corrida_id})
    assert mensaje["senales"] == [], "un post-venta que menciona la factura no es un conflicto"


@sin_mongo
async def test_cada_tanda_cuenta_sus_motivos_y_su_corte(base) -> None:
    """Lo que distingue «el prompt se puso estricto» de «el recorrido se rompió»."""
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

    def salteado(nombre, motivo):
        return visitado(
            contacto_nombre=nombre, borrador_dejado=False, texto_borrador=None, motivo=motivo
        )

    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={
            "chats": [
                visitado(),
                salteado("Enojado", "disconforme"),
                salteado("Otro enojado", "disconforme"),
                salteado("Ya compró", "ya_compro"),
                salteado("Ocupado", "campo_ocupado"),
            ],
            "fin_de_ventana": False,
            "corte": "tope_de_visitas",
        },
        ahora=AHORA,
    )

    assert procesado.motivos == {"disconforme": 2, "ya_compro": 1, "campo_ocupado": 1}
    assert procesado.corte == "tope_de_visitas"
    corrida = await base["corridas"].find_one({"_id": corrida_id})
    assert corrida["tandas"][0]["motivos"] == procesado.motivos
    assert corrida["tandas"][0]["corte"] == "tope_de_visitas"


# ---------------------------------------------------------------------------
# De atrás para adelante, con cursor de ventana (D43)
# ---------------------------------------------------------------------------


@sin_mongo
async def test_por_defecto_el_orden_es_el_de_siempre_y_no_hay_cursor(base) -> None:
    """La migración no cambia nada hasta que alguien toque el switch."""
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["orden"] == "mas_nuevos_primero"
    assert "ventana_hasta_dias" not in payload
    validar_payload("BORRADORES", payload)


@sin_mongo
async def test_del_mas_viejo_hacia_hoy_sin_cursor_arranca_del_extremo_viejo(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(
        base,
        {
            "destinos_permitidos": ["*"],
            "orden_recorrido": "mas_viejos_primero",
            "antiguedad_min_dias": 21,
            "antiguedad_max_dias": 90,
        },
    )
    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["orden"] == "mas_viejos_primero"
    assert payload["ventana_hasta_dias"] == 90
    assert payload["antiguedad_min_dias"] == 21
    validar_payload("BORRADORES", payload)


@sin_mongo
async def test_el_cursor_de_la_ventana_viaja_con_su_frontera(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(
        base, {"destinos_permitidos": ["*"], "orden_recorrido": "mas_viejos_primero"}
    )
    await vendedores.registrar_ventana(
        base, "mac-rocio", hasta_dias=55, tanda=["Frontera"], completado=False, ahora=AHORA
    )

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ya_vistos=["De esta"], ahora=AHORA
    )

    assert payload["ventana_hasta_dias"] == 55
    assert payload["ya_vistos"] == ["Frontera", "De esta"]


@sin_mongo
async def test_el_cursor_de_la_ventana_no_pasa_del_maximo_si_el_dueno_lo_bajo(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(
        base,
        {
            "destinos_permitidos": ["*"],
            "orden_recorrido": "mas_viejos_primero",
            "antiguedad_max_dias": 40,
        },
    )
    await vendedores.registrar_ventana(
        base, "mac-rocio", hasta_dias=80, tanda=[], completado=False, ahora=AHORA
    )

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["ventana_hasta_dias"] == 40


@sin_mongo
async def test_procesar_reporte_avanza_el_cursor_de_la_ventana(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()
    job = job_borradores(corrida_id)
    job["payload"]["orden"] = "mas_viejos_primero"

    await pase_unico.procesar_reporte(
        base,
        job=job,
        detalle={
            "chats": [
                visitado(contacto_nombre="Viejo", antiguedad_dias=80),
                visitado(contacto_nombre="Menos viejo", antiguedad_dias=62),
            ],
            "fin_de_ventana": False,
        },
        ahora=AHORA,
    )

    vendedor = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert vendedor["ventana"]["hasta_dias"] == 62
    assert vendedor["ventana"]["ultima_tanda"] == ["Viejo", "Menos viejo"]
    assert vendedor["ventana"]["completado_en"] is None
    #  El de barrido no se toca: son dos recorridos distintos.
    assert "barrido" not in vendedor


@sin_mongo
async def test_al_llegar_al_minimo_la_ventana_vuelve_a_empezar(base) -> None:
    """Un barrido terminado se queda terminado; una ventana terminada reempieza."""
    await maquina_activa(base)
    await configuracion.actualizar(
        base, {"destinos_permitidos": ["*"], "orden_recorrido": "mas_viejos_primero"}
    )
    await vendedores.registrar_ventana(
        base, "mac-rocio", hasta_dias=40, tanda=["Anterior"], completado=False, ahora=AHORA
    )
    corrida_id = ObjectId()
    job = job_borradores(corrida_id)
    job["payload"]["orden"] = "mas_viejos_primero"

    await pase_unico.procesar_reporte(
        base,
        job=job,
        detalle={"chats": [visitado(antiguedad_dias=22)], "fin_de_ventana": True},
        ahora=AHORA,
    )

    vendedor = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert "hasta_dias" not in vendedor["ventana"]
    assert vendedor["ventana"]["completado_en"] == AHORA
    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )
    assert payload["ventana_hasta_dias"] == 90, "la próxima arranca del extremo viejo"
    assert payload["ya_vistos"] == ["Corralón San Justo"], "la frontera sigue valiendo"


@sin_mongo
async def test_en_orden_de_siempre_el_cursor_de_la_ventana_no_se_toca(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    await pase_unico.procesar_reporte(
        base,
        job=job_borradores(ObjectId()),
        detalle={"chats": [visitado(antiguedad_dias=30)]},
        ahora=AHORA,
    )

    vendedor = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert "ventana" not in vendedor


@sin_mongo
async def test_ya_vistos_conserva_ciento_veinte(base) -> None:
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    payload = await pase_unico.armar_payload(
        base,
        corrida_id=ObjectId(),
        maquina="mac-rocio",
        ya_vistos=[f"Visto {i:03d}" for i in range(150)],
        ahora=AHORA,
    )

    assert len(payload["ya_vistos"]) == 120
    assert payload["ya_vistos"][-1] == "Visto 149"
    validar_payload("BORRADORES", payload)


# ---------------------------------------------------------------------------
# No repetir números ni chats (D43)
# ---------------------------------------------------------------------------


@sin_mongo
async def test_los_numeros_con_mensaje_reciente_viajan_aparte(base) -> None:
    """Las listas por nombre no ven que "Juan" y "Juan Ferretería" son la misma
    persona: el número sí, y se compara al abrir el chat."""
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()
    await _dejar(base, maquina="mac-rocio", corrida_id=corrida_id, i=1)
    #  Uno por nombre, sin número: no entra en la lista de números.
    await mensajes.crear_borrador(
        base,
        corrida_id=corrida_id,
        maquina="mac-rocio",
        contacto_id="nombre:Sin Número",
        contacto_nombre="Sin Número",
        texto="Hola",
        ahora=AHORA,
    )
    #  Un vetado con número (D42) también.
    await base["vetados"].insert_one(
        {
            "maquina": "mac-rocio",
            "clave": "+5491199999999",
            "nombre": "Enojado",
            "motivo": "disconforme",
            "actualizado_en": AHORA,
            "vence_en": AHORA + timedelta(days=300),
        }
    )

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )

    assert payload["no_escribir_numeros"][0] == "+5491199999999", "los vetados van primero"
    assert any(
        n.startswith("+54911") and n != "+5491199999999" for n in payload["no_escribir_numeros"]
    )
    assert not any(n.startswith("nombre:") for n in payload["no_escribir_numeros"])
    validar_payload("BORRADORES", payload)


@sin_mongo
async def test_un_segundo_borrador_a_la_misma_persona_se_registra_con_senal(base) -> None:
    """El borrador está en WhatsApp: esconderlo del panel sería peor que el duplicado."""
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()

    await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={"chats": [visitado(contacto_nombre="Juan")]},
        ahora=AHORA,
    )
    procesado = await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={
            "chats": [
                visitado(
                    contacto_nombre="Juan Ferretería",
                    texto_borrador="Hola Juan, seguis con lo del hierro?",
                )
            ]
        },
        ahora=AHORA,
    )

    assert procesado.repetidos_por_numero == 1
    assert len(procesado.registrados) == 1
    segundo = await base["mensajes"].find_one({"contacto_nombre": "Juan Ferretería"})
    assert segundo["estado"] == str(Estado.BORRADOR_DEJADO)
    assert "NUMERO_REPETIDO" in segundo["senales"]
    primero = await base["mensajes"].find_one({"contacto_nombre": "Juan"})
    assert "NUMERO_REPETIDO" not in primero["senales"]


@sin_mongo
async def test_cada_chat_abierto_queda_en_la_memoria_de_visitas(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})

    await pase_unico.procesar_reporte(
        base,
        job=job_borradores(ObjectId()),
        detalle={
            "chats": [
                visitado(contacto_nombre="Con borrador"),
                visitado(
                    contacto_nombre="Salteado",
                    borrador_dejado=False,
                    texto_borrador=None,
                    motivo="campo_ocupado",
                ),
            ]
        },
        ahora=AHORA,
    )

    visitas = {v["nombre"]: v async for v in base["visitas"].find({"maquina": "mac-rocio"})}
    assert set(visitas) == {"Con borrador", "Salteado"}
    assert visitas["Salteado"]["dejado"] is False
    assert visitas["Salteado"]["motivo"] == "campo_ocupado"


@sin_mongo
async def test_la_memoria_de_visitas_entra_a_ya_vistos_y_vence(base) -> None:
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    await base["visitas"].insert_many(
        [
            {"maquina": "mac-rocio", "nombre": "Reciente", "visto_en": AHORA - timedelta(days=2)},
            {"maquina": "mac-rocio", "nombre": "Vencida", "visto_en": AHORA - timedelta(days=45)},
            {"maquina": "mac-sofia", "nombre": "De otra", "visto_en": AHORA},
        ]
    )

    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ya_vistos=["De esta"], ahora=AHORA
    )

    assert payload["ya_vistos"] == ["Reciente", "De esta"]


@sin_mongo
async def test_al_truncar_ya_vistos_se_pierde_la_memoria_y_no_la_corrida(base) -> None:
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    await base["visitas"].insert_many(
        [
            {
                "maquina": "mac-rocio",
                "nombre": f"Memoria {i:03d}",
                "visto_en": AHORA - timedelta(hours=i),
            }
            for i in range(110)
        ]
    )

    payload = await pase_unico.armar_payload(
        base,
        corrida_id=ObjectId(),
        maquina="mac-rocio",
        ya_vistos=[f"Corrida {i:02d}" for i in range(20)],
        ahora=AHORA,
    )

    assert len(payload["ya_vistos"]) == 120
    assert all(f"Corrida {i:02d}" in payload["ya_vistos"] for i in range(20))
    assert "Memoria 000" in payload["ya_vistos"], "la más nueva de la memoria queda"
    assert "Memoria 109" not in payload["ya_vistos"], "la más vieja se cae primero"


@sin_mongo
async def test_la_oferta_post_venta_viaja_recortada_y_vacia_por_defecto(base) -> None:
    """Preparado y apagado: de fábrica no viaja nada, y con texto viaja limpio."""
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )
    assert payload["post_venta_ofrecer"] == ""
    validar_payload("BORRADORES", payload)

    await configuracion.actualizar(base, {"post_venta_ofrecer": "  10% en accesorios  "})
    payload = await pase_unico.armar_payload(
        base, corrida_id=ObjectId(), maquina="mac-rocio", ahora=AHORA
    )
    assert payload["post_venta_ofrecer"] == "10% en accesorios"
    validar_payload("BORRADORES", payload)


@sin_mongo
async def test_un_borrador_sobre_una_venta_cerrada_queda_marcado_como_post_venta(base) -> None:
    await maquina_activa(base)
    await configuracion.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = ObjectId()
    post_venta = visitado(
        motivo="ya_compro",
        contacto_nombre="Ada",
        contacto_telefono="+5491155667788",
        texto_borrador="Hola Ada, vi que al final lo compraste. Quedó todo bien?",
    )

    await pase_unico.procesar_reporte(
        base,
        job=job_borradores(corrida_id),
        detalle={"chats": [visitado(), post_venta]},
        ahora=AHORA,
    )

    por_nombre = {
        m["contacto_nombre"]: m async for m in base["mensajes"].find({"corrida_id": corrida_id})
    }
    assert por_nombre["Ada"]["post_venta"] is True
    assert all(m["post_venta"] is False for n, m in por_nombre.items() if n != "Ada")
