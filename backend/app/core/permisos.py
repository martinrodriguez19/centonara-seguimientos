"""El rol de MongoDB con el que se conecta el backend.

**MongoDB no sabe prohibir.** Los roles sólo otorgan: no existe "readWrite pero
sin update sobre esta colección". Por eso hay que enumerar colección por
colección — si se diera `readWrite` sobre la base entera, `update` sobre
`auditoria` vendría incluido y no habría forma de sacárselo después.

Esa limitación es la razón de que este módulo exista en vez de una línea de
configuración.

La definición vive acá, en Python, porque es lo que testea la suite: se aplica
contra un Mongo de verdad y se verifica que un `update` sobre `auditoria` falla.
`infra/mongo/01-usuario-app.js` es la misma definición para el arranque del
contenedor y para copiar a la consola de Atlas, y hay un test que verifica que
las dos no se hayan desincronizado.
"""

from __future__ import annotations

from typing import Any

NOMBRE_DEL_ROL = "app_seguimiento"

# Todo lo que el backend necesita hacer con una colección normal.
ESCRITURA = (
    "find",
    "insert",
    "update",
    "remove",
    "createIndex",
    "createCollection",
    "listIndexes",
    "listCollections",
    "dropCollection",
)

# ⚠️ Sobre `auditoria`: leer y agregar. Nada más.
#
# Sin `update` y sin `remove`. Es lo que convierte la regla R5 —"el registro es
# inmutable"— de una convención que alguien puede olvidar en una restricción que
# la base aplica sola.
SOLO_AGREGAR = ("find", "insert", "createIndex", "listIndexes", "listCollections")

CON_ESCRITURA = ("vendedores", "corridas", "mensajes", "jobs", "configuracion", "telefonos")

SOLO_AGREGADO = ("auditoria",)


def privilegios(base: str) -> list[dict[str, Any]]:
    """Los privilegios del rol, para una base dada."""
    lista: list[dict[str, Any]] = [
        {"resource": {"db": base, "collection": coleccion}, "actions": list(ESCRITURA)}
        for coleccion in CON_ESCRITURA
    ]
    lista += [
        {"resource": {"db": base, "collection": coleccion}, "actions": list(SOLO_AGREGAR)}
        for coleccion in SOLO_AGREGADO
    ]
    # Para asegurar el esquema al arrancar: listar y crear colecciones.
    lista.append(
        {
            "resource": {"db": base, "collection": ""},
            "actions": ["listCollections", "createCollection"],
        }
    )
    return lista


def comando_crear_rol(base: str, nombre: str = NOMBRE_DEL_ROL) -> dict[str, Any]:
    """El `createRole` listo para mandarle a Mongo."""
    return {"createRole": nombre, "privileges": privilegios(base), "roles": []}


def comando_crear_usuario(
    usuario: str, clave: str, base: str, nombre_del_rol: str = NOMBRE_DEL_ROL
) -> dict[str, Any]:
    return {
        "createUser": usuario,
        "pwd": clave,
        "roles": [{"role": nombre_del_rol, "db": base}],
    }
