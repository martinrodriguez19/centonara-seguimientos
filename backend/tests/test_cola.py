"""Tests de la cola.

El que importa es `test_ningun_job_se_entrega_dos_veces`: es la parte donde una
condición de carrera se traduce en un cliente recibiendo el mismo mensaje dos
veces.

Los de espaciado y política de reintento no necesitan base y corren en
cualquier lado. Los de concurrencia sí: `findOneAndUpdate` es atómico *en el
servidor*, y eso no se puede simular.
"""

from __future__ import annotations

import asyncio
import itertools
import os
import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.cola import (
    CANARIO,
    ESPERA_CANARIO_S,
    MAX_INTENTOS,
    PAUSA_ENTRE_ENVIOS,
    Codigo,
    EstadoJob,
    JobDesconocido,
    Tipo,
    encolar,
    encolar_envio_escalonado,
    encolar_envios,
    escalonar,
    pendientes,
    recuperar_colgados,
    reportar,
    tomar,
)
from app.core.esquema import inicializar

AHORA = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Política de reintento — sin base de datos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "codigo",
    [
        Codigo.CONTACTO_NO_COINCIDE,
        Codigo.NUMERO_NO_RESOLUBLE,
        Codigo.DESTINO_NO_PERMITIDO,
        Codigo.SIN_CONFIRMAR,
        Codigo.SELECTOR_ROTO,
        Codigo.CANCELADO,
    ],
)
def test_lo_que_nunca_se_reintenta(codigo: Codigo) -> None:
    """No son fallas transitorias: son el sistema haciendo su trabajo.

    Reintentar un `CONTACTO_NO_COINCIDE` es insistir con el chat equivocado, que
    es la forma exacta de convertir un aborto correcto en un error real.
    """
    assert not codigo.reintenta


@pytest.mark.parametrize(
    "codigo",
    [
        Codigo.CAMPO_NO_VACIO,
        Codigo.CHAT_NO_ABRE,
        Codigo.SESION_CAIDA,
        Codigo.TIMEOUT,
        Codigo.ERROR_INESPERADO,
    ],
)
def test_lo_que_si_se_reintenta(codigo: Codigo) -> None:
    assert codigo.reintenta


def test_sin_confirmar_no_se_reintenta_porque_puede_haber_salido() -> None:
    """El caso más sutil de la tabla.

    `SIN_CONFIRMAR` no significa "no salió": significa "no sabemos". Reintentar
    mandaría el mensaje dos veces. Por eso alerta en vez de reintentar.
    """
    assert not Codigo.SIN_CONFIRMAR.reintenta


def test_solo_el_selector_roto_frena_la_corrida() -> None:
    """Si el DOM cambió, los envíos siguientes tienen el mismo problema."""
    assert Codigo.SELECTOR_ROTO.frena_corrida
    for codigo in Codigo:
        if codigo is not Codigo.SELECTOR_ROTO:
            assert not codigo.frena_corrida


def test_todo_codigo_tiene_decidida_su_politica() -> None:
    """Si mañana alguien agrega un código y se olvida de decidir, esto lo agarra."""
    for codigo in Codigo:
        assert isinstance(codigo.reintenta, bool)
        assert isinstance(codigo.frena_corrida, bool)


# ---------------------------------------------------------------------------
# Espaciado — función pura, sin base de datos
# ---------------------------------------------------------------------------


def test_el_primero_sale_enseguida() -> None:
    momentos = escalonar(3, desde=AHORA, aleatorio=random.Random(1))
    assert momentos[0] == AHORA


def test_los_momentos_van_siempre_para_adelante() -> None:
    momentos = escalonar(20, desde=AHORA, aleatorio=random.Random(1))
    assert momentos == sorted(momentos)


def test_veinte_envios_producen_veinte_intervalos_distintos() -> None:
    """La pausa nunca es fija. Un `sleep(60)` acá es un bug.

    Lo que dispara bloqueos de línea no es principalmente el volumen: son los
    patrones de tiempo regulares.
    """
    momentos = escalonar(21, desde=AHORA, aleatorio=random.Random(7))
    intervalos = [(b - a).total_seconds() for a, b in itertools.pairwise(momentos)]
    assert len(intervalos) == 20
    assert len(set(intervalos)) == 20


def test_los_intervalos_caen_dentro_de_la_pausa_configurada() -> None:
    minimo, maximo = PAUSA_ENTRE_ENVIOS
    momentos = escalonar(50, desde=AHORA, aleatorio=random.Random(3))
    for anterior, siguiente in itertools.pairwise(momentos):
        assert minimo <= (siguiente - anterior).total_seconds() <= maximo


