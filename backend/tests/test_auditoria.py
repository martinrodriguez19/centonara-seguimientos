"""Tests de la auditoría, y de que sea inmutable de verdad.

El que importa es `test_un_update_sobre_auditoria_falla_en_la_base`. Todo lo
demás verifica que el módulo hace su trabajo; ése verifica que **aunque alguien
se saltee el módulo, MongoDB lo rechaza igual**.

Necesita un Mongo con autenticación, porque un servidor sin `--auth` no aplica
roles. Por eso el compose local levanta con credenciales: sin eso la
inmutabilidad sería una promesa que nadie puede probar hasta producción.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pymongo.errors import OperationFailure

from app.core import auditoria, permisos
from app.core.esquema import inicializar

# 13 es `Unauthorized` en MongoDB. Se compara el código y no el mensaje: el texto
# cambia entre versiones, el código no.
NO_AUTORIZADO = 13

AHORA = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

SCRIPT_JS = Path(__file__).resolve().parents[2] / "infra" / "mongo" / "01-usuario-app.js"


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
# La definición del rol — sin base de datos
# ---------------------------------------------------------------------------


def test_el_rol_no_otorga_update_ni_remove_sobre_auditoria() -> None:
    """MongoDB no sabe prohibir: la única forma de que no pueda es no otorgarlo."""
    assert "update" not in permisos.SOLO_AGREGAR
    assert "remove" not in permisos.SOLO_AGREGAR


def test_auditoria_esta_en_la_lista_de_solo_agregado() -> None:
    assert "auditoria" in permisos.SOLO_AGREGADO
    assert "auditoria" not in permisos.CON_ESCRITURA


def test_las_demas_colecciones_si_pueden_escribirse() -> None:
    """Si `mensajes` cayera en la lista restringida, el sistema no funcionaría."""
    for coleccion in ("mensajes", "jobs", "vendedores", "corridas", "configuracion"):
        assert coleccion in permisos.CON_ESCRITURA


def test_el_privilegio_de_auditoria_es_el_restringido() -> None:
    de_auditoria = [
        p for p in permisos.privilegios("seguimiento") if p["resource"]["collection"] == "auditoria"
    ]
    assert len(de_auditoria) == 1
    assert set(de_auditoria[0]["actions"]) == set(permisos.SOLO_AGREGAR)


def test_ninguna_coleccion_esta_en_las_dos_listas() -> None:
    assert not set(permisos.CON_ESCRITURA) & set(permisos.SOLO_AGREGADO)


def test_el_rol_cubre_las_seis_colecciones_del_esquema() -> None:
    """Una colección sin privilegio declarado rompería en producción y no acá."""
    from app.core.esquema import COLECCIONES

    declaradas = set(permisos.CON_ESCRITURA) | set(permisos.SOLO_AGREGADO)
    assert {c.nombre for c in COLECCIONES} == declaradas


def test_el_script_de_arranque_no_se_desincronizo_de_python() -> None:
    """Hay dos copias de la definición y tienen que decir lo mismo.

    El `.js` lo corre el contenedor al arrancar y es lo que se copia a la consola
    de Atlas; el Python es lo que testea esta suite contra un Mongo real. Si
    divergen, la suite probaría una cosa y producción tendría otra.
    """
    js = SCRIPT_JS.read_text(encoding="utf-8")

    def arreglo(nombre: str) -> set[str]:
        bloque = re.search(rf"const {nombre} = \[(.*?)\];", js, re.S)
        assert bloque, f"no encontré {nombre} en {SCRIPT_JS.name}"
        return set(re.findall(r'"([a-zA-Z]+)"', bloque.group(1)))

    assert arreglo("SOLO_AGREGAR") == set(permisos.SOLO_AGREGAR)
    assert arreglo("ESCRITURA") == set(permisos.ESCRITURA)
    assert arreglo("CON_ESCRITURA") == set(permisos.CON_ESCRITURA)


# ---------------------------------------------------------------------------
# ⚠️ La inmutabilidad, contra un Mongo de verdad
# ---------------------------------------------------------------------------


@pytest.fixture
async def base_restringida():
    """Una base con el mismo rol que usa producción, y un cliente que lo tiene.

    Se crea todo con el usuario root y se conecta con el restringido: es
    exactamente la relación que hay en Atlas entre la consola y el backend.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    raiz = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    usuario, clave = "app_prueba", uuid4().hex

    db_raiz = raiz[nombre]
    await inicializar(db_raiz)
    await db_raiz.command(permisos.comando_crear_rol(nombre))
    await db_raiz.command(permisos.comando_crear_usuario(usuario, clave, nombre))

    servidor = os.environ["MONGO_URL_TESTS"].split("@")[-1].split("/")[0]
    restringido = AsyncIOMotorClient(
        f"mongodb://{usuario}:{clave}@{servidor}/{nombre}?authSource={nombre}", tz_aware=True
    )
    try:
        yield restringido[nombre]
    finally:
        restringido.close()
        await raiz.drop_database(nombre)
        raiz.close()


