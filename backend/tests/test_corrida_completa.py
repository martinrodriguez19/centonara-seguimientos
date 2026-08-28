"""Una corrida entera, por los endpoints, como la va a hacer un agente real.

Los tests de `test_generacion.py` prueban las dos piezas nuevas por separado.
Este prueba que estén **enchufadas**: que un `LISTAR` reportado produzca jobs de
`REDACTAR` de verdad, que el agente los reciba de la cola, y que reportarlos
termine en borradores que la validación mueve a donde corresponde.

Es el test que faltaba desde el principio y que nadie podía escribir, porque el
backend no conectaba una punta con la otra: el resultado de un `LISTAR` se
guardaba y no lo leía nadie.

No hay ningún navegador ni ningún modelo acá. Se simula lo que el agente
reporta, que es exactamente lo que devuelven `jobs/listar.py` y
`jobs/redactar.py` — sus formas están probadas del otro lado.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app import db
from app.core import cola, configuracion, corridas, validacion, vendedores
from app.core.esquema import inicializar
from app.core.estados import Estado
from app.main import app

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

PERMITIDO = "+5491123231151"
OTRO_PERMITIDO = "+5491136007586"
AJENO = "+5491155550000"


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://prueba") as c:
        yield c


@pytest.fixture
async def maquina(base):
    alta = await vendedores.dar_de_alta(base, maquina="pc-1", nombre="Prueba")
    await base["vendedores"].update_one(
        {"maquina": "pc-1"},
        {"$set": {"activo": True, "acepto_condiciones_en": datetime.now(UTC)}},
    )
    await configuracion.actualizar(base, {"destinos_permitidos": [PERMITIDO, OTRO_PERMITIDO]})
    return alta


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def chats() -> list[dict]:
    """Lo que devuelve `jobs/listar.py`, con los tres casos que importan."""
    return [
        {
            "contacto_nombre": "Corralón San Justo",
            "contacto_telefono": PERMITIDO,
            "ultimo_mensaje_resumen": "preguntó por hierro del 8",
            "quien_hablo_ultimo": "contacto",
            "antiguedad_dias": 6,
        },
        {
            "contacto_nombre": "Obra Ramos",
            "contacto_telefono": OTRO_PERMITIDO,
            "ultimo_mensaje_resumen": "quedó en pasar por el depósito",
            "quien_hablo_ultimo": "vendedor",
            "antiguedad_dias": 3,
        },
        #  No está en destinos permitidos: no se redacta y no se paga por él.
        {
            "contacto_nombre": "Ferretería del Norte",
            "contacto_telefono": AJENO,
            "ultimo_mensaje_resumen": "pidió presupuesto de cemento",
            "quien_hablo_ultimo": "contacto",
            "antiguedad_dias": 10,
        },
        #  El modelo no pudo leer el teléfono y se negó a deducirlo.
        {
            "contacto_nombre": "Pintureria Sur",
            "contacto_telefono": None,
            "ultimo_mensaje_resumen": "consultó por látex",
            "quien_hablo_ultimo": "contacto",
            "antiguedad_dias": 2,
        },
    ]


async def tomar(http, token: str) -> dict | None:
    respuesta = await http.get("/api/agente/jobs/proximo", headers=auth(token))
    return None if respuesta.status_code == 204 else respuesta.json()


async def reportar(http, token: str, job_id: str, **cuerpo) -> None:
    cuerpo.setdefault("detalle", {})
    respuesta = await http.post(
        f"/api/agente/jobs/{job_id}/resultado", json={"ok": True, **cuerpo}, headers=auth(token)
    )
    assert respuesta.status_code == 200, respuesta.text


@sin_mongo
async def test_de_apretar_el_boton_a_borradores_en_los_chats(http, base, maquina) -> None:
    """El recorrido entero, por los endpoints — el flujo de un paso (D36).

    panel -> LISTAR -> N REDACTAR -> (encadenado) ENVIAR prueba -> BORRADOR_DEJADO

    Nadie aprieta un segundo botón: cada redacción limpia se encola sola para
    quedar como borrador en el chat.
    """
    #  Sin pausas entre envíos: el test no puede adelantar el reloj del
    #  endpoint, y lo que se prueba es el circuito, no el espaciado (que tiene
    #  sus propios tests en test_cola).
    await configuracion.actualizar(base, {"pausa_entre_envios_s": [0, 0]})
    disparo = await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=10)
    corrida_id = disparo.corrida_id

    # 1. El agente pide trabajo y le toca el LISTAR.
    job = await tomar(http, maquina.token)
    assert job["tipo"] == "LISTAR"
    assert job["payload"]["n_chats"] == 10

    # 2. Lo reporta con lo que "leyó" del navegador.
    await reportar(
        http, maquina.token, job["id"], detalle={"chats": chats(), "leidos": 4}, costo_usd=0.43
    )

    # 3. Y ahora hay dos REDACTAR esperando: uno por cada chat al que se le
    #    puede escribir. Los otros dos no se redactan y no se pagan.
    pendientes = await base["jobs"].count_documents({"tipo": str(cola.Tipo.REDACTAR)})
    assert pendientes == 2

    # 4. El agente va tomando lo que sigue. En el medio aparece el RESOLVER del
    #    chat sin teléfono, y —apenas cada texto se reporta— el ENVIAR en modo
    #    prueba que el encadenado dejó listo: doce pasos, sin apretar enviar.
    textos = {}
    dejados = []
    while (siguiente := await tomar(http, maquina.token)) is not None:
        if siguiente["tipo"] == "RESOLVER":
            assert siguiente["payload"]["contactos"] == ["Pintureria Sur"]
            await reportar(
                http,
                maquina.token,
                siguiente["id"],
                detalle={
                    "contactos": [
                        {
                            "nombre": "Pintureria Sur",
                            "telefono": None,
                            "motivo": "numero_no_legible",
                        }
                    ]
                },
            )
            continue
        if siguiente["tipo"] == "ENVIAR":
            assert siguiente["payload"]["modo"] == "prueba", "el encadenado nunca envía de verdad"
            dejados.append(siguiente["payload"]["contacto_id"])
            await reportar(
                http,
                maquina.token,
                siguiente["id"],
                borrador=True,
                raw=siguiente["payload"]["texto"],
            )
            continue
        assert siguiente["tipo"] == "REDACTAR"
        #  El payload no lleva teléfono: `REDACTAR` no envía nada.
        assert "contacto_id" not in siguiente["payload"]
        texto = f"Hola {siguiente['payload']['contacto_nombre']}, ¿seguimos?"
        textos[siguiente["payload"]["contacto_nombre"]] = texto
        await reportar(
            http,
            maquina.token,
            siguiente["id"],
            detalle={"status": "ok", "texto": texto},
            costo_usd=0.002,
        )

    assert len(textos) == 2
    assert sorted(dejados) == sorted([PERMITIDO, OTRO_PERMITIDO])

    # 5. Los mensajes terminaron como borradores EN LOS CHATS, sin que nadie
    #    apretara nada más que "generar".
    finales = await base["mensajes"].find().to_list(None)
    assert len(finales) == 2
    assert {m["estado"] for m in finales} == {str(Estado.BORRADOR_DEJADO)}

    # 6. La corrida quedó en enviando (lo puso el primer encadenado) y la
    #    auditoría dice que fue el modo automático.
    corrida = await base["corridas"].find_one({"_id": corrida_id})
    assert corrida["estado"] == "enviando"
    evento = await base["auditoria"].find_one({"detalle.accion": "borradores_automaticos"})
    assert evento is not None

    # 7. Y la validación por tanda —que quedó como red manual— no tiene nada
    #    que hacer: no quedó ningún BORRADOR.
    resultado = await validacion.validar_corrida(base, corrida_id)
    assert resultado.total == 0


@sin_mongo
async def test_un_chat_sin_contexto_llega_al_panel_y_no_se_pierde(http, base, maquina) -> None:
    """El modelo se negó a inventar. Ese chat tiene que quedar a la vista."""
    disparo = await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=5)

    job = await tomar(http, maquina.token)
    await reportar(http, maquina.token, job["id"], detalle={"chats": chats()[:1]})

    redactar = await tomar(http, maquina.token)
    await reportar(
        http,
        maquina.token,
        redactar["id"],
        detalle={"status": "sin_contexto", "motivo": "es una charla personal"},
    )

    mensaje = await base["mensajes"].find_one({})
    assert mensaje["estado"] == str(Estado.RETENIDO)
    assert "SIN_CONTEXTO" in mensaje["senales"]

    # Y la validación no lo toca: no es un borrador pendiente de reglas.
    resultado = await validacion.validar_corrida(base, disparo.corrida_id)
    assert resultado.total == 0
    assert mensaje["estado"] == str(Estado.RETENIDO)


@sin_mongo
async def test_sin_destinos_permitidos_no_se_redacta_nada(http, base, maquina) -> None:
    """⚠️ R4 de punta a punta: lista vacía significa a nadie.

    No es sólo que no se envíe: es que **no se paga por redactar** mensajes que
    nunca iban a poder salir.
    """
    await configuracion.actualizar(base, {"destinos_permitidos": []})
    await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=5)

    job = await tomar(http, maquina.token)
    await reportar(http, maquina.token, job["id"], detalle={"chats": chats()})

    assert await base["jobs"].count_documents({"tipo": str(cola.Tipo.REDACTAR)}) == 0
    assert await tomar(http, maquina.token) is None


@sin_mongo
async def test_un_listar_fallido_no_encola_nada(http, base, maquina) -> None:
    """La sesión se cayó a mitad. No hay chats, no hay redacciones."""
    await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=5)

    job = await tomar(http, maquina.token)
    respuesta = await http.post(
        f"/api/agente/jobs/{job['id']}/resultado",
        json={"ok": False, "codigo": "SESION_CAIDA", "detalle": {"motivo": "sesion_no_iniciada"}},
        headers=auth(maquina.token),
    )
    assert respuesta.status_code == 200

    assert await base["jobs"].count_documents({"tipo": str(cola.Tipo.REDACTAR)}) == 0


@sin_mongo
async def test_el_costo_de_cada_job_queda_registrado(http, base, maquina) -> None:
    """Es de donde sale el costo por mensaje, que decide si el proyecto sirve."""
    await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=5)

    job = await tomar(http, maquina.token)
    await reportar(http, maquina.token, job["id"], detalle={"chats": chats()[:1]}, costo_usd=0.43)

    redactar = await tomar(http, maquina.token)
    await reportar(
        http,
        maquina.token,
        redactar["id"],
        detalle={"status": "ok", "texto": "Hola"},
        costo_usd=0.002,
    )

    guardados = await base["jobs"].find().to_list(None)
    #  La vuelta al navegador cuesta ~200 veces lo que redactar. Es el motivo
    #  entero por el que `REDACTAR` no abre el navegador.
    assert sum(j["costo_usd"] for j in guardados) == pytest.approx(0.432)


@sin_mongo
async def test_un_numero_resuelto_desde_el_panel_se_redacta(http, base, maquina) -> None:
    """El caso real: el contacto está agendado por nombre y el número vive en
    el panel de contacto de ese chat. El `RESOLVER` lo trae — determinístico,
    sin modelo — y recién con el número se decide R4 y se redacta."""
    await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=5)

    job = await tomar(http, maquina.token)
    await reportar(
        http,
        maquina.token,
        job["id"],
        detalle={
            "chats": [
                {
                    "contacto_nombre": "Corralon Oeste",
                    "contacto_telefono": None,
                    "ultimo_mensaje_resumen": "pidió precio de hierro del 8",
                    "quien_hablo_ultimo": "contacto",
                    "antiguedad_dias": 20,
                }
            ]
        },
    )

    resolver = await tomar(http, maquina.token)
    assert resolver["tipo"] == "RESOLVER"
    assert resolver["payload"]["contactos"] == ["Corralon Oeste"]

    #  El agente leyó el número del panel, tal como lo muestra la interfaz.
    await reportar(
        http,
        maquina.token,
        resolver["id"],
        detalle={
            "contactos": [
                {"nombre": "Corralon Oeste", "telefono": "+54 9 11 2323-1151", "motivo": None}
            ]
        },
    )

    redactar = await tomar(http, maquina.token)
    assert redactar["tipo"] == "REDACTAR"
    assert redactar["payload"]["contacto_nombre"] == "Corralon Oeste"
    assert "contacto_id" not in redactar["payload"]

    #  El contexto guarda el número ya normalizado: es contra el que después
    #  compara la identidad (R1) y el que hereda el borrador.
    doc = await base["jobs"].find_one({"tipo": str(cola.Tipo.REDACTAR)})
    assert doc["contexto"]["contacto_id"] == PERMITIDO


@sin_mongo
async def test_un_chat_fuera_de_la_ventana_de_antiguedad_no_se_sigue(http, base, maquina) -> None:
    """El caso de uso son los clientes fríos: el chat de hoy no necesita
    seguimiento y el de hace un año se considera perdido. Ni se redacta ni se
    manda a resolver."""
    await configuracion.actualizar(base, {"antiguedad_min_dias": 5, "antiguedad_max_dias": 30})
    await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=5)

    job = await tomar(http, maquina.token)
    #  La ventana viaja en el payload, para que el agente busque donde hay.
    assert job["payload"]["antiguedad_min_dias"] == 5
    assert job["payload"]["antiguedad_max_dias"] == 30

    await reportar(
        http,
        maquina.token,
        job["id"],
        detalle={
            "chats": [
                {
                    "contacto_nombre": "Muy Fresco",
                    "contacto_telefono": PERMITIDO,
                    "ultimo_mensaje_resumen": "escribió hoy",
                    "quien_hablo_ultimo": "contacto",
                    "antiguedad_dias": 1,
                },
                {
                    "contacto_nombre": "Muy Viejo",
                    "contacto_telefono": None,
                    "ultimo_mensaje_resumen": "consultó hace un año",
                    "quien_hablo_ultimo": "contacto",
                    "antiguedad_dias": 300,
                },
            ]
        },
    )

    assert await base["jobs"].count_documents({"tipo": str(cola.Tipo.REDACTAR)}) == 0
    assert await base["jobs"].count_documents({"tipo": str(cola.Tipo.RESOLVER)}) == 0
    assert await tomar(http, maquina.token) is None


@sin_mongo
async def test_el_barrido_avanza_su_cursor_por_maquina(http, base, maquina) -> None:
    """D27 de punta a punta: la primera tanda va al fondo del historial, el
    cursor queda en la antigüedad del chat más nuevo de la tanda, la corrida
    siguiente lo lleva en el payload junto con los nombres para no repetir, y
    una tanda corta marca el barrido como completado."""
    await configuracion.actualizar(base, {"modo_lectura": "barrido"})
    await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=2)

    job = await tomar(http, maquina.token)
    assert job["tipo"] == "LISTAR"
    assert job["payload"]["estrategia"] == "barrido"
    assert job["payload"]["barrido_hasta_dias"] == 3650
    assert job["payload"]["ya_vistos"] == []

    await reportar(
        http,
        maquina.token,
        job["id"],
        detalle={
            "chats": [
                {
                    "contacto_nombre": "El Mas Viejo",
                    "contacto_telefono": PERMITIDO,
                    "ultimo_mensaje_resumen": "cotizó hierro para una obra y no volvió",
                    "quien_hablo_ultimo": "contacto",
                    "antiguedad_dias": 400,
                },
                {
                    "contacto_nombre": "El Siguiente",
                    "contacto_telefono": OTRO_PERMITIDO,
                    "ultimo_mensaje_resumen": "pidió precio de cemento",
                    "quien_hablo_ultimo": "contacto",
                    "antiguedad_dias": 380,
                },
            ]
        },
    )

    vendedor = await base["vendedores"].find_one({"maquina": "pc-1"})
    assert vendedor["barrido"]["hasta_dias"] == 380
    assert vendedor["barrido"]["ultima_tanda"] == ["El Mas Viejo", "El Siguiente"]
    assert vendedor["barrido"]["completado_en"] is None

    # La corrida siguiente arranca donde terminó la anterior.
    await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=2)
    listar2 = await base["jobs"].find_one({"tipo": "LISTAR", "estado": "pendiente"})
    assert listar2["payload"]["barrido_hasta_dias"] == 380
    assert listar2["payload"]["ya_vistos"] == ["El Mas Viejo", "El Siguiente"]

    # El agente va recibiendo lo pendiente (los REDACTAR de la tanda uno
    # primero); cuando llega el segundo LISTAR, una tanda corta = llegó a hoy.
    while (siguiente := await tomar(http, maquina.token)) is not None:
        if siguiente["tipo"] == "REDACTAR":
            await reportar(
                http,
                maquina.token,
                siguiente["id"],
                detalle={"status": "ok", "texto": "Hola, ¿retomamos?"},
            )
            continue
        assert siguiente["tipo"] == "LISTAR"
        await reportar(
            http,
            maquina.token,
            siguiente["id"],
            detalle={
                "fin_del_historial": True,
                "chats": [
                    {
                        "contacto_nombre": "El Ultimo Que Queda",
                        "contacto_telefono": None,
                        "ultimo_mensaje_resumen": "consultó por perfiles y quedó en avisar",
                        "quien_hablo_ultimo": "contacto",
                        "antiguedad_dias": 350,
                    }
                ],
            },
        )
        break

    vendedor = await base["vendedores"].find_one({"maquina": "pc-1"})
    assert vendedor["barrido"]["hasta_dias"] == 350
    assert vendedor["barrido"]["completado_en"] is not None
    assert vendedor["barrido"]["ultima_tanda"] == ["El Ultimo Que Queda"]


@sin_mongo
async def test_una_tanda_corta_por_tiempo_no_da_el_barrido_por_terminado(
    http, base, maquina
) -> None:
    """⚠️ Contar no alcanza: el barrido abre chat por chat y a veces corta por
    tiempo devolviendo menos de los pedidos. Si eso se leyera como "llegué al
    presente", el historial quedaría a medio recorrer y nadie se enteraría."""
    await configuracion.actualizar(base, {"modo_lectura": "barrido"})
    await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=20)

    job = await tomar(http, maquina.token)
    await reportar(
        http,
        maquina.token,
        job["id"],
        detalle={
            "fin_del_historial": False,
            "chats": [
                {
                    "contacto_nombre": "Uno Solo",
                    "contacto_telefono": PERMITIDO,
                    "ultimo_mensaje_resumen": "pidió presupuesto y no volvió",
                    "quien_hablo_ultimo": "contacto",
                    "antiguedad_dias": 500,
                }
            ],
        },
    )

    vendedor = await base["vendedores"].find_one({"maquina": "pc-1"})
    assert vendedor["barrido"]["completado_en"] is None, "una tanda corta no cierra el barrido"
    assert vendedor["barrido"]["hasta_dias"] == 500, "pero el cursor sí avanza con lo que trajo"


