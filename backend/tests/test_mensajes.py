"""Tests del repositorio de mensajes.

Lo que importa acá es que **toda transición pase por `mover`** y que la máquina
de estados no se pueda sortear escribiendo el campo a mano.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from bson import ObjectId

from app.core import auditoria, mensajes
from app.core.esquema import inicializar
from app.core.estados import Estado, Motivo, TransicionInvalida

MIERCOLES = datetime(2026, 8, 19, 11, 0, tzinfo=UTC)

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
        yield db
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


async def crear(base, **extra) -> ObjectId:
    opciones = {
        "corrida_id": ObjectId(),
        "maquina": "mac-rocio",
        "contacto_id": "+5491144405036",
        "contacto_nombre": "Marcelo",
        "texto": "Hola Marcelo, ¿avanzamos con el pedido?",
        "ahora": MIERCOLES,
    }
    opciones.update(extra)
    return await mensajes.crear_borrador(base, **opciones)


# ---------------------------------------------------------------------------
# Crear
# ---------------------------------------------------------------------------


@sin_mongo
async def test_un_borrador_nace_sin_validar(base) -> None:
    """Quien lo mueve a EN_ESPERA es el paso de reglas, no el de creación."""
    mensaje_id = await crear(base)
    documento = await base["mensajes"].find_one({"_id": mensaje_id})

    assert documento["estado"] == Estado.BORRADOR
    assert documento["motivo"] is None
    assert documento["editado_por"] is None


@sin_mongo
async def test_el_mismo_mensaje_dos_veces_no_se_guarda_dos_veces(base) -> None:
    """Lo frena el índice único, no un `if`: una carrera no lo puede esquivar."""
    corrida = ObjectId()
    await crear(base, corrida_id=corrida)

    with pytest.raises(mensajes.MensajeDuplicado):
        await crear(base, corrida_id=corrida)


@sin_mongo
async def test_el_mismo_contacto_en_otra_corrida_si_se_guarda(base) -> None:
    """El anti-duplicado por días es otra cosa (G5) y vive en los guardrails."""
    await crear(base, corrida_id=ObjectId())
    await crear(base, corrida_id=ObjectId())


def test_la_clave_cambia_si_cambia_el_texto() -> None:
    """Editar un borrador lo convierte en otro mensaje, y tiene que poder guardarse."""
    corrida = ObjectId()
    una = mensajes.clave_idempotencia(corrida_id=corrida, contacto_id="+549", texto="Hola")
    otra = mensajes.clave_idempotencia(corrida_id=corrida, contacto_id="+549", texto="Hola!")
    assert una != otra


def test_la_clave_es_la_misma_para_el_mismo_mensaje() -> None:
    corrida = ObjectId()
    args = {"corrida_id": corrida, "contacto_id": "+549", "texto": "Hola"}
    assert mensajes.clave_idempotencia(**args) == mensajes.clave_idempotencia(**args)


# ---------------------------------------------------------------------------
# Mover
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_recorrido_completo_de_un_mensaje_que_sale(base) -> None:
    mensaje_id = await crear(base)

    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, ahora=MIERCOLES)
    await mensajes.mover(base, mensaje_id, Estado.ENVIANDO, ahora=MIERCOLES)
    final = await mensajes.mover(base, mensaje_id, Estado.ENVIADO, ahora=MIERCOLES)

    assert final is Estado.ENVIADO


@sin_mongo
async def test_una_transicion_invalida_no_toca_la_base(base) -> None:
    """La regla vive en `estados.py` y acá se respeta: no hay atajo."""
    mensaje_id = await crear(base)

    with pytest.raises(TransicionInvalida):
        await mensajes.mover(base, mensaje_id, Estado.ENVIANDO, ahora=MIERCOLES)

    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == Estado.BORRADOR, "quedó donde estaba"


@sin_mongo
async def test_solo_en_espera_puede_pasar_a_enviando(base) -> None:
    """A partir de ENVIANDO el agente le escribe a una persona real."""
    mensaje_id = await crear(base)
    await mensajes.mover(base, mensaje_id, Estado.RETENIDO, ahora=MIERCOLES)

    with pytest.raises(TransicionInvalida):
        await mensajes.mover(base, mensaje_id, Estado.ENVIANDO, ahora=MIERCOLES)


@sin_mongo
async def test_descartar_sin_motivo_falla(base) -> None:
    from app.core.estados import MotivoRequerido

    mensaje_id = await crear(base)
    with pytest.raises(MotivoRequerido):
        await mensajes.mover(base, mensaje_id, Estado.DESCARTADO, ahora=MIERCOLES)


@sin_mongo
async def test_mover_un_mensaje_que_no_existe_falla(base) -> None:
    with pytest.raises(mensajes.MensajeDesconocido):
        await mensajes.mover(base, ObjectId(), Estado.EN_ESPERA)


@sin_mongo
async def test_dos_procesos_que_mueven_el_mismo_mensaje_a_la_vez(base) -> None:
    """⚠️ La escritura es condicional al estado de origen.

    Sin eso, el barrido de vencimientos y una persona vetando desde el panel se
    pisarían: los dos leen BORRADOR, los dos escriben, y el segundo tapa la
    decisión del primero sin que nadie se entere.

    **Uno gana y el otro se entera.** Al otro lo frena una de dos defensas,
    según dónde lo agarre:

    - si alcanzó a leer antes de que el primero escribiera, el filtro por estado
      de origen no encuentra el documento → `CarreraDeEstados`;
    - si releyó después, ve el estado nuevo y su transición ya no existe →
      `TransicionInvalida`.

    Cuál de las dos salte depende de cómo se intercale, y no importa: lo que
    importa es que **no ganen los dos**.
    """
    mensaje_id = await crear(base)

    resultados = await asyncio.gather(
        mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, ahora=MIERCOLES),
        mensajes.mover(base, mensaje_id, Estado.RETENIDO, ahora=MIERCOLES),
        return_exceptions=True,
    )

    ganaron = [r for r in resultados if isinstance(r, Estado)]
    frenados = [
        r for r in resultados if isinstance(r, mensajes.CarreraDeEstados | TransicionInvalida)
    ]

    assert len(ganaron) == 1, "sólo uno pudo escribir"
    assert len(frenados) == 1, "al otro lo frenaron en vez de dejarlo pisar"

    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == ganaron[0]


@sin_mongo
async def test_las_senales_del_triage_se_guardan_al_retener(base) -> None:
    """Cada retenido tiene que decir POR QUÉ se retuvo."""
    mensaje_id = await crear(base)
    await mensajes.mover(
        base, mensaje_id, Estado.RETENIDO, senales=["PALABRA_CONFLICTO"], ahora=MIERCOLES
    )

    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["senales"] == ["PALABRA_CONFLICTO"]


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------


@sin_mongo
async def test_enviar_queda_registrado(base) -> None:
    mensaje_id = await crear(base)
    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, ahora=MIERCOLES)
    await mensajes.mover(base, mensaje_id, Estado.ENVIANDO, ahora=MIERCOLES)
    await mensajes.mover(base, mensaje_id, Estado.ENVIADO, quien="mac-rocio", ahora=MIERCOLES)

    eventos = await auditoria.de_un_mensaje(base, mensaje_id)
    assert [e["que"] for e in eventos] == ["mensaje_enviado"]
    assert eventos[0]["quien"] == "mac-rocio"


@sin_mongo
async def test_descartar_queda_registrado_con_el_motivo(base) -> None:
    mensaje_id = await crear(base)
    await mensajes.mover(
        base, mensaje_id, Estado.DESCARTADO, motivo=Motivo.VETADO, quien="panel", ahora=MIERCOLES
    )

    eventos = await auditoria.de_un_mensaje(base, mensaje_id)
    assert eventos[0]["que"] == "mensaje_descartado"
    assert eventos[0]["detalle"]["motivo"] == "vetado"


@sin_mongo
async def test_moverse_entre_estados_intermedios_no_llena_la_auditoria(base) -> None:
    """Sólo se registra lo que le importa a alguien: que salió, o que no va a salir."""
    mensaje_id = await crear(base)
    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, ahora=MIERCOLES)
    await mensajes.mover(base, mensaje_id, Estado.ENVIANDO, ahora=MIERCOLES)

    assert await auditoria.de_un_mensaje(base, mensaje_id) == []


# ---------------------------------------------------------------------------
# Editar
# ---------------------------------------------------------------------------


@sin_mongo
async def test_editar_un_borrador_en_espera(base) -> None:
    mensaje_id = await crear(base)
    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, ahora=MIERCOLES)

    await mensajes.editar_texto(base, mensaje_id, "Texto corregido", quien="martin")

    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["texto"] == "Texto corregido"
    assert documento["editado_por"] == "martin"


@sin_mongo
async def test_editar_cambia_la_clave_de_idempotencia(base) -> None:
    """Si no cambiara, el mensaje editado chocaría con el original."""
    mensaje_id = await crear(base)
    antes = (await base["mensajes"].find_one({"_id": mensaje_id}))["clave_idempotencia"]
    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, ahora=MIERCOLES)

    await mensajes.editar_texto(base, mensaje_id, "Otro texto", quien="martin")

    despues = (await base["mensajes"].find_one({"_id": mensaje_id}))["clave_idempotencia"]
    assert antes != despues


@pytest.mark.parametrize("estado", [Estado.ENVIANDO, Estado.ENVIADO, Estado.DESCARTADO])
@sin_mongo
async def test_no_se_edita_un_mensaje_que_ya_salio_o_esta_saliendo(base, estado: Estado) -> None:
    """Editarlo sería mentir sobre lo que se envió."""
    mensaje_id = await crear(base)
    await base["mensajes"].update_one({"_id": mensaje_id}, {"$set": {"estado": str(estado)}})

    with pytest.raises(mensajes.NoSePuedeEditar):
        await mensajes.editar_texto(base, mensaje_id, "Nuevo", quien="martin")


@sin_mongo
async def test_editar_queda_registrado(base) -> None:
    mensaje_id = await crear(base)
    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, ahora=MIERCOLES)
    await mensajes.editar_texto(base, mensaje_id, "Corregido", quien="martin")

    eventos = await auditoria.de_un_mensaje(base, mensaje_id)
    assert eventos[0]["que"] == "mensaje_editado"


@sin_mongo
async def test_editar_un_mensaje_que_no_existe_falla(base) -> None:
    with pytest.raises(mensajes.MensajeDesconocido):
        await mensajes.editar_texto(base, ObjectId(), "Hola", quien="martin")


# ---------------------------------------------------------------------------
# Vencimiento
# ---------------------------------------------------------------------------


@sin_mongo
async def test_un_borrador_de_mas_de_24_horas_se_descarta(base) -> None:
    """D3: un mensaje con contexto de anteayer es peor que uno que no sale."""
    viejo = MIERCOLES - timedelta(hours=25)
    mensaje_id = await crear(base, ahora=viejo)

    assert await mensajes.vencer_viejos(base, ahora=MIERCOLES) == 1

    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == Estado.DESCARTADO
    assert documento["motivo"] == Motivo.VENCIDO


@sin_mongo
async def test_un_retenido_que_nadie_resolvio_vence_no_se_libera(base) -> None:
    """⚠️ Liberarlos por defecto invertiría el sentido del triage.

    Son justamente los casos donde un error cuesta caro.
    """
    viejo = MIERCOLES - timedelta(hours=25)
    mensaje_id = await crear(base, ahora=viejo)
    await mensajes.mover(base, mensaje_id, Estado.RETENIDO, ahora=viejo)

    await mensajes.vencer_viejos(base, ahora=MIERCOLES)

    documento = await base["mensajes"].find_one({"_id": mensaje_id})
    assert documento["estado"] == Estado.DESCARTADO


@sin_mongo
async def test_un_borrador_reciente_no_vence(base) -> None:
    await crear(base, ahora=MIERCOLES - timedelta(hours=2))
    assert await mensajes.vencer_viejos(base, ahora=MIERCOLES) == 0


@sin_mongo
async def test_un_mensaje_que_ya_salio_no_vence(base) -> None:
    viejo = MIERCOLES - timedelta(hours=30)
    mensaje_id = await crear(base, ahora=viejo)
    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, ahora=viejo)
    await mensajes.mover(base, mensaje_id, Estado.ENVIANDO, ahora=viejo)
    await mensajes.mover(base, mensaje_id, Estado.ENVIADO, ahora=viejo)

    assert await mensajes.vencer_viejos(base, ahora=MIERCOLES) == 0


@sin_mongo
async def test_vencer_es_idempotente(base) -> None:
    """Corre todos los días: la segunda pasada no encuentra nada."""
    await crear(base, ahora=MIERCOLES - timedelta(hours=25))
    assert await mensajes.vencer_viejos(base, ahora=MIERCOLES) == 1
    assert await mensajes.vencer_viejos(base, ahora=MIERCOLES) == 0


@sin_mongo
async def test_el_barrido_no_revienta_si_algo_cambio_debajo(base) -> None:
    """Corre sobre muchos mensajes: uno que se movió no puede tumbar a los demás.

    Se prepara un viejo que sí tiene que vencer y otro que quedó en un estado
    terminal. El barrido saltea el segundo y termina el trabajo.
    """
    viejo = MIERCOLES - timedelta(hours=25)
    vence = await crear(base, contacto_id="+5491100000001", texto="Vence", ahora=viejo)
    ya_salio = await crear(base, contacto_id="+5491100000002", texto="Ya salió", ahora=viejo)

    for estado in (Estado.EN_ESPERA, Estado.ENVIANDO, Estado.ENVIADO):
        await mensajes.mover(base, ya_salio, estado, ahora=viejo)

    assert await mensajes.vencer_viejos(base, ahora=MIERCOLES) == 1

    assert (await base["mensajes"].find_one({"_id": vence}))["estado"] == Estado.DESCARTADO
    assert (await base["mensajes"].find_one({"_id": ya_salio}))["estado"] == Estado.ENVIADO


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------


@sin_mongo
async def test_contar_por_estado(base) -> None:
    corrida = ObjectId()
    for n in range(3):
        await crear(base, corrida_id=corrida, contacto_id=f"+54911000000{n}", texto=f"T{n}")

    conteo = await mensajes.contar_por_estado(base, corrida)
    assert conteo == {"BORRADOR": 3}


@sin_mongo
async def test_la_tasa_de_edicion_es_la_metrica_de_calidad_del_prompt(base) -> None:
    """Si el dueño reescribe el 80%, el sistema no aporta valor y hay que saberlo."""
    corrida = ObjectId()
    ids = [
        await crear(base, corrida_id=corrida, contacto_id=f"+54911000000{n}", texto=f"T{n}")
        for n in range(4)
    ]
    for mensaje_id in ids[:3]:
        await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, ahora=MIERCOLES)
        await mensajes.editar_texto(base, mensaje_id, "reescrito", quien="martin")

    assert await mensajes.tasa_de_edicion(base, corrida) == 0.75


@sin_mongo
async def test_la_tasa_de_edicion_de_una_corrida_vacia_es_cero(base) -> None:
    assert await mensajes.tasa_de_edicion(base, ObjectId()) == 0.0


@sin_mongo
async def test_enviados_hoy_cuenta_desde_la_medianoche(base) -> None:
    ayer = MIERCOLES - timedelta(days=1)
    viejo = await crear(base, contacto_id="+5491100000001", texto="Ayer", ahora=ayer)
    await mensajes.mover(base, viejo, Estado.EN_ESPERA, ahora=ayer)

    hoy = await crear(base, contacto_id="+5491100000002", texto="Hoy", ahora=MIERCOLES)
    await mensajes.mover(base, hoy, Estado.EN_ESPERA, ahora=MIERCOLES)

    assert await mensajes.enviados_hoy(base, "mac-rocio", ahora=MIERCOLES) == 1


@sin_mongo
async def test_varios_borradores_a_la_vez_no_se_pisan(base) -> None:
    """Una corrida encola veinte mensajes en paralelo."""
    corrida = ObjectId()
    ids = await asyncio.gather(
        *(
            crear(base, corrida_id=corrida, contacto_id=f"+549110000{n:04d}", texto=f"T{n}")
            for n in range(20)
        )
    )
    assert len(set(ids)) == 20
