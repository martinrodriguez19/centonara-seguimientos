"""Los contactos a los que el pase único no vuelve a escribir (D42).

Un chat con un reclamo abierto, o uno donde el cliente ya compró, se saltea en
la tanda en que se lo lee — eso lo decide el modelo con las reglas de D41. Lo
que este módulo agrega es **memoria**: que la corrida siguiente no vuelva a
abrir ese chat, no vuelva a pagar la lectura, y no dependa de que el modelo
acierte dos veces seguidas.

Tres cosas que conviene tener presentes:

- **Se llena sola**, desde el reporte de cada tanda. No hay pantalla de carga:
  el veto nace de lo que el modelo vio, con la cita que lo justifica.
- **Vence.** Un veto perpetuo es una lista negra que nadie decidió armar: un
  cliente que reclamó en marzo puede volver a interesar el año que viene. Los
  días viven en la configuración, por motivo.
- **Entra primero a `no_escribir`.** Esa lista se trunca, y el orden decide
  quién se cae: los vetados van arriba de los recientes, siempre. Un reciente
  que se cae recibe un segundo borrador; un vetado que se cae recibe un
  seguimiento arriba de un reclamo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId

from app.core.contactos import NumeroInvalido, normalizar
from app.logging import obtener_logger

log = obtener_logger(__name__)

# Los dos motivos que vetan (D41) y el campo de configuración con sus días.
MOTIVOS = {
    "disconforme": "dias_veto_disconforme",
    "ya_compro": "dias_veto_ya_compro",
}

# Cuántos nombres vetados viajan como máximo. Es la mitad de `MAX_NO_ESCRIBIR`
# a propósito: la lista es de los dos, y una de vetados que la llene entera
# dejaría afuera a todos los recientes — que es el otro duplicado que evita.
MAX_EN_LISTA = 60


def clave(nombre: str, telefono: Any) -> str:
    """Por número cuando se puede, por nombre cuando no. Nunca se deduce un número."""
    if telefono:
        try:
            return normalizar(str(telefono))
        except NumeroInvalido:
            pass
    return f"nombre:{nombre[:100]}"


async def registrar(
    base,
    *,
    maquina: str,
    chat: dict[str, Any],
    motivo: str,
    corrida_id: ObjectId,
    config: dict[str, Any],
    ahora: datetime | None = None,
) -> bool:
    """Un chat que el modelo marcó `disconforme` o `ya_compro` pasa a la memoria.

    Idempotente por `(maquina, clave)`: leer el mismo chat dos veces renueva el
    vencimiento y actualiza el motivo — el último visto es el que vale. `False`
    si el motivo no es de los que vetan, que no es un error: es un salteo común.
    """
    campo = MOTIVOS.get(motivo)
    if campo is None:
        return False
    momento = ahora or datetime.now(UTC)
    nombre = str(chat.get("contacto_nombre") or "").strip()[:120]
    if not nombre:
        return False
    dias = max(1, int(config.get(campo, 180)))

    await base["vetados"].update_one(
        {"maquina": maquina, "clave": clave(nombre, chat.get("contacto_telefono"))},
        {
            "$set": {
                "nombre": nombre,
                "motivo": motivo,
                "cita": str(chat.get("cita") or chat.get("ultimo_mensaje_resumen") or "")[:80],
                "corrida_id": corrida_id,
                "actualizado_en": momento,
                "vence_en": momento + timedelta(days=dias),
            },
            "$setOnInsert": {"creado_en": momento},
        },
        upsert=True,
    )
    log.info("contacto_vetado", maquina=maquina, contacto=nombre[:60], motivo=motivo, dias=dias)
    return True


async def vigentes(base, maquina: str, *, ahora: datetime | None = None) -> list[str]:
    """Los nombres vetados de esta máquina que todavía no vencieron, los más nuevos primero."""
    momento = ahora or datetime.now(UTC)
    filas = (
        await base["vetados"]
        .find({"maquina": maquina, "vence_en": {"$gt": momento}}, {"nombre": 1})
        .sort("actualizado_en", -1)
        .limit(MAX_EN_LISTA)
        .to_list(None)
    )
    return [str(f["nombre"]) for f in filas if str(f.get("nombre") or "").strip()]


async def listar(base, *, maquina: str | None = None) -> list[dict[str, Any]]:
    """Todos los vetos, vencidos incluidos, para el panel o para la API."""
    filtro: dict[str, Any] = {"maquina": maquina} if maquina else {}
    filas = await base["vetados"].find(filtro).sort("actualizado_en", -1).to_list(500)
    return [
        {
            "id": str(f["_id"]),
            "maquina": f["maquina"],
            "nombre": f.get("nombre", ""),
            "clave": f.get("clave", ""),
            "motivo": f.get("motivo", ""),
            "cita": f.get("cita", ""),
            "creado_en": f.get("creado_en"),
            "vence_en": f.get("vence_en"),
        }
        for f in filas
    ]


async def levantar(base, veto_id: ObjectId, *, quien: str) -> bool:
    """Saca a alguien de la lista, a mano. Queda en el log con quién lo hizo."""
    resultado = await base["vetados"].delete_one({"_id": veto_id})
    if resultado.deleted_count:
        log.warning("veto_levantado", veto=str(veto_id), quien=quien)
    return bool(resultado.deleted_count)
