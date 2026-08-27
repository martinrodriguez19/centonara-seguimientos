"""El registro de lo que pasó. Sólo se agrega; no se corrige.

Es lo único que responde el día que un cliente se queje de un mensaje que su
vendedor no escribió. Si se puede editar, no responde nada.

**La inmutabilidad no está acá.** Está en el rol de MongoDB con el que se
conecta el backend, que no otorga `update` ni `remove` sobre esta colección
(`infra/mongo/01-usuario-app.js`). Este módulo colabora no exponiendo ninguna
forma de modificar — pero si alguien escribiera `base["auditoria"].update_one`
salteándolo, la base lo rechazaría igual.

Las dos capas hacen falta y protegen de cosas distintas: el rol, de un error en
producción; no tener API de edición, de que alguien lo escriba en primer lugar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from bson import ObjectId

from app.logging import obtener_logger

log = obtener_logger(__name__)


class Que(StrEnum):
    """Qué pasó. Un conjunto cerrado, para poder contar y filtrar.

    Si hiciera falta uno nuevo se agrega acá: un `que` de texto libre convierte
    el historial en algo que sólo se puede leer a ojo.
    """

    CORRIDA_DISPARADA = "corrida_disparada"
    CORRIDA_CANCELADA = "corrida_cancelada"
    CORRIDA_REANUDADA = "corrida_reanudada"
    """Alguien miró por qué el canario frenó la corrida y decidió continuar
    (D31). Suelta también el kill switch."""
    DATOS_BORRADOS = "datos_borrados"
    """Alguien vació el sistema para entregarlo (D28). El registro de auditoría
    NO se borra —el rol de Mongo ni siquiera lo permite—, así que este evento es
    la marca de dónde empieza la historia del cliente."""
    MENSAJE_ENVIADO = "mensaje_enviado"
    BORRADOR_DEJADO = "borrador_dejado"
    """El texto quedó como borrador en el WhatsApp del vendedor, sin enviarse
    (D30). No es un envío: no cuenta en el tope diario ni como enviado."""
    MENSAJE_VETADO = "mensaje_vetado"
    MENSAJE_EDITADO = "mensaje_editado"
    MENSAJE_LIBERADO = "mensaje_liberado"
    MENSAJE_DESCARTADO = "mensaje_descartado"
    ENVIO_ABORTADO = "envio_abortado"
    KILL_SWITCH = "kill_switch"
    CONFIGURACION_CAMBIADA = "configuracion_cambiada"
    DESTINOS_CAMBIADOS = "destinos_cambiados"
    MAQUINA_ALTA = "maquina_alta"
    MAQUINA_BAJA = "maquina_baja"
    CONSENTIMIENTO_REGISTRADO = "consentimiento_registrado"


# El sistema como autor, cuando no lo pidió una persona: un vencimiento, un
# guardrail, el canario frenándose solo.
SISTEMA = "sistema"


async def registrar(
    base,
    *,
    que: Que,
    quien: str,
    mensaje_id: ObjectId | None = None,
    corrida_id: ObjectId | None = None,
    detalle: dict[str, Any] | None = None,
    ahora: datetime | None = None,
) -> ObjectId:
    """Anota que pasó algo. Es la única forma de escribir en `auditoria`.

    `quien` es una persona (`martin@cliente.com`), una máquina (`mac-rocio`) o
    `SISTEMA`. Los tres son legítimos y hay que poder distinguirlos: "lo frenó
    el sistema" y "lo frenó alguien" son historias distintas.
    """
    documento = {
        "cuando": ahora or datetime.now(UTC),
        "que": str(que),
        "quien": quien,
        "mensaje_id": mensaje_id,
        "corrida_id": corrida_id,
        "detalle": detalle or {},
    }
    resultado = await base["auditoria"].insert_one(documento)
    return resultado.inserted_id


async def de_un_mensaje(base, mensaje_id: ObjectId) -> list[dict[str, Any]]:
    """Todo lo que le pasó a un mensaje, del más viejo al más nuevo.

    Es lo que se abre cuando un cliente pregunta por un mensaje puntual.
    """
    return await base["auditoria"].find({"mensaje_id": mensaje_id}).sort("cuando", 1).to_list(None)


async def recientes(
    base,
    *,
    limite: int = 100,
    que: Que | None = None,
    desde: datetime | None = None,
) -> list[dict[str, Any]]:
    """Lo último que pasó, para la pantalla de historial."""
    filtro: dict[str, Any] = {}
    if que is not None:
        filtro["que"] = str(que)
    if desde is not None:
        filtro["cuando"] = {"$gte": desde}

    return await base["auditoria"].find(filtro).sort("cuando", -1).limit(limite).to_list(None)


async def contar(base, *, que: Que, desde: datetime) -> int:
    """Cuántas veces pasó algo desde un momento.

    Lo usan los topes: "cuántos mensajes salieron hoy" se pregunta acá y no en
    `mensajes`, porque la auditoría es la que no se puede haber editado.
    """
    return await base["auditoria"].count_documents({"que": str(que), "cuando": {"$gte": desde}})
