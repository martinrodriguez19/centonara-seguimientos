"""Tests de las alertas.

Lo que se prueba, además de que cada alerta aparezca cuando corresponde: que
**no aparezca cuando no corresponde**. Un panel con alertas permanentes enseña
a ignorarlas, y la que se ignora es siempre la que importaba.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from bson import ObjectId

from app.core import alertas, cola, configuracion, mensajes, vendedores
from app.core.esquema import inicializar
from app.core.estados import Estado, Motivo

AHORA = datetime(2026, 8, 19, 11, 0, tzinfo=UTC)

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
        await configuracion.obtener(db)
        await vendedores.dar_de_alta(db, maquina="mac-rocio", nombre="Rocío")
        await db["vendedores"].update_one(
            {"maquina": "mac-rocio"},
            {"$set": {"activo": True, "acepto_condiciones_en": AHORA, "ultimo_latido": AHORA}},
        )
        yield db
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


def codigos(encontradas) -> set[str]:
    return {a.codigo for a in encontradas}


# ---------------------------------------------------------------------------
# El estado tranquilo
# ---------------------------------------------------------------------------


@sin_mongo
async def test_un_sistema_sano_no_grita_nada(base) -> None:
    """Si esto falla, el panel va a tener una alerta permanente y nadie las va a leer."""
    assert await alertas.revisar(base, ahora=AHORA) == []


# ---------------------------------------------------------------------------
# Urgentes
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_selector_roto_es_urgente(base) -> None:
    """Frena la corrida entera: hasta que alguien lo toque no sale nada."""
    await base["jobs"].insert_one(
        {
            "tipo": str(cola.Tipo.ENVIAR),
            "codigo": str(cola.Codigo.SELECTOR_ROTO),
            "estado": str(cola.EstadoJob.FALLIDO),
            "terminado_en": AHORA,
        }
    )

    encontradas = await alertas.revisar(base, ahora=AHORA)
    alerta = next(a for a in encontradas if a.codigo == "selector_roto")
    assert alerta.nivel is alertas.Nivel.URGENTE
    assert alerta.accion, "una alerta sin acción es una queja"


@sin_mongo
async def test_un_selector_roto_viejo_ya_no_alerta(base) -> None:
    """Si fue hace tres días y ya se arregló, no tiene que seguir gritando."""
    await base["jobs"].insert_one(
        {
            "tipo": str(cola.Tipo.ENVIAR),
            "codigo": str(cola.Codigo.SELECTOR_ROTO),
            "estado": str(cola.EstadoJob.FALLIDO),
            "terminado_en": AHORA - timedelta(days=3),
        }
    )
    assert "selector_roto" not in codigos(await alertas.revisar(base, ahora=AHORA))


@sin_mongo
async def test_los_sin_confirmar_son_la_alerta_mas_importante(base) -> None:
    """⚠️ "No sabemos si salió" es peor que "no salió".

    Un fallido no llegó a nadie. Éste puede haber llegado, y la única forma de
    saberlo es que una persona abra ese chat y mire.
    """
    mensaje_id = await mensajes.crear_borrador(
        base,
        corrida_id=ObjectId(),
        maquina="mac-rocio",
        contacto_id="+5491144405036",
        contacto_nombre="Ferretería Sur",
        texto="Hola",
        ahora=AHORA,
    )
    await base["mensajes"].update_one(
        {"_id": mensaje_id},
        {"$set": {"estado": str(Estado.DESCARTADO), "motivo": str(Motivo.SIN_CONFIRMAR)}},
    )

    alerta = next(
        a for a in await alertas.revisar(base, ahora=AHORA) if a.codigo == "sin_confirmar"
    )
    assert alerta.nivel is alertas.Nivel.URGENTE
    assert "Ferretería Sur" in alerta.detalle, "dice a quién, no sólo cuántos"


@sin_mongo
async def test_una_corrida_frenada_por_el_canario_alerta(base) -> None:
    await base["corridas"].insert_one({"estado": "frenada", "creada_en": AHORA})
    assert "canario_fallido" in codigos(await alertas.revisar(base, ahora=AHORA))


@sin_mongo
async def test_una_maquina_caida_con_trabajo_esperando_es_urgente(base) -> None:
    """Hay alguien esperando algo que no está pasando."""
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"},
        {"$set": {"ultimo_latido": AHORA - timedelta(minutes=30)}},
    )
    await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio", ahora=AHORA)

    alerta = next(
        a for a in await alertas.revisar(base, ahora=AHORA) if a.codigo == "maquina_caida"
    )
    assert alerta.nivel is alertas.Nivel.URGENTE
    assert "Rocío" in alerta.titulo, "el nombre de la persona, no el de la máquina"


@sin_mongo
async def test_una_maquina_caida_SIN_trabajo_no_alerta(base) -> None:
    """⚠️ Una Mac apagada no es noticia.

    Por eso el agente consulta en vez de recibir: el job la espera. Alertar cada
    vez que un vendedor apaga la computadora sería una alerta por día por
    persona, y al mes nadie las mira.
    """
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"},
        {"$set": {"ultimo_latido": AHORA - timedelta(hours=12)}},
    )
    assert "maquina_caida" not in codigos(await alertas.revisar(base, ahora=AHORA))


@sin_mongo
async def test_una_maquina_pausada_no_alerta_aunque_este_caida(base) -> None:
    """El vendedor la pausó a propósito. No hay nada que avisar."""
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"},
        {
            "$set": {
                "ultimo_latido": AHORA - timedelta(hours=2),
                "pausado_hasta": AHORA + timedelta(hours=4),
            }
        },
    )
    await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio", ahora=AHORA)

    assert "maquina_caida" not in codigos(await alertas.revisar(base, ahora=AHORA))


# ---------------------------------------------------------------------------
# Avisos
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_kill_switch_puesto_es_un_aviso_no_una_urgencia(base) -> None:
    """Alguien lo apretó a propósito. Pero tiene que verse: un sistema frenado
    que nadie recuerda haber frenado se ve igual que uno roto."""
    await configuracion.pausar(base, pausado=True, quien="prueba")

    alerta = next(a for a in await alertas.revisar(base, ahora=AHORA) if a.codigo == "pausa_global")
    assert alerta.nivel is alertas.Nivel.AVISO


@sin_mongo
async def test_una_maquina_degradada_es_un_aviso(base) -> None:
    """Está viva y conectada, pero no va a tomar envíos."""
    await vendedores.registrar_latido(
        base, "mac-rocio", diagnostico={"claude_bin": "falla", "chrome": "ok"}, ahora=AHORA
    )

    alerta = next(
        a for a in await alertas.revisar(base, ahora=AHORA) if a.codigo == "maquina_degradada"
    )
    assert alerta.nivel is alertas.Nivel.AVISO
    assert "claude_bin" in alerta.detalle, "dice QUÉ chequeo falla"


@sin_mongo
async def test_un_na_en_el_diagnostico_no_es_una_falla(base) -> None:
    """Los chequeos de navegador dan n/a mientras se desarrolla en Windows."""
    await vendedores.registrar_latido(
        base, "mac-rocio", diagnostico={"selectores": "n/a", "chrome": "ok"}, ahora=AHORA
    )
    assert "maquina_degradada" not in codigos(await alertas.revisar(base, ahora=AHORA))


# ---------------------------------------------------------------------------
# El orden y la forma
# ---------------------------------------------------------------------------


@sin_mongo
async def test_las_urgentes_van_primero(base) -> None:
    await configuracion.pausar(base, pausado=True, quien="prueba")
    await base["corridas"].insert_one({"estado": "frenada", "creada_en": AHORA})

    encontradas = await alertas.revisar(base, ahora=AHORA)
    assert encontradas[0].nivel is alertas.Nivel.URGENTE


@sin_mongo
async def test_toda_alerta_dice_que_hacer(base) -> None:
    """Una alerta sin acción es una queja."""
    await configuracion.pausar(base, pausado=True, quien="prueba")
    await base["corridas"].insert_one({"estado": "frenada", "creada_en": AHORA})
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"}, {"$set": {"ultimo_latido": AHORA - timedelta(hours=1)}}
    )
    await cola.encolar(base, tipo=cola.Tipo.ENVIAR, maquina="mac-rocio", ahora=AHORA)

    for alerta in await alertas.revisar(base, ahora=AHORA):
        assert alerta.accion, f"{alerta.codigo} no dice qué hacer"
        assert alerta.titulo
        assert alerta.detalle


def test_solo_hay_dos_niveles() -> None:
    """Nada de "informativo": una alerta que no pide nada es un número."""
    assert len(alertas.Nivel) == 2
