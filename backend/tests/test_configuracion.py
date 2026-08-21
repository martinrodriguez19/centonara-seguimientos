"""Tests de la configuración operativa.

Lo que más importa acá es `destino_permitido`: es la regla R4, lo único que
impide que una corrida alcance a un cliente real mientras el sistema se está
construyendo.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.core import configuracion
from app.core.esquema import inicializar

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


# ---------------------------------------------------------------------------
# Destinos permitidos (R4) — sin base de datos
# ---------------------------------------------------------------------------


def test_una_lista_vacia_significa_a_nadie() -> None:
    """⚠️ La decisión más importante del módulo.

    El estado seguro tiene que ser el que se obtiene sin hacer nada. Si una
    lista vacía significara "a todos", un sistema recién desplegado que nadie
    configuró podría escribirle a cualquiera.
    """
    assert not configuracion.destino_permitido({"destinos_permitidos": []}, "+5491144405036")
    assert not configuracion.destino_permitido({}, "+5491144405036")
    assert not configuracion.destino_permitido({"destinos_permitidos": None}, "+5491144405036")


def test_un_numero_de_la_lista_esta_permitido() -> None:
    config = {"destinos_permitidos": ["+5491144405036", "+5491155667788"]}
    assert configuracion.destino_permitido(config, "+5491144405036")


def test_un_numero_fuera_de_la_lista_no_esta_permitido() -> None:
    config = {"destinos_permitidos": ["+5491144405036"]}
    assert not configuracion.destino_permitido(config, "+5491133445566")


def test_el_asterisco_abre_a_todos() -> None:
    """Es el acto que habilita el sistema para clientes reales."""
    config = {"destinos_permitidos": [configuracion.TODOS]}
    assert configuracion.destino_permitido(config, "+5491133445566")


def test_la_lista_por_defecto_esta_vacia() -> None:
    """Una base recién creada no puede escribirle a nadie."""
    assert configuracion.POR_DEFECTO["destinos_permitidos"] == []


def test_el_sistema_no_arranca_pausado() -> None:
    """La pausa es un acto, no el estado inicial: si arrancara pausado, nadie
    sabría si el kill switch está puesto o si así viene de fábrica."""
    assert configuracion.POR_DEFECTO["pausa_global"] is False


# ---------------------------------------------------------------------------
# Persistencia — con base
# ---------------------------------------------------------------------------


@sin_mongo
async def test_obtener_crea_la_configuracion_si_no_existe(base) -> None:
    config = await configuracion.obtener(base)
    assert config["_id"] == configuracion.ID
    assert config["tope_diario_maquina"] == 20


@sin_mongo
async def test_obtener_no_pisa_lo_que_el_cliente_cambio(base) -> None:
    """`$setOnInsert`: llamarla mil veces no revierte un tope que tocó el dueño."""
    await configuracion.obtener(base)
    await configuracion.actualizar(base, {"tope_diario_maquina": 5})

    config = await configuracion.obtener(base)
    assert config["tope_diario_maquina"] == 5


@sin_mongo
async def test_actualizar_deja_la_marca_de_cuando(base) -> None:
    config = await configuracion.actualizar(base, {"largo_maximo": 400})
    assert config["largo_maximo"] == 400
    assert config["actualizado_en"] is not None


@sin_mongo
async def test_actualizar_rechaza_un_campo_que_no_existe(base) -> None:
    """Un typo en el panel no puede crear un campo fantasma que nadie lee."""
    with pytest.raises(ValueError, match="no existen en la configuración"):
        await configuracion.actualizar(base, {"tope_diarrio_maquina": 5})


@sin_mongo
async def test_actualizar_no_deja_cambiar_el_id(base) -> None:
    with pytest.raises(ValueError):
        await configuracion.actualizar(base, {"_id": "otra"})


@sin_mongo
async def test_se_pueden_agregar_palabras_del_rubro(base) -> None:
    """El cliente va a querer sumar términos suyos sin pedirnos nada."""
    palabras = [*configuracion.POR_DEFECTO["palabras_conflicto"], "faltante", "roto en obra"]
    config = await configuracion.actualizar(base, {"palabras_conflicto": palabras})
    assert "roto en obra" in config["palabras_conflicto"]


@sin_mongo
async def test_el_kill_switch_se_pone_y_se_saca(base) -> None:
    assert await configuracion.esta_pausado(base) is False

    await configuracion.pausar(base, pausado=True, quien="martin")
    assert await configuracion.esta_pausado(base) is True

    await configuracion.pausar(base, pausado=False, quien="martin")
    assert await configuracion.esta_pausado(base) is False


@sin_mongo
async def test_abrir_los_destinos_es_un_cambio_como_cualquier_otro(base) -> None:
    """Deliberado y reversible: se abre y se vuelve a cerrar."""
    await configuracion.actualizar(base, {"destinos_permitidos": [configuracion.TODOS]})
    config = await configuracion.obtener(base)
    assert configuracion.destino_permitido(config, "+5491133445566")

    await configuracion.actualizar(base, {"destinos_permitidos": []})
    config = await configuracion.obtener(base)
    assert not configuracion.destino_permitido(config, "+5491133445566")


@sin_mongo
async def test_cambiar_un_tope_en_una_base_nueva_no_borra_lo_demas(base) -> None:
    """⚠️ Regresión de un bug silencioso.

    `actualizar` hacía `upsert` directo. Sobre una base donde nadie había leído
    la configuración todavía, eso creaba un documento con SÓLO el campo tocado:
    la primera persona que ajustaba un tope desde el panel se llevaba puestas
    las palabras del triage, y el triage dejaba de retener nada — sin un error
    en ningún lado.
    """
    config = await configuracion.actualizar(base, {"tope_diario_maquina": 5})

    assert config["tope_diario_maquina"] == 5
    assert config["palabras_conflicto"], "las palabras del triage siguen ahí"
    assert config["palabras_comerciales"]
    assert config["largo_maximo"] == 600
    assert config["ventana"]["inicio"] == "09:00"


@sin_mongo
async def test_la_configuracion_queda_completa_venga_de_donde_venga(base) -> None:
    """Se lea primero o se escriba primero, el documento tiene todos los campos."""
    await configuracion.actualizar(base, {"largo_maximo": 400})
    config = await configuracion.obtener(base)

    assert set(config) >= set(configuracion.POR_DEFECTO)
