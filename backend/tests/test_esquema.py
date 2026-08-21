"""Tests del esquema: colecciones e índices.

Dos grupos, con distinto requisito:

- Los de **declaración** miran `COLECCIONES` y corren en cualquier lado. Son los
  que detectan que alguien tocó un índice que era una regla de negocio.
- Los de **comportamiento** necesitan un Mongo de verdad. Se saltean si no hay
  uno, y en CI lo hay: sin Mongo real no se puede verificar que un índice único
  rechaza el duplicado, que es justamente lo que queremos saber.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from app.core.esquema import (
    COLECCIONES,
    RETENCION_JOBS_DIAS,
    RETENCION_RESUMEN_DIAS,
    Indice,
    inicializar,
    purgar_resumenes,
)

POR_NOMBRE = {c.nombre: c for c in COLECCIONES}


def indices_de(coleccion: str) -> dict[str, Indice]:
    return {i.nombre: i for i in POR_NOMBRE[coleccion].indices}


# ---------------------------------------------------------------------------
# Declaración — sin base de datos
# ---------------------------------------------------------------------------


def test_estan_las_seis_colecciones() -> None:
    assert set(POR_NOMBRE) == {
        "vendedores",
        "corridas",
        "mensajes",
        "jobs",
        "auditoria",
        "configuracion",
    }


def test_ninguna_coleccion_esta_declarada_dos_veces() -> None:
    assert len(POR_NOMBRE) == len(COLECCIONES)


def test_toda_coleccion_explica_para_que_es() -> None:
    for coleccion in COLECCIONES:
        assert coleccion.porque, f"{coleccion.nombre} no dice para qué es"


def test_ningun_indice_esta_declarado_dos_veces() -> None:
    for coleccion in COLECCIONES:
        nombres = [i.nombre for i in coleccion.indices]
        assert len(nombres) == len(set(nombres)), coleccion.nombre


def test_la_clave_de_idempotencia_es_unica() -> None:
    """Es lo que impide que un reintento mande el mismo mensaje dos veces.

    Si alguien saca el `unique`, el anti-duplicado pasa a depender de un `if`
    que una condición de carrera puede esquivar.
    """
    assert indices_de("mensajes")["clave_idempotencia_1"].unico


def test_la_maquina_es_unica() -> None:
    """Dos máquinas con el mismo nombre serían dos agentes sobre la misma cola."""
    assert indices_de("vendedores")["maquina_1"].unico


def test_el_indice_de_la_cola_tiene_las_tres_claves_en_orden() -> None:
    """El orden importa: se filtra por estado y máquina, se ordena por fecha.

    Con las claves en otro orden, la consulta que corre cada 10 segundos por
    cada máquina deja de usar el índice.
    """
    indice = indices_de("jobs")["estado_1_maquina_1_disponible_desde_1"]
    assert indice.claves == (
        ("estado", ASCENDING),
        ("maquina", ASCENDING),
        ("disponible_desde", ASCENDING),
    )


def test_el_anti_duplicado_busca_por_contacto_y_fecha() -> None:
    """Guardrail G5: ¿le escribimos a este contacto en los últimos siete días?"""
    indice = indices_de("mensajes")["contacto_id_1_creado_en_-1"]
    assert indice.claves == (("contacto_id", ASCENDING), ("creado_en", DESCENDING))


def test_los_jobs_terminados_vencen_y_los_vivos_no() -> None:
    """El TTL va sobre `terminado_en`, que un job vivo no tiene.

    Mongo ignora los documentos donde el campo del índice TTL no es una fecha,
    así que la cola no se vacía sola. Si el TTL fuera sobre `creado_en`, un job
    encolado hace un mes desaparecería sin haberse ejecutado.
    """
    indice = indices_de("jobs")["terminado_en_1"]
    assert indice.claves == (("terminado_en", ASCENDING),)
    assert indice.expira_en_segundos == RETENCION_JOBS_DIAS * 24 * 60 * 60


def test_la_auditoria_no_vence_nunca() -> None:
    """R5: es lo único que responde el día que un cliente pregunte."""
    for indice in POR_NOMBRE["auditoria"].indices:
        assert indice.expira_en_segundos is None


def test_los_mensajes_no_tienen_ttl() -> None:
    """El texto que enviamos se guarda indefinidamente (D1).

    El resumen de la conversación del cliente sí vence, pero con un `$unset`
    programado y no con un TTL — un TTL borraría el documento entero, y con él
    el mensaje que mandamos.
    """
    for indice in POR_NOMBRE["mensajes"].indices:
        assert indice.expira_en_segundos is None


def test_el_nombre_del_indice_se_deriva_de_sus_claves() -> None:
    """Nombre estable: si cambiara, Mongo crearía un índice nuevo al lado."""
    indice = Indice(claves=(("a", ASCENDING), ("b", DESCENDING)))
    assert indice.nombre == "a_1_b_-1"


def test_el_modelo_de_pymongo_lleva_las_opciones_declaradas() -> None:
    modelo = Indice(
        claves=(("x", ASCENDING),), unico=True, expira_en_segundos=60, parcial={"x": {"$gt": 0}}
    ).a_modelo()
    documento = modelo.document
    assert documento["unique"] is True
    assert documento["expireAfterSeconds"] == 60
    assert documento["partialFilterExpression"] == {"x": {"$gt": 0}}
    assert documento["name"] == "x_1"


# ---------------------------------------------------------------------------
# Comportamiento — necesita un Mongo de verdad
# ---------------------------------------------------------------------------

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"),
    reason="necesita un Mongo real: definí MONGO_URL_TESTS (docker compose up mongo)",
)


@pytest.fixture
async def base():
    """Una base limpia por test, que se borra al terminar.

    El nombre lleva un `uuid4` y no una marca de tiempo. Con segundos de
    resolución, dos tests que arrancan en el mismo segundo comparten base — y
    el `drop_database` de uno se lleva puestos los datos del otro. Pasa siempre
    que la suite corre rápido, que es justamente en CI.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    try:
        yield cliente[nombre]
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


