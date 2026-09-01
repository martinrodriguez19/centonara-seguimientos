"""Escenarios de caos: romper el sistema a propósito.

El criterio es uno solo y no admite matices:

    **Nunca se envía dos veces, y nunca se pierde el registro de algo que salió.**

Todo lo demás —que una corrida quede a medias, que un job tarde, que haya que
reintentar— es aceptable. Esas dos cosas no.

Estos tests se le muestran al cliente: son la respuesta a "¿qué pasa si se corta
la luz?".
"""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from bson import ObjectId
from conftest import ar

from app.core import auditoria, cola, configuracion, mensajes, validacion, vendedores
from app.core.esquema import inicializar
from app.core.estados import Estado, Motivo, TransicionInvalida

AHORA = ar(19, 11, 0)  # miércoles, media mañana en Argentina

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)


@pytest.fixture
async def base():
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    try:
        db = cliente[nombre]
        await inicializar(db)
        await configuracion.actualizar(db, {"destinos_permitidos": ["*"]})
        for maquina in ("mac-rocio", "mac-juan"):
            await vendedores.dar_de_alta(db, maquina=maquina, nombre=maquina)
            await db["vendedores"].update_one(
                {"maquina": maquina},
                {"$set": {"activo": True, "acepto_condiciones_en": AHORA}},
            )
        yield db
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


async def corrida_lista(base, cuantos: int = 6, maquina: str = "mac-rocio") -> ObjectId:
    """Una corrida con `cuantos` mensajes validados y listos para salir."""
    corrida_id = (
        await base["corridas"].insert_one(
            {
                "tipo": "generacion",
                "modo": "prueba",
                "estado": "revision",
                "maquinas": [maquina],
                "creada_en": AHORA,
            }
        )
    ).inserted_id

    for n in range(cuantos):
        await mensajes.crear_borrador(
            base,
            corrida_id=corrida_id,
            maquina=maquina,
            contacto_id=f"+54911000{n:05d}",
            contacto_nombre=f"Contacto {n}",
            texto=f"Hola, quedó pendiente lo que hablamos. Consulta {n}.",
            resumen_ultimo="preguntó por precio de chapa",
            ahora=AHORA,
        )

    await validacion.validar_corrida(base, corrida_id, ahora=AHORA)
    return corrida_id


# ---------------------------------------------------------------------------
# 1. Se apaga una Mac a mitad de corrida
# ---------------------------------------------------------------------------


@sin_mongo
async def test_una_mac_que_se_apaga_no_pierde_su_trabajo(base) -> None:
    """El job vuelve a la cola cuando el barrido lo da por colgado."""
    from app.core import corridas

    corrida_id = await corrida_lista(base, cuantos=3)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)

    # El agente toma uno y la máquina se apaga: nadie reporta nunca.
    tomado = await cola.tomar(base, "mac-rocio", ahora=AHORA)
    assert tomado is not None

    #  Bien pasado el umbral (60 min desde el pase único): lo que se prueba es
    #  la recuperación, no el filo del corte.
    despues = AHORA + timedelta(hours=2)
    assert await cola.recuperar_colgados(base, ahora=despues) == 1

    de_nuevo = await cola.tomar(base, "mac-rocio", ahora=despues)
    assert de_nuevo["_id"] == tomado["_id"], "el mismo trabajo, no otro"


@sin_mongo
async def test_una_mac_que_se_apaga_no_deja_el_mensaje_trabado(base) -> None:
    """El mensaje quedó en ENVIANDO y nadie lo va a mover: tiene que poder volver."""
    corrida_id = await corrida_lista(base, cuantos=1)
    mensaje = (await mensajes.de_la_corrida(base, corrida_id))[0]

    await mensajes.mover(base, mensaje["_id"], Estado.ENVIANDO, ahora=AHORA)
    # La Mac se apaga. Al reintentar, el mensaje vuelve a estar listo.
    await mensajes.mover(base, mensaje["_id"], Estado.EN_ESPERA, ahora=AHORA)

    assert await mensajes.mover(base, mensaje["_id"], Estado.ENVIANDO) is Estado.ENVIANDO


# ---------------------------------------------------------------------------
# 2. Varios agentes tomando trabajo a la vez
# ---------------------------------------------------------------------------


@sin_mongo
async def test_ocho_agentes_sobre_la_misma_cola_no_duplican_nada(base) -> None:
    """⚠️ El escenario que se traduce en un cliente recibiendo lo mismo dos veces."""
    from app.core import corridas

    corrida_id = await corrida_lista(base, cuantos=20)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)

    # Muy en el futuro: todos los jobs están disponibles, canario incluido.
    despues = AHORA + timedelta(days=1)

    async def consumidor() -> list[str]:
        mios = []
        while (job := await cola.tomar(base, "mac-rocio", ahora=despues)) is not None:
            mios.append(job["payload"]["mensaje_id"])
        return mios

    repartos = await asyncio.gather(*(consumidor() for _ in range(8)))
    todos = [m for reparto in repartos for m in reparto]

    assert len(todos) == 20
    assert len(set(todos)) == 20, "un mensaje se entregó dos veces"