def test_dos_corridas_no_producen_el_mismo_patron() -> None:
    una = escalonar(10, desde=AHORA, aleatorio=random.Random(1))
    otra = escalonar(10, desde=AHORA, aleatorio=random.Random(2))
    assert una != otra


def test_escalonar_de_cero_no_devuelve_nada() -> None:
    assert escalonar(0, desde=AHORA) == []


def test_escalonar_rechaza_una_cantidad_negativa() -> None:
    with pytest.raises(ValueError, match="negativa"):
        escalonar(-1, desde=AHORA)


def test_escalonar_rechaza_una_pausa_dada_vuelta() -> None:
    with pytest.raises(ValueError, match="pausa inválida"):
        escalonar(3, desde=AHORA, pausa=(180, 45))


# ---------------------------------------------------------------------------
# Comportamiento — necesita un Mongo de verdad
# ---------------------------------------------------------------------------

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"),
    reason="necesita un Mongo real: definí MONGO_URL_TESTS",
)


@pytest.fixture
async def base():
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    try:
        db = cliente[nombre]
        await inicializar(db)
        yield db
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


@sin_mongo
async def test_encolar_y_tomar(base) -> None:
    await encolar(base, tipo=Tipo.DIAGNOSTICO, maquina="mac-1")
    job = await tomar(base, "mac-1")
    assert job is not None
    assert job["tipo"] == Tipo.DIAGNOSTICO
    assert job["estado"] == EstadoJob.TOMADO
    assert job["intentos"] == 1


@sin_mongo
async def test_sin_trabajo_devuelve_nada(base) -> None:
    assert await tomar(base, "mac-1") is None


@sin_mongo
async def test_una_maquina_no_toma_el_job_de_otra(base) -> None:
    await encolar(base, tipo=Tipo.DIAGNOSTICO, maquina="mac-1")
    assert await tomar(base, "mac-2") is None
    assert await tomar(base, "mac-1") is not None


@sin_mongo
async def test_un_job_del_futuro_no_se_entrega_todavia(base) -> None:
    """Así se implementa el espaciado: sin dormir un hilo."""
    await encolar(
        base,
        tipo=Tipo.ENVIAR,
        maquina="mac-1",
        disponible_desde=AHORA + timedelta(minutes=5),
        ahora=AHORA,
    )
    assert await tomar(base, "mac-1", ahora=AHORA) is None
    assert await tomar(base, "mac-1", ahora=AHORA + timedelta(minutes=6)) is not None


@sin_mongo
async def test_se_entrega_el_mas_viejo_primero(base) -> None:
    """Sin orden, un job puede quedarse esperando para siempre."""
    for minutos in (10, 1, 5):
        await encolar(
            base,
            tipo=Tipo.ENVIAR,
            maquina="mac-1",
            payload={"orden": minutos},
            disponible_desde=AHORA + timedelta(minutes=minutos),
            ahora=AHORA,
        )
    despues = AHORA + timedelta(hours=1)
    ordenes = [(await tomar(base, "mac-1", ahora=despues))["payload"]["orden"] for _ in range(3)]
    assert ordenes == [1, 5, 10]


@sin_mongo
async def test_ningun_job_se_entrega_dos_veces(base) -> None:
    """⚠️ El test que justifica que la cola exista.

    Ocho consumidores concurrentes contra treinta jobs. Si `find_one_and_update`
    no fuera atómico, dos agentes se llevarían el mismo job y un cliente
    recibiría el mismo mensaje dos veces.
    """
    cantidad = 30
    for indice in range(cantidad):
        await encolar(base, tipo=Tipo.ENVIAR, maquina="mac-1", payload={"n": indice})

    async def consumidor() -> list[int]:
        mios = []
        while (job := await tomar(base, "mac-1")) is not None:
            mios.append(job["payload"]["n"])
        return mios

    repartos = await asyncio.gather(*(consumidor() for _ in range(8)))

    todos = [n for reparto in repartos for n in reparto]
    assert len(todos) == cantidad, "se entregaron más o menos jobs de los que había"
    assert len(set(todos)) == cantidad, "hubo un job entregado dos veces"


@sin_mongo
async def test_reportar_bien_cierra_el_job(base) -> None:
    job_id = await encolar(base, tipo=Tipo.LISTAR, maquina="mac-1")
    await tomar(base, "mac-1")
    reporte = await reportar(base, job_id, ok=True, raw='{"chats": []}', costo_usd=0.03)

    assert reporte.estado is EstadoJob.LISTO
    guardado = await base["jobs"].find_one({"_id": job_id})
    assert guardado["terminado_en"] is not None
    assert guardado["costo_usd"] == 0.03


