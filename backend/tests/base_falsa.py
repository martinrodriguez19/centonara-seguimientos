"""Una base de Mongo en memoria, con lo justo que usan las conexiones (D69-D73).

Los tests que necesitan Mongo de verdad se saltean sin `MONGO_URL_TESTS`, y el
dueño pidió no depender de Docker para estos. Esto cubre las operaciones que
tocan `conexiones`, `api/publico` y el latido: `find_one`, `find().sort()`,
`update_one` con `$set` (también con puntos), `$unset`, `$push` con
`$each`/`$slice`, `arrayFilters` de igualdad, `upsert`,
`find_one_and_update` con `$setOnInsert` e `insert_one`.

No pretende ser Mongo: lo que no sabe hacer lo dice con `NotImplementedError`
en vez de inventar un resultado.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

from bson import ObjectId


def _coincide(documento: dict[str, Any], filtro: dict[str, Any]) -> bool:
    for clave, esperado in filtro.items():
        valor = _leer(documento, clave)
        if isinstance(esperado, dict) and any(k.startswith("$") for k in esperado):
            for operador, operando in esperado.items():
                if operador == "$in":
                    if valor not in operando:
                        return False
                elif operador == "$ne":
                    if valor == operando:
                        return False
                else:
                    raise NotImplementedError(operador)
        elif valor != esperado:
            return False
    return True


def _leer(documento: dict[str, Any], ruta: str) -> Any:
    actual: Any = documento
    for parte in ruta.split("."):
        if not isinstance(actual, dict):
            return None
        actual = actual.get(parte)
    return actual


def _escribir(documento: dict[str, Any], ruta: str, valor: Any) -> None:
    partes = ruta.split(".")
    actual = documento
    for parte in partes[:-1]:
        actual = actual.setdefault(parte, {})
    actual[partes[-1]] = valor


def _borrar(documento: dict[str, Any], ruta: str) -> None:
    partes = ruta.split(".")
    actual = documento
    for parte in partes[:-1]:
        actual = actual.get(parte)
        if not isinstance(actual, dict):
            return
    actual.pop(partes[-1], None)


class _Cursor:
    def __init__(self, documentos: list[dict[str, Any]]) -> None:
        self._documentos = documentos

    def sort(self, campo: str, orden: int = 1) -> _Cursor:
        self._documentos.sort(key=lambda d: (_leer(d, campo) is None, _leer(d, campo)))
        if orden < 0:
            self._documentos.reverse()
        return self

    async def to_list(self, _largo: int | None) -> list[dict[str, Any]]:
        return [copy.deepcopy(d) for d in self._documentos]


class Coleccion:
    def __init__(self) -> None:
        self.documentos: list[dict[str, Any]] = []

    async def insert_one(self, documento: dict[str, Any]) -> SimpleNamespace:
        nuevo = copy.deepcopy(documento)
        nuevo.setdefault("_id", ObjectId())
        self.documentos.append(nuevo)
        return SimpleNamespace(inserted_id=nuevo["_id"])

    async def find_one(self, filtro: dict[str, Any] | None = None, **_: Any):
        for documento in self.documentos:
            if _coincide(documento, filtro or {}):
                return copy.deepcopy(documento)
        return None

    def find(self, filtro: dict[str, Any] | None = None) -> _Cursor:
        return _Cursor([d for d in self.documentos if _coincide(d, filtro or {})])

    async def count_documents(self, filtro: dict[str, Any]) -> int:
        return sum(1 for d in self.documentos if _coincide(d, filtro))

    def _aplicar(
        self,
        documento: dict[str, Any],
        operacion: dict[str, Any],
        array_filters: list[dict[str, Any]] | None,
        *,
        insertando: bool,
    ) -> None:
        #  Como Mongo: los `arrayFilters` se evalúan contra el documento de
        #  antes de la actualización, no campo por campo.
        original = copy.deepcopy(documento)
        for operador, campos in operacion.items():
            if operador == "$set":
                for ruta, valor in campos.items():
                    if "$[" in ruta:
                        self._set_filtrado(documento, original, ruta, valor, array_filters or [])
                    else:
                        _escribir(documento, ruta, copy.deepcopy(valor))
            elif operador == "$setOnInsert":
                if insertando:
                    for ruta, valor in campos.items():
                        _escribir(documento, ruta, copy.deepcopy(valor))
            elif operador == "$unset":
                for ruta in campos:
                    _borrar(documento, ruta)
            elif operador == "$push":
                for ruta, valor in campos.items():
                    lista = _leer(documento, ruta) or []
                    if isinstance(valor, dict) and "$each" in valor:
                        lista = lista + copy.deepcopy(valor["$each"])
                        if "$slice" in valor:
                            corte = valor["$slice"]
                            lista = lista[corte:] if corte < 0 else lista[:corte]
                    else:
                        lista = [*lista, copy.deepcopy(valor)]
                    _escribir(documento, ruta, lista)
            else:
                raise NotImplementedError(operador)

    @staticmethod
    def _set_filtrado(documento, original, ruta: str, valor, array_filters) -> None:
        lista_ruta, _, resto = ruta.partition(".$[")
        nombre, _, campo = resto.partition("].")
        condiciones = {
            k.split(".", 1)[1]: v
            for f in array_filters
            for k, v in f.items()
            if k.startswith(nombre + ".")
        }
        antes = _leer(original, lista_ruta) or []
        for indice, elemento in enumerate(_leer(documento, lista_ruta) or []):
            previo = antes[indice] if indice < len(antes) else elemento
            if all(previo.get(k) == v for k, v in condiciones.items()):
                _escribir(elemento, campo, copy.deepcopy(valor))

    async def update_one(
        self,
        filtro: dict[str, Any],
        operacion: dict[str, Any],
        *,
        upsert: bool = False,
        array_filters: list[dict[str, Any]] | None = None,
    ) -> SimpleNamespace:
        for documento in self.documentos:
            if _coincide(documento, filtro):
                self._aplicar(documento, operacion, array_filters, insertando=False)
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            nuevo = copy.deepcopy({k: v for k, v in filtro.items() if not isinstance(v, dict)})
            self._aplicar(nuevo, operacion, array_filters, insertando=True)
            self.documentos.append(nuevo)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def find_one_and_update(
        self, filtro, operacion, *, upsert: bool = False, return_document=None
    ):
        existia = await self.find_one(filtro)
        await self.update_one(filtro, operacion, upsert=upsert)
        if existia is None and not upsert:
            return None
        return await self.find_one(filtro)


class BaseFalsa:
    def __init__(self) -> None:
        self._colecciones: dict[str, Coleccion] = {}

    def __getitem__(self, nombre: str) -> Coleccion:
        return self._colecciones.setdefault(nombre, Coleccion())