@sin_mongo
async def test_dos_maquinas_no_se_roban_trabajo(base) -> None:
    from app.core import corridas

    corrida_id = await corrida_lista(base, cuantos=4, maquina="mac-rocio")
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)

    despues = AHORA + timedelta(days=1)
    assert await cola.tomar(base, "mac-juan", ahora=despues) is None
    assert await cola.tomar(base, "mac-rocio", ahora=despues) is not None


# ---------------------------------------------------------------------------
# 3. Se dispara la misma corrida dos veces
# ---------------------------------------------------------------------------


@sin_mongo
async def test_encolar_los_envios_dos_veces_no_encola_dos_jobs(base) -> None:
    """El dueño aprieta enviar, no ve respuesta, y aprieta de nuevo.

    Un `EN_ESPERA` cuyo envío sigue vivo en la cola no se vuelve a encolar: dos
    jobs para el mismo mensaje serían dos escrituras en el mismo chat. Antes el
    doble click sí re-encolaba y el segundo job rebotaba recién contra la
    máquina de estados; se cambió a propósito con el encadenado automático
    (D36), que hace normal que un mensaje esté encolado sin que nadie apriete.
    """
    from app.core import corridas

    corrida_id = await corrida_lista(base, cuantos=3)

    primera = await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)
    segunda = await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)

    assert primera.mensajes == 3
    assert segunda.mensajes == 0, "sus envíos ya están en la cola"
    assert await base["jobs"].count_documents({"tipo": str(cola.Tipo.ENVIAR)}) == 3

    # Y aunque un job doble existiera, un agente sólo puede llevarse cada
    # mensaje una vez: el primero lo mueve a ENVIANDO y el resto rebota.
    despues = AHORA + timedelta(days=1)
    entregados = set()
    while (job := await cola.tomar(base, "mac-rocio", ahora=despues)) is not None:
        mensaje_id = ObjectId(job["payload"]["mensaje_id"])
        try:
            await mensajes.mover(base, mensaje_id, Estado.ENVIANDO)
            entregados.add(str(mensaje_id))
        except (TransicionInvalida, mensajes.CarreraDeEstados):
            pass

    assert len(entregados) == 3, "cada mensaje se envió una sola vez"


@sin_mongo
async def test_el_mismo_borrador_dos_veces_lo_frena_la_base(base) -> None:
    """No un `if`: un índice único. Una condición de carrera no lo esquiva."""
    corrida_id = ObjectId()
    datos = {
        "corrida_id": corrida_id,
        "maquina": "mac-rocio",
        "contacto_id": "+5491144405036",
        "contacto_nombre": "Marcelo",
        "texto": "Hola Marcelo",
        "ahora": AHORA,
    }
    await mensajes.crear_borrador(base, **datos)

    with pytest.raises(mensajes.MensajeDuplicado):
        await mensajes.crear_borrador(base, **datos)


# ---------------------------------------------------------------------------
# 4. El backend se reinicia con trabajo a medias
# ---------------------------------------------------------------------------


@sin_mongo
async def test_reiniciar_el_backend_no_pierde_la_cola(base) -> None:
    """Todo el estado vive en Mongo. No hay nada en memoria que se pueda perder."""
    from app.core import corridas

    corrida_id = await corrida_lista(base, cuantos=5)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)

    # "Reiniciar" es abrir un cliente nuevo: no hay estado compartido.
    from motor.motor_asyncio import AsyncIOMotorClient

    otro = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)[base.name]
    try:
        pendientes = await cola.pendientes(otro, corrida_id=corrida_id)
        assert pendientes == 5
    finally:
        otro.client.close()


@sin_mongo
async def test_asegurar_el_esquema_dos_veces_no_rompe_nada(base) -> None:
    """Cada arranque lo corre. Si no fuera idempotente, el segundo despliegue fallaría."""
    primera = await inicializar(base)
    segunda = await inicializar(base)
    assert primera == segunda


# ---------------------------------------------------------------------------
# 5. Se frena todo en la mitad
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_kill_switch_no_pierde_lo_encolado(base) -> None:
    """Frenar no es cancelar: al soltarlo, el trabajo sigue ahí."""
    from app.core import corridas

    corrida_id = await corrida_lista(base, cuantos=4)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)

    await configuracion.pausar(base, pausado=True, quien="prueba")
    assert await cola.pendientes(base, corrida_id=corrida_id) == 4

    await configuracion.pausar(base, pausado=False, quien="prueba")
    despues = AHORA + timedelta(days=1)
    assert await cola.tomar(base, "mac-rocio", ahora=despues) is not None