@sin_mongo
async def test_el_raw_y_el_stderr_se_guardan_tambien_cuando_sale_bien(base) -> None:
    """R5. Si se agregan recién cuando falla, el día que hagan falta no están."""
    job_id = await encolar(base, tipo=Tipo.LISTAR, maquina="mac-1")
    await tomar(base, "mac-1")
    await reportar(base, job_id, ok=True, raw="salida completa", stderr="un aviso")

    guardado = await base["jobs"].find_one({"_id": job_id})
    assert guardado["raw"] == "salida completa"
    assert guardado["stderr"] == "un aviso"


@sin_mongo
async def test_un_timeout_se_reintenta_una_sola_vez(base) -> None:
    """⚠️ Un TIMEOUT no es un tropiezo: es que el trabajo no entró en el tiempo
    que tenía. Con el barrido —que abre chat por chat— tres intentos de 25
    minutos son tres cuartos de hora de máquina para la misma conclusión. Uno
    cubre el caso transitorio; el segundo ya es esperar sentado.
    """
    job_id = await encolar(base, tipo=Tipo.LISTAR, maquina="mac-1", ahora=AHORA)
    await tomar(base, "mac-1", ahora=AHORA)

    primero = await reportar(base, job_id, ok=False, codigo=Codigo.TIMEOUT, ahora=AHORA)
    assert primero.reintenta, "el primero sí: pudo ser una carga lenta"

    despues = AHORA + timedelta(minutes=30)
    await tomar(base, "mac-1", ahora=despues)
    segundo = await reportar(base, job_id, ok=False, codigo=Codigo.TIMEOUT, ahora=despues)

    assert not segundo.reintenta
    assert segundo.estado is EstadoJob.FALLIDO

    #  Y los otros códigos reintentables conservan sus tres intentos.
    otro = await encolar(base, tipo=Tipo.ENVIAR, maquina="mac-1", ahora=AHORA)
    await tomar(base, "mac-1", ahora=AHORA)
    reporte = await reportar(base, otro, ok=False, codigo=Codigo.CHAT_NO_ABRE, ahora=AHORA)
    assert reporte.reintenta


@sin_mongo
async def test_el_rescate_de_colgados_espera_mas_que_el_job_mas_largo(base) -> None:
    """⚠️ Si el backend devolviera a la cola un job que el agente todavía está
    haciendo, ese trabajo se pagaría dos veces. El `LISTAR` del barrido puede
    tardar 25 minutos, así que el rescate tiene que estar por encima."""
    from app.core.cola import SEGUNDOS_PARA_DAR_POR_COLGADO

    assert SEGUNDOS_PARA_DAR_POR_COLGADO > 25 * 60

    job_id = await encolar(base, tipo=Tipo.LISTAR, maquina="mac-1", ahora=AHORA)
    await tomar(base, "mac-1", ahora=AHORA)

    #  A los 45 minutos sigue siendo suyo: un barrido largo todavía puede estar
    #  trabajando (el umbral subió a 60 con el pase único).
    assert await recuperar_colgados(base, ahora=AHORA + timedelta(minutes=45)) == 0
    #  A los 75, no: esa Mac se murió.
    assert await recuperar_colgados(base, ahora=AHORA + timedelta(minutes=75)) == 1
    guardado = await base["jobs"].find_one({"_id": job_id})
    assert guardado["estado"] == str(EstadoJob.PENDIENTE)


@sin_mongo
async def test_un_fallo_reintentable_vuelve_a_la_cola(base) -> None:
    job_id = await encolar(base, tipo=Tipo.ENVIAR, maquina="mac-1", ahora=AHORA)
    await tomar(base, "mac-1", ahora=AHORA)
    reporte = await reportar(base, job_id, ok=False, codigo=Codigo.CHAT_NO_ABRE, ahora=AHORA)

    assert reporte.reintenta
    assert reporte.estado is EstadoJob.PENDIENTE
    # Vuelve con un respiro: no reintenta en bucle contra algo que no se recuperó.
    assert await tomar(base, "mac-1", ahora=AHORA) is None
    assert await tomar(base, "mac-1", ahora=AHORA + timedelta(minutes=5)) is not None


