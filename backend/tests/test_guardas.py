"""Las guardas aditivas del backend (G1 a G4).

Son los cuatro agregados que impidieron que la corrida del 28/08 terminara —o
que van a impedir el próximo incidente— sin cambiar ningún algoritmo existente:

- **G1**: el piso de reanudación del canario. Sin él, los mismos tres jobs
  fallidos de antes de apretar «reanudar» volvían a frenar la máquina apenas
  reportaba el siguiente envío: el loop freno→soltar→freno de los logs.
- **G2**: el watchdog de mantenimiento. `recuperar_colgados` y `vencer_viejos`
  decían «corre en APScheduler» y APScheduler nunca entró.
- **G3**: un `ENVIAR` cuyo mensaje ya no está en espera no se entrega.
- **G4**: un solo `ENVIAR` vivo por mensaje, como índice único parcial.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app import db
from app.core import cola, corridas, mensajes, vendedores
from app.core.esquema import inicializar
from app.core.estados import Estado
from app.main import app, mantenimiento_periodico

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

AHORA = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


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


async def maquina(base, nombre: str = "mac-rocio"):
    alta = await vendedores.dar_de_alta(base, maquina=nombre, nombre="Rocío")
    await base["vendedores"].update_one(
        {"maquina": nombre},
        {"$set": {"activo": True, "acepto_condiciones_en": datetime.now(UTC)}},
    )
    return alta


async def tres_enviar_fallidos(base, corrida_id, *, terminados_en: datetime) -> None:
    """Los tres primeros ENVIAR de la máquina, fallidos y ya reportados."""
    for i in range(3):
        await base["jobs"].insert_one(
            {
                "tipo": str(cola.Tipo.ENVIAR),
                "maquina": "mac-rocio",
                "corrida_id": corrida_id,
                "payload": {"mensaje_id": str(ObjectId())},
                "contexto": {},
                "estado": str(cola.EstadoJob.FALLIDO),
                "codigo": "CHAT_NO_ABRE",
                "disponible_desde": terminados_en - timedelta(minutes=10 - i),
                "intentos": 3,
                "raw": "",
                "stderr": "",
                "costo_usd": 0.0,
                "creado_en": terminados_en - timedelta(minutes=15),
                "tomado_en": None,
                "terminado_en": terminados_en,
            }
        )


# ---------------------------------------------------------------------------
# G1 — el piso de reanudación del canario
# ---------------------------------------------------------------------------


@sin_mongo
async def test_sin_reanudar_el_canario_frena_como_siempre(base) -> None:
    await maquina(base)
    corrida_id = ObjectId()
    await tres_enviar_fallidos(base, corrida_id, terminados_en=AHORA)

    freno = await corridas.revisar_canario(base, corrida_id, maquina="mac-rocio")

    assert freno is True
    vendedor = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert vendedor["frenado_por_canario_en"] is not None


@sin_mongo
async def test_los_fallos_de_antes_de_reanudar_no_vuelven_a_frenar(base) -> None:
    """⚠️ El loop freno→soltar→freno. Los tres jobs evaluados terminaron ANTES
    del último «reanudar»: ya se miraron, y volver a frenar por ellos deja la
    máquina frenada para siempre — incluso con los selectores arreglados."""
    await maquina(base)
    corrida_id = ObjectId()
    await tres_enviar_fallidos(base, corrida_id, terminados_en=AHORA)

    #  El canario frena; una persona mira y reanuda.
    assert await corridas.revisar_canario(base, corrida_id, maquina="mac-rocio") is True
    await vendedores.soltar_freno_de_canario(
        base, ["mac-rocio"], ahora=AHORA + timedelta(minutes=5)
    )

    #  El agente reporta el siguiente envío y el canario se vuelve a evaluar,
    #  sobre los MISMOS tres jobs viejos.
    freno = await corridas.revisar_canario(base, corrida_id, maquina="mac-rocio")

    assert freno is False
    vendedor = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert vendedor["frenado_por_canario_en"] is None, "no tiene que volver a frenarse"


@sin_mongo
async def test_tres_fallos_nuevos_despues_de_reanudar_si_frenan(base) -> None:
    """El piso no es una amnistía: fallos POSTERIORES al reanudar cuentan."""
    await maquina(base)
    corrida_id = ObjectId()
    await vendedores.soltar_freno_de_canario(base, ["mac-rocio"], ahora=AHORA)
    #  Nada que soltar (no estaba frenada): el piso no quedó anotado, y aunque
    #  hubiera quedado, estos tres terminan DESPUÉS.
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"}, {"$set": {"freno_soltado_en": AHORA}}
    )
    await tres_enviar_fallidos(base, corrida_id, terminados_en=AHORA + timedelta(minutes=20))

    assert await corridas.revisar_canario(base, corrida_id, maquina="mac-rocio") is True


@sin_mongo
async def test_un_job_cancelado_no_cuenta_para_el_canario(base) -> None:
    """Un CANCELADO es una decisión del panel (o G3), no un síntoma del
    sistema: contarlo frenaría una máquina sana."""
    await maquina(base)
    corrida_id = ObjectId()
    await tres_enviar_fallidos(base, corrida_id, terminados_en=AHORA)
    await base["jobs"].update_one(
        {"corrida_id": corrida_id, "estado": str(cola.EstadoJob.FALLIDO)},
        {"$set": {"codigo": "CANCELADO"}},
    )

    #  Con uno cancelado quedan dos evaluables: no alcanza para decidir.
    assert await corridas.revisar_canario(base, corrida_id, maquina="mac-rocio") is False


# ---------------------------------------------------------------------------
# G2 — el watchdog de mantenimiento
# ---------------------------------------------------------------------------


async def test_el_mantenimiento_corre_y_sobrevive_a_sus_propios_errores(monkeypatch) -> None:
    """Sin Mongo: lo que se prueba es el loop — que llama a las dos funciones
    cada intervalo y que un error en una vuelta no lo mata."""
    from app.core import cola as cola_mod
    from app.core import mensajes as mensajes_mod

    llamadas = {"recuperados": 0, "vencidos": 0}
    dos_vueltas_completas = asyncio.Event()

    async def recuperar_falso(base):
        llamadas["recuperados"] += 1
        if llamadas["recuperados"] == 1:
            raise RuntimeError("hipo de Mongo")
        return 0

    async def vencer_falso(base):
        llamadas["vencidos"] += 1
        if llamadas["vencidos"] >= 2:
            dos_vueltas_completas.set()
        return 0

    monkeypatch.setattr(db, "obtener_base", lambda: object())
    monkeypatch.setattr(cola_mod, "recuperar_colgados", recuperar_falso)
    monkeypatch.setattr(mensajes_mod, "vencer_viejos", vencer_falso)

    tarea = asyncio.create_task(mantenimiento_periodico(intervalo_s=0.01))
    try:
        async with asyncio.timeout(5):
            await dos_vueltas_completas.wait()
    finally:
        tarea.cancel()

    #  La primera vuelta reventó en `recuperar` y el loop siguió vivo.
    assert llamadas["recuperados"] >= 3
    assert llamadas["vencidos"] >= 2


@sin_mongo
async def test_recuperar_colgados_devuelve_a_la_cola_un_job_de_maquina_muerta(base) -> None:
    """La integración de verdad: un job tomado hace más de 40 minutos vuelve a
    `pendiente` — es lo que hace que la corrida de una Mac apagada termine."""
    job_id = await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio")
    await base["jobs"].update_one(
        {"_id": job_id},
        {
            "$set": {
                "estado": str(cola.EstadoJob.TOMADO),
                "tomado_en": datetime.now(UTC) - timedelta(hours=2),
            }
        },
    )

    assert await cola.recuperar_colgados(base) == 1
    job = await base["jobs"].find_one({"_id": job_id})
    assert job["estado"] == str(cola.EstadoJob.PENDIENTE)


# ---------------------------------------------------------------------------
# G3 — un ENVIAR cuyo mensaje ya no está en espera no se entrega
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@sin_mongo
async def test_un_mensaje_vetado_no_se_entrega_y_el_job_se_cancela(base, cliente) -> None:
    alta = await maquina(base)
    corrida_id = ObjectId()
    mensaje_id = await mensajes.crear_borrador(
        base,
        corrida_id=corrida_id,
        maquina="mac-rocio",
        contacto_id="+5491123231151",
        contacto_nombre="Corralón",
        texto="hola",
    )
    #  Sigue en BORRADOR: nadie lo aprobó. Entregar su ENVIAR sería escribir
    #  algo que una persona no soltó.
    job_id = await cola.encolar(
        base,
        tipo=cola.Tipo.ENVIAR,
        maquina="mac-rocio",
        corrida_id=corrida_id,
        payload={"mensaje_id": str(mensaje_id), "contacto_id": "+5491123231151", "texto": "hola"},
    )

    respuesta = await cliente.get("/api/agente/jobs/proximo", headers=_auth(alta.token))

    assert respuesta.status_code == 204, "el agente no tiene que recibir ese payload"
    job = await base["jobs"].find_one({"_id": job_id})
    assert job["estado"] == str(cola.EstadoJob.FALLIDO)
    assert job["codigo"] == "CANCELADO"


@sin_mongo
async def test_un_mensaje_en_espera_se_entrega_normal(base, cliente) -> None:
    """El control del test anterior: con el mensaje EN_ESPERA, todo igual."""
    alta = await maquina(base)
    corrida_id = ObjectId()
    mensaje_id = await mensajes.crear_borrador(
        base,
        corrida_id=corrida_id,
        maquina="mac-rocio",
        contacto_id="+5491123231151",
        contacto_nombre="Corralón",
        texto="hola",
    )
    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA)
    await cola.encolar(
        base,
        tipo=cola.Tipo.ENVIAR,
        maquina="mac-rocio",
        corrida_id=corrida_id,
        payload={"mensaje_id": str(mensaje_id), "contacto_id": "+5491123231151", "texto": "hola"},
    )

    respuesta = await cliente.get("/api/agente/jobs/proximo", headers=_auth(alta.token))

    assert respuesta.status_code == 200
    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == str(Estado.ENVIANDO)


# ---------------------------------------------------------------------------
# G4 — un solo ENVIAR vivo por mensaje
# ---------------------------------------------------------------------------


def test_el_indice_de_unicidad_esta_declarado() -> None:
    from app.core import esquema

    jobs = next(c for c in esquema.COLECCIONES if c.nombre == "jobs")
    indice = next(
        (i for i in jobs.indices if i.claves == (("payload.mensaje_id", 1),)),
        None,
    )
    assert indice is not None
    assert indice.unico
    assert indice.parcial == {
        "tipo": "ENVIAR",
        "payload.mensaje_id": {"$exists": True},
        "terminado_en": {"$type": "null"},
    }


@sin_mongo
async def test_el_segundo_enviar_vivo_para_el_mismo_mensaje_no_se_crea(base) -> None:
    """La carrera entre el encadenado automático y el botón del panel: el
    segundo encolar devuelve el job que ya estaba vivo, no uno nuevo."""
    mensaje_id = str(ObjectId())
    payload = {"mensaje_id": mensaje_id, "contacto_id": "+5491123231151", "texto": "hola"}

    primero = await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio", payload=payload)
    segundo = await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio", payload=payload)

    assert segundo == primero
    vivos = await base["jobs"].count_documents(
        {"payload.mensaje_id": mensaje_id, "terminado_en": None}
    )
    assert vivos == 1


async def test_si_el_ganador_termino_en_el_medio_se_reintenta_una_vez() -> None:
    """La carrera dentro de la carrera: el insert choca con el índice, pero
    cuando se busca al job vivo, el ganador YA terminó y salió del índice. No
    se puede montar con un Mongo real —es una ventana de milisegundos— así que
    se prueba con una base falsa: el segundo insert tiene que entrar."""
    from types import SimpleNamespace

    from pymongo.errors import DuplicateKeyError

    class JobsFalsos:
        def __init__(self) -> None:
            self.inserciones = 0

        async def insert_one(self, documento):
            self.inserciones += 1
            if self.inserciones == 1:
                raise DuplicateKeyError("ya había un ENVIAR vivo")
            return SimpleNamespace(inserted_id="job-reintentado")

        async def find_one(self, filtro):
            #  El ganador terminó entre el insert y esta consulta.
            return None

    jobs = JobsFalsos()
    base_falsa = {"jobs": jobs}

    creado = await cola.encolar(
        base_falsa,
        tipo=cola.Tipo.ENVIAR,
        maquina="mac-rocio",
        payload={"mensaje_id": str(ObjectId()), "contacto_id": "+5491123231151", "texto": "hola"},
    )

    assert creado == "job-reintentado"
    assert jobs.inserciones == 2


@sin_mongo
async def test_un_enviar_terminado_no_bloquea_el_reintento_del_mensaje(base) -> None:
    """«Vivo» es la palabra que importa: reenviar un mensaje que falló sigue
    siendo posible, porque el job terminado sale del índice."""
    mensaje_id = str(ObjectId())
    payload = {"mensaje_id": mensaje_id, "contacto_id": "+5491123231151", "texto": "hola"}

    primero = await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio", payload=payload)
    await base["jobs"].update_one(
        {"_id": primero},
        {"$set": {"estado": str(cola.EstadoJob.FALLIDO), "terminado_en": datetime.now(UTC)}},
    )

    segundo = await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio", payload=payload)

    assert segundo != primero