@sin_mongo
async def test_cancelar_corta_lo_pendiente_y_libera_el_boton(http, base, maquina) -> None:
    """Sin esto, una corrida con un job trabado deja el panel "en curso" para
    siempre y no se puede disparar otra. Cancelar es la salida, y es de una
    persona: queda en la auditoría.

    Lo ya hecho queda hecho; sólo lo pendiente se marca fallido.
    """
    disparo = await corridas.disparar(base, quien="dueño", tipo="generacion", n_chats=5)
    corrida_id = disparo.corrida_id

    # El LISTAR se hace y deja pendientes dos REDACTAR y el RESOLVER del chat
    # sin teléfono. Nadie los toma.
    job = await tomar(http, maquina.token)
    await reportar(http, maquina.token, job["id"], detalle={"chats": chats(), "leidos": 4})
    assert (await corridas.progreso(base, corrida_id))["terminada"] is False

    cortados = await corridas.cancelar(base, corrida_id, quien="panel")
    assert cortados == 3

    progreso = await corridas.progreso(base, corrida_id)
    assert progreso["terminada"] is True
    assert progreso["estado"] == "cancelada"

    # El LISTAR reportado no se tocó; los cortados dicen por qué murieron.
    guardados = await base["jobs"].find({"corrida_id": corrida_id}).to_list(None)
    assert {j["estado"] for j in guardados} == {"listo", "fallido"}
    assert all(j["codigo"] == "CANCELADO" for j in guardados if j["estado"] == "fallido")

    # Y quedó escrito quién lo hizo.
    evento = await base["auditoria"].find_one({"que": "corrida_cancelada"})
    assert evento is not None and evento["quien"] == "panel"