@sin_mongo
async def test_un_contacto_que_no_coincide_no_se_reintenta_nunca(base) -> None:
    """La verificación de identidad abortó. Insistir es escribirle a otro."""
    job_id = await encolar(base, tipo=Tipo.ENVIAR, maquina="mac-1")
    await tomar(base, "mac-1")
    reporte = await reportar(base, job_id, ok=False, codigo=Codigo.CONTACTO_NO_COINCIDE)

    assert not reporte.reintenta
    assert reporte.estado is EstadoJob.FALLIDO
    assert await tomar(base, "mac-1") is None


@sin_mongo
async def test_se_agotan_los_intentos_y_el_job_falla(base) -> None:
    job_id = await encolar(base, tipo=Tipo.ENVIAR, maquina="mac-1", ahora=AHORA)
    momento = AHORA

    for _ in range(MAX_INTENTOS):
        momento += timedelta(minutes=10)
        assert await tomar(base, "mac-1", ahora=momento) is not None
        reporte = await reportar(base, job_id, ok=False, codigo=Codigo.CHAT_NO_ABRE, ahora=momento)

    assert reporte.estado is EstadoJob.FALLIDO
    assert not reporte.reintenta


@sin_mongo
async def test_el_selector_roto_avisa_que_hay_que_frenar_la_corrida(base) -> None:
    job_id = await encolar(base, tipo=Tipo.ENVIAR, maquina="mac-1")
    await tomar(base, "mac-1")
    reporte = await reportar(base, job_id, ok=False, codigo=Codigo.SELECTOR_ROTO)

    assert reporte.frena_corrida
    assert reporte.estado is EstadoJob.FALLIDO


@sin_mongo
async def test_reportar_un_job_que_no_existe_es_un_bug(base) -> None:
    from bson import ObjectId

    with pytest.raises(JobDesconocido):
        await reportar(base, ObjectId(), ok=True)


@sin_mongo
async def test_un_agente_que_se_muere_deja_su_job_recuperable(base) -> None:
    """El escenario "apagar una Mac a mitad de corrida"."""
    await encolar(base, tipo=Tipo.ENVIAR, maquina="mac-1", ahora=AHORA)
    await tomar(base, "mac-1", ahora=AHORA)

    # Nadie reporta: la máquina se apagó.
    assert await tomar(base, "mac-1", ahora=AHORA + timedelta(minutes=5)) is None

    recuperados = await recuperar_colgados(base, ahora=AHORA + timedelta(hours=2))
    assert recuperados == 1
    assert await tomar(base, "mac-1", ahora=AHORA + timedelta(hours=2)) is not None


@sin_mongo
async def test_recuperar_no_toca_un_job_que_todavia_esta_corriendo(base) -> None:
    """`LISTAR` abre el navegador y tarda. Recuperarlo temprano lo correría dos veces."""
    await encolar(base, tipo=Tipo.LISTAR, maquina="mac-1", ahora=AHORA)
    await tomar(base, "mac-1", ahora=AHORA)

    assert await recuperar_colgados(base, ahora=AHORA + timedelta(minutes=2)) == 0


@sin_mongo
async def test_recuperar_no_resetea_los_intentos(base) -> None:
    """Un envío que hace colgar al agente no puede entrar en un bucle infinito."""
    await encolar(base, tipo=Tipo.ENVIAR, maquina="mac-1", ahora=AHORA)
    await tomar(base, "mac-1", ahora=AHORA)
    await recuperar_colgados(base, ahora=AHORA + timedelta(hours=2))

    job = await tomar(base, "mac-1", ahora=AHORA + timedelta(hours=2))
    assert job["intentos"] == 2


@sin_mongo
async def test_encolar_envios_baraja_y_espacia(base) -> None:
    from bson import ObjectId

    corrida = ObjectId()
    payloads = [{"n": n} for n in range(10)]
    await encolar_envios(
        base,
        maquina="mac-1",
        corrida_id=corrida,
        payloads=payloads,
        aleatorio=random.Random(5),
        ahora=AHORA,
    )

    jobs = await base["jobs"].find({"corrida_id": corrida}).to_list(None)
    assert len(jobs) == 10

    # Barajado: el orden de salida no es el de entrada.
    por_momento = sorted(jobs, key=lambda j: j["disponible_desde"])
    assert [j["payload"]["n"] for j in por_momento] != list(range(10))

    # Espaciado: ningún par sale al mismo tiempo.
    momentos = [j["disponible_desde"] for j in por_momento]
    assert len(set(momentos)) == 10


# ---------------------------------------------------------------------------
# Encolar de a uno (D36): el espaciado sin conocer la tanda
# ---------------------------------------------------------------------------