@sin_mongo
async def test_con_el_rol_de_produccion_se_puede_agregar_a_la_auditoria(base_restringida) -> None:
    """Lo primero: el rol no rompe lo que el sistema necesita hacer."""
    identificador = await auditoria.registrar(
        base_restringida, que=auditoria.Que.MENSAJE_ENVIADO, quien="mac-rocio"
    )
    assert identificador is not None


@sin_mongo
async def test_un_update_sobre_auditoria_falla_en_la_base(base_restringida) -> None:
    """⚠️ La regla R5, verificada donde tiene que estar.

    No alcanza con que el módulo no exponga una forma de editar: alguien puede
    escribir `base["auditoria"].update_one(...)` directamente. Esto prueba que
    MongoDB lo rechaza igual, con el rol que usa producción.
    """
    await auditoria.registrar(
        base_restringida, que=auditoria.Que.MENSAJE_ENVIADO, quien="mac-rocio"
    )

    with pytest.raises(OperationFailure) as error:
        await base_restringida["auditoria"].update_one(
            {"quien": "mac-rocio"}, {"$set": {"quien": "otro"}}
        )
    assert error.value.code == NO_AUTORIZADO


@sin_mongo
async def test_un_delete_sobre_auditoria_falla_en_la_base(base_restringida) -> None:
    await auditoria.registrar(base_restringida, que=auditoria.Que.KILL_SWITCH, quien="martin")

    with pytest.raises(OperationFailure) as error:
        await base_restringida["auditoria"].delete_many({})
    assert error.value.code == NO_AUTORIZADO


@sin_mongo
async def test_borrar_la_coleccion_entera_tambien_falla(base_restringida) -> None:
    """El atajo obvio para alguien apurado."""
    with pytest.raises(OperationFailure):
        await base_restringida["auditoria"].drop()


@sin_mongo
async def test_las_demas_colecciones_si_se_pueden_modificar(base_restringida) -> None:
    """El rol tiene que restringir `auditoria` y sólo `auditoria`."""
    await base_restringida["mensajes"].insert_one({"clave_idempotencia": "x", "texto": "hola"})
    resultado = await base_restringida["mensajes"].update_one(
        {"clave_idempotencia": "x"}, {"$set": {"texto": "corregido"}}
    )
    assert resultado.modified_count == 1


# ---------------------------------------------------------------------------
# El módulo
# ---------------------------------------------------------------------------


@sin_mongo
async def test_registrar_guarda_quien_que_y_cuando(base) -> None:
    from bson import ObjectId

    mensaje = ObjectId()
    await auditoria.registrar(
        base,
        que=auditoria.Que.MENSAJE_ENVIADO,
        quien="mac-rocio",
        mensaje_id=mensaje,
        detalle={"contacto_id": "+5491144405036"},
        ahora=AHORA,
    )

    documento = await base["auditoria"].find_one({"mensaje_id": mensaje})
    assert documento["que"] == "mensaje_enviado"
    assert documento["quien"] == "mac-rocio"
    assert documento["cuando"] == AHORA
    assert documento["detalle"]["contacto_id"] == "+5491144405036"