@sin_mongo
async def test_inicializar_crea_todas_las_colecciones(base) -> None:
    await inicializar(base)
    assert set(await base.list_collection_names()) >= set(POR_NOMBRE)


@sin_mongo
async def test_inicializar_es_idempotente(base) -> None:
    """El criterio de salida de F1.3: correrlo dos veces no rompe nada."""
    primera = await inicializar(base)
    segunda = await inicializar(base)
    assert primera == segunda


@sin_mongo
async def test_crea_todos_los_indices_declarados(base) -> None:
    resultado = await inicializar(base)
    for coleccion in COLECCIONES:
        for indice in coleccion.indices:
            assert indice.nombre in resultado[coleccion.nombre], (
                f"falta {indice.nombre} en {coleccion.nombre}"
            )


@sin_mongo
async def test_la_clave_de_idempotencia_rechaza_el_duplicado_en_la_base(base) -> None:
    """La prueba que sólo se puede hacer contra Mongo de verdad.

    No alcanza con declarar el índice: hay que ver que el segundo insert falle.
    Es lo que impide que un reintento mande el mismo mensaje dos veces.
    """
    await inicializar(base)
    await base["mensajes"].insert_one({"clave_idempotencia": "abc", "texto": "hola"})
    with pytest.raises(DuplicateKeyError):
        await base["mensajes"].insert_one({"clave_idempotencia": "abc", "texto": "hola de nuevo"})


@sin_mongo
async def test_dos_maquinas_no_pueden_llamarse_igual(base) -> None:
    await inicializar(base)
    await base["vendedores"].insert_one({"maquina": "mac-rocio"})
    with pytest.raises(DuplicateKeyError):
        await base["vendedores"].insert_one({"maquina": "mac-rocio"})


@sin_mongo
async def test_purgar_resumenes_borra_el_viejo_y_deja_el_mensaje(base) -> None:
    """D1: el resumen del cliente vence; el texto que mandamos nosotros, no."""
    await inicializar(base)
    viejo = datetime.now(UTC) - timedelta(days=RETENCION_RESUMEN_DIAS + 1)
    await base["mensajes"].insert_one(
        {
            "clave_idempotencia": "viejo",
            "creado_en": viejo,
            "resumen_ultimo": "preguntó por chapa galvanizada",
            "texto": "Hola Marcelo, quedamos en pasarte el precio.",
        }
    )

    assert await purgar_resumenes(base) == 1

    documento = await base["mensajes"].find_one({"clave_idempotencia": "viejo"})
    assert "resumen_ultimo" not in documento
    assert documento["texto"] == "Hola Marcelo, quedamos en pasarte el precio."


@sin_mongo
async def test_purgar_resumenes_no_toca_los_recientes(base) -> None:
    await inicializar(base)
    await base["mensajes"].insert_one(
        {
            "clave_idempotencia": "reciente",
            "creado_en": datetime.now(UTC) - timedelta(days=1),
            "resumen_ultimo": "pidió presupuesto",
        }
    )

    assert await purgar_resumenes(base) == 0

    documento = await base["mensajes"].find_one({"clave_idempotencia": "reciente"})
    assert documento["resumen_ultimo"] == "pidió presupuesto"


@sin_mongo
async def test_purgar_resumenes_es_idempotente(base) -> None:
    """Corre todos los días: la segunda pasada no tiene que encontrar nada."""
    await inicializar(base)
    await base["mensajes"].insert_one(
        {
            "clave_idempotencia": "viejo",
            "creado_en": datetime.now(UTC) - timedelta(days=RETENCION_RESUMEN_DIAS + 1),
            "resumen_ultimo": "algo",
        }
    )
    assert await purgar_resumenes(base) == 1
    assert await purgar_resumenes(base) == 0
