"""Que los tipos del panel describan lo que el backend devuelve de verdad.

`docs/RETOMAR.md` anotaba el riesgo con todas las letras: *"el panel se escribió
contra los tipos del cliente de API, no contra respuestas reales"*. Casi tres mil
líneas de TypeScript compiladas contra tipos escritos a mano, y ningún test que
comparara esos tipos con un `dict` real.

Compilar no ayuda acá. Los endpoints del panel devuelven `dict[str, Any]`, así
que el esquema de OpenAPI sale como `{"type": "object"}` y `tsc` valida los
tipos del panel **contra sí mismos**. Un campo que el backend deja de mandar, o
uno nuevo que nadie llevó a la pantalla, pasan los dos en verde.

Este test lee `frontend/lib/panel.ts`, saca los campos de cada `export type`, y
los compara con la respuesta real. Encontró que `/configuracion` devolvía
`palabras_comerciales` —la lista que decide si un chat parece de trabajo, y la
que mueve la tasa de retención que la pantalla de métricas manda calibrar— sin
que la pantalla de configuración pudiera tocarla.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

import pytest

from app import db
from app.api import panel
from app.api.panel import AltaMaquina, CambioMaquina, NuevaCorrida
from app.core.esquema import inicializar

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)

PANEL_TS = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "panel.ts"

# Campos que el tipo declara y la respuesta puede no traer. `actualizado_en`
# aparece recién con el primer cambio guardado.
OPCIONALES = {"Configuracion": {"actualizado_en"}}


def campos_declarados() -> dict[str, set[str]]:
    """Los campos de cada `export type X = { ... }` de `panel.ts`.

    Deliberadamente tonto: un parser de TypeScript acá sería más frágil que la
    convención de que los tipos del panel se escriben planos, uno por línea.
    """
    texto = PANEL_TS.read_text(encoding="utf-8")
    tipos: dict[str, set[str]] = {}
    for bloque in re.finditer(r"export type (\w+) = \{(.*?)\n\};", texto, re.S):
        cuerpo = re.sub(r"/\*.*?\*/", "", bloque.group(2), flags=re.S)
        tipos[bloque.group(1)] = set(re.findall(r"^\s*(\w+)\??:", cuerpo, re.M))
    return tipos


def comparar(tipo: str, respuesta: dict) -> None:
    """Los dos lados, no uno.

    Que falte un campo rompe la pantalla. Que sobre es más silencioso y por eso
    peor: es una capacidad del backend que nadie puede usar, y nadie se entera.
    """
    declarados = campos_declarados()[tipo]
    devueltos = set(respuesta)
    faltan = declarados - devueltos - OPCIONALES.get(tipo, set())
    sobran = devueltos - declarados
    assert not faltan, f"{tipo}: el panel espera y el backend no devuelve {sorted(faltan)}"
    assert not sobran, f"{tipo}: el backend devuelve y el panel ignora {sorted(sobran)}"


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


@sin_mongo
async def test_el_panel_ts_declara_los_tipos_que_se_comparan() -> None:
    """Si el parser deja de encontrarlos, los demás tests pasarían vacíos."""
    tipos = campos_declarados()
    for nombre in ("Estado", "Maquina", "Corrida", "Configuracion", "Metricas", "Revision"):
        assert tipos.get(nombre), f"no se pudo leer el tipo {nombre} de panel.ts"


@sin_mongo
async def test_estado_vacio_coincide(base) -> None:
    """Sin datos: es lo primero que ve el panel la primera vez que se abre."""
    comparar("Estado", await panel.estado(None))


@sin_mongo
async def test_configuracion_coincide(base) -> None:
    comparar("Configuracion", await panel.ver_configuracion(None))


@sin_mongo
async def test_metricas_coinciden(base) -> None:
    comparar("Metricas", await panel.ver_metricas(None))


@sin_mongo
async def test_maquina_coincide(base) -> None:
    await panel.alta_maquina(AltaMaquina(maquina="pc-1", nombre="Prueba"), None)
    estado = await panel.estado(None)
    comparar("Maquina", estado["maquinas"][0])


@sin_mongo
async def test_corrida_y_revision_coinciden(base) -> None:
    """Dar de alta no alcanza: hay que activar. Es la regla de F5.8."""
    await panel.alta_maquina(AltaMaquina(maquina="pc-1", nombre="Prueba"), None)
    await panel.editar_maquina("pc-1", CambioMaquina(activo=True, acepto_condiciones=True), None)

    disparo = await panel.disparar_corrida(NuevaCorrida(tipo="diagnostico"), None)
    comparar("Corrida", await panel.ver_corrida(disparo["id"], None))
    comparar("Revision", await panel.mensajes_de_la_corrida(disparo["id"], None))