@sin_mongo
async def test_lo_que_ya_salio_queda_registrado_pase_lo_que_pase(base) -> None:
    """⚠️ La otra mitad del criterio: no se pierde el registro de algo que salió.

    Se frena el sistema y se vencen los borradores. Lo que ya se envió sigue en
    la auditoría, que es lo único que responde el día que alguien pregunte.
    """
    corrida_id = await corrida_lista(base, cuantos=3)
    listos = await mensajes.de_la_corrida(base, corrida_id)

    enviado = listos[0]["_id"]
    await mensajes.mover(base, enviado, Estado.ENVIANDO, ahora=AHORA)
    await mensajes.mover(base, enviado, Estado.ENVIADO, quien="mac-rocio", ahora=AHORA)

    await configuracion.pausar(base, pausado=True, quien="prueba")
    await mensajes.vencer_viejos(base, ahora=AHORA + timedelta(days=2))

    registro = await auditoria.de_un_mensaje(base, enviado)
    assert [e["que"] for e in registro] == ["mensaje_enviado"]
    assert (await base["mensajes"].find_one({"_id": enviado}))["estado"] == Estado.ENVIADO


# ---------------------------------------------------------------------------
# 6. Un envío falla de las peores maneras
# ---------------------------------------------------------------------------


@sin_mongo
async def test_un_contacto_que_no_coincide_no_se_reintenta_nunca(base) -> None:
    """⚠️ Reintentar sería insistir con el chat equivocado.

    Es la forma exacta de convertir un aborto correcto —el sistema haciendo su
    trabajo— en el error más caro que puede cometer.
    """
    from app.core import corridas

    corrida_id = await corrida_lista(base, cuantos=1)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)

    job = await cola.tomar(base, "mac-rocio", ahora=AHORA)
    reporte = await cola.reportar(
        base, job["_id"], ok=False, codigo=cola.Codigo.CONTACTO_NO_COINCIDE
    )

    assert not reporte.reintenta
    assert await cola.tomar(base, "mac-rocio", ahora=AHORA + timedelta(days=1)) is None


@sin_mongo
async def test_un_sin_confirmar_no_se_reintenta_porque_puede_haber_salido(base) -> None:
    """Reintentar mandaría el mensaje dos veces. Por eso alerta en vez de insistir."""
    from app.core import corridas

    corrida_id = await corrida_lista(base, cuantos=1)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)

    job = await cola.tomar(base, "mac-rocio", ahora=AHORA)
    reporte = await cola.reportar(base, job["_id"], ok=False, codigo=cola.Codigo.SIN_CONFIRMAR)

    assert not reporte.reintenta


@sin_mongo
async def test_una_sesion_caida_si_se_reintenta(base) -> None:
    """Es transitorio: el vendedor escanea el QR y sigue."""
    from app.core import corridas

    corrida_id = await corrida_lista(base, cuantos=1)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)

    job = await cola.tomar(base, "mac-rocio", ahora=AHORA)
    reporte = await cola.reportar(
        base, job["_id"], ok=False, codigo=cola.Codigo.SESION_CAIDA, ahora=AHORA
    )

    assert reporte.reintenta
    assert await cola.tomar(base, "mac-rocio", ahora=AHORA + timedelta(hours=1)) is not None


# ---------------------------------------------------------------------------
# 7. Todo junto
# ---------------------------------------------------------------------------


@sin_mongo
async def test_una_corrida_con_todo_saliendo_mal_igual_cierra_las_cuentas(base) -> None:
    """El escenario feo completo: uno sale, uno falla, uno se cuelga, uno se veta.

    Al final, cada mensaje está en exactamente un estado, y la auditoría tiene
    una entrada por cada uno que salió o que no va a salir.
    """
    from app.core import corridas

    corrida_id = await corrida_lista(base, cuantos=4)
    await corridas.preparar_envios(base, corrida_id, quien="panel", ahora=AHORA)
    listos = await mensajes.de_la_corrida(base, corrida_id)

    # 1. Uno sale bien.
    await mensajes.mover(base, listos[0]["_id"], Estado.ENVIANDO, ahora=AHORA)
    await mensajes.mover(base, listos[0]["_id"], Estado.ENVIADO, quien="mac-rocio", ahora=AHORA)

    # 2. Uno falla sin reintento.
    await mensajes.mover(base, listos[1]["_id"], Estado.ENVIANDO, ahora=AHORA)
    await mensajes.mover(
        base, listos[1]["_id"], Estado.DESCARTADO, motivo=Motivo.FALLIDO, ahora=AHORA
    )

    # 3. Uno se cuelga y lo recupera el barrido.
    await mensajes.mover(base, listos[2]["_id"], Estado.ENVIANDO, ahora=AHORA)
    await mensajes.mover(base, listos[2]["_id"], Estado.EN_ESPERA, ahora=AHORA)

    # 4. Uno lo veta una persona.
    await mensajes.mover(
        base, listos[3]["_id"], Estado.DESCARTADO, motivo=Motivo.VETADO, quien="panel", ahora=AHORA
    )

    conteo = await mensajes.contar_por_estado(base, corrida_id)
    assert conteo == {str(Estado.ENVIADO): 1, str(Estado.DESCARTADO): 2, str(Estado.EN_ESPERA): 1}

    # Uno enviado + dos descartados = tres entradas de auditoría.
    eventos = await base["auditoria"].count_documents({})
    assert eventos >= 3

    enviados = await auditoria.contar(
        base, que=auditoria.Que.MENSAJE_ENVIADO, desde=AHORA - timedelta(minutes=1)
    )
    assert enviados == 1, "exactamente uno salió, y quedó anotado una sola vez"