@sin_mongo
async def test_encolar_de_a_uno_el_primero_sale_enseguida(base) -> None:
    from bson import ObjectId

    corrida = ObjectId()
    job_id = await encolar_envio_escalonado(
        base, maquina="mac-1", corrida_id=corrida, payload={"n": 0}, ahora=AHORA
    )

    job = await base["jobs"].find_one({"_id": job_id})
    assert job["tipo"] == Tipo.ENVIAR
    assert job["disponible_desde"] == AHORA


@sin_mongo
async def test_encolar_de_a_uno_espacia_detras_del_ultimo(base) -> None:
    """La pausa aleatoria de siempre, aunque la tanda no exista como momento."""
    from bson import ObjectId

    corrida = ObjectId()
    await encolar_envio_escalonado(
        base, maquina="mac-1", corrida_id=corrida, payload={"n": 0}, ahora=AHORA
    )
    segundo = await encolar_envio_escalonado(
        base,
        maquina="mac-1",
        corrida_id=corrida,
        payload={"n": 1},
        aleatorio=random.Random(7),
        ahora=AHORA,
    )

    job = await base["jobs"].find_one({"_id": segundo})
    delta = (job["disponible_desde"] - AHORA).total_seconds()
    assert PAUSA_ENTRE_ENVIOS[0] <= delta <= PAUSA_ENTRE_ENVIOS[1]


@sin_mongo
async def test_encolar_de_a_uno_abre_el_hueco_del_canario(base) -> None:
    """Los tres primeros de la máquina, y después los diez minutos de mirar."""
    from bson import ObjectId

    corrida = ObjectId()
    for n in range(CANARIO + 1):
        await encolar_envio_escalonado(
            base,
            maquina="mac-1",
            corrida_id=corrida,
            payload={"n": n},
            aleatorio=random.Random(n),
            ahora=AHORA,
        )

    momentos = sorted(
        j["disponible_desde"]
        for j in await base["jobs"].find({"corrida_id": corrida}).to_list(None)
    )
    salto = (momentos[CANARIO] - momentos[CANARIO - 1]).total_seconds()
    assert salto >= ESPERA_CANARIO_S


@sin_mongo
async def test_encolar_de_a_uno_nunca_programa_en_el_pasado(base) -> None:
    """Si el último programado ya pasó —una redacción tardó—, se arranca de ahora."""
    from bson import ObjectId

    corrida = ObjectId()
    await encolar_envio_escalonado(
        base, maquina="mac-1", corrida_id=corrida, payload={"n": 0}, ahora=AHORA
    )

    mucho_despues = AHORA + timedelta(hours=2)
    segundo = await encolar_envio_escalonado(
        base, maquina="mac-1", corrida_id=corrida, payload={"n": 1}, ahora=mucho_despues
    )

    job = await base["jobs"].find_one({"_id": segundo})
    assert job["disponible_desde"] >= mucho_despues


@sin_mongo
async def test_encolar_de_a_uno_no_mira_los_envios_de_otra_maquina(base) -> None:
    """Cada agente tiene su propia cola y su propio ritmo."""
    from bson import ObjectId

    corrida = ObjectId()
    for n in range(3):
        await encolar_envio_escalonado(
            base, maquina="mac-1", corrida_id=corrida, payload={"n": n}, ahora=AHORA
        )
    de_otra = await encolar_envio_escalonado(
        base, maquina="mac-2", corrida_id=corrida, payload={"n": 0}, ahora=AHORA
    )

    job = await base["jobs"].find_one({"_id": de_otra})
    assert job["disponible_desde"] == AHORA, "mac-2 no espera detrás de mac-1"


@sin_mongo
async def test_encolar_de_a_uno_rechaza_una_pausa_dada_vuelta(base) -> None:
    from bson import ObjectId

    with pytest.raises(ValueError):
        await encolar_envio_escalonado(
            base, maquina="mac-1", corrida_id=ObjectId(), payload={}, pausa=(180, 45)
        )


@sin_mongo
async def test_pendientes_cuenta_lo_que_falta(base) -> None:
    from bson import ObjectId

    corrida = ObjectId()
    for _ in range(3):
        await encolar(base, tipo=Tipo.ENVIAR, maquina="mac-1", corrida_id=corrida)
    otro = await encolar(base, tipo=Tipo.ENVIAR, maquina="mac-1")

    assert await pendientes(base) == 4
    assert await pendientes(base, corrida_id=corrida) == 3

    await tomar(base, "mac-1")
    assert await pendientes(base) == 4, "un job tomado sigue pendiente de terminar"

    await reportar(base, otro, ok=True)
    assert await pendientes(base) == 3