@sin_mongo
async def test_la_historia_de_un_mensaje_viene_en_orden(base) -> None:
    """Es lo que se abre cuando un cliente pregunta por un mensaje puntual."""
    from bson import ObjectId

    mensaje = ObjectId()
    for minutos, que in enumerate(
        [
            auditoria.Que.MENSAJE_EDITADO,
            auditoria.Que.MENSAJE_LIBERADO,
            auditoria.Que.MENSAJE_ENVIADO,
        ]
    ):
        await auditoria.registrar(
            base,
            que=que,
            quien="martin",
            mensaje_id=mensaje,
            ahora=AHORA + timedelta(minutes=minutos),
        )

    historia = await auditoria.de_un_mensaje(base, mensaje)
    assert [h["que"] for h in historia] == [
        "mensaje_editado",
        "mensaje_liberado",
        "mensaje_enviado",
    ]


@sin_mongo
async def test_los_recientes_vienen_del_mas_nuevo_al_mas_viejo(base) -> None:
    for minutos in range(5):
        await auditoria.registrar(
            base,
            que=auditoria.Que.CORRIDA_DISPARADA,
            quien="martin",
            ahora=AHORA + timedelta(minutes=minutos),
        )

    recientes = await auditoria.recientes(base, limite=3)
    assert len(recientes) == 3
    assert recientes[0]["cuando"] > recientes[-1]["cuando"]


@sin_mongo
async def test_se_puede_filtrar_por_que_paso(base) -> None:
    await auditoria.registrar(base, que=auditoria.Que.MENSAJE_ENVIADO, quien="mac-1", ahora=AHORA)
    await auditoria.registrar(base, que=auditoria.Que.KILL_SWITCH, quien="martin", ahora=AHORA)

    solo_envios = await auditoria.recientes(base, que=auditoria.Que.MENSAJE_ENVIADO)
    assert len(solo_envios) == 1


@sin_mongo
async def test_contar_es_lo_que_van_a_usar_los_topes(base) -> None:
    """Los topes preguntan acá y no en `mensajes`, porque esto no se pudo editar."""
    ayer = AHORA - timedelta(days=1)
    await auditoria.registrar(base, que=auditoria.Que.MENSAJE_ENVIADO, quien="mac-1", ahora=ayer)
    for _ in range(3):
        await auditoria.registrar(
            base, que=auditoria.Que.MENSAJE_ENVIADO, quien="mac-1", ahora=AHORA
        )

    de_hoy = await auditoria.contar(
        base, que=auditoria.Que.MENSAJE_ENVIADO, desde=AHORA - timedelta(hours=1)
    )
    assert de_hoy == 3


def test_el_modulo_no_expone_ninguna_forma_de_editar() -> None:
    """La segunda capa: que nadie lo escriba en primer lugar.

    El rol de MongoDB protege de un error en producción; esto protege de que el
    error se escriba. Las dos hacen falta.
    """
    publicas = {n for n in dir(auditoria) if not n.startswith("_")}
    assert not {"editar", "actualizar", "borrar", "eliminar", "corregir"} & publicas


@sin_mongo
async def test_se_puede_filtrar_desde_un_momento(base) -> None:
    """Lo que usa la pantalla de historial para mostrar "lo de hoy"."""
    await auditoria.registrar(
        base, que=auditoria.Que.MENSAJE_ENVIADO, quien="mac-1", ahora=AHORA - timedelta(days=2)
    )
    await auditoria.registrar(base, que=auditoria.Que.MENSAJE_ENVIADO, quien="mac-1", ahora=AHORA)

    recientes = await auditoria.recientes(base, desde=AHORA - timedelta(hours=1))
    assert len(recientes) == 1
