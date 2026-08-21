"""Los números que decide mirar el dueño.

Son cuatro, y sólo uno es sobre plata. El más importante es la **tasa de
edición**: qué proporción de borradores reescribe el humano.

Si reescribe el 80%, el sistema no está aportando valor — le está dando trabajo
disfrazado de ayuda — y hay que saberlo antes de que lo diga él. Un panel que
sólo muestra "23 mensajes enviados" no distingue un sistema que funciona de uno
que la gente arregla a mano todos los días.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId

from app.core import auditoria, cola
from app.core.estados import Estado, Motivo


async def de_la_corrida(base, corrida_id: ObjectId) -> dict[str, Any]:
    """Cómo salió una corrida."""
    mensajes = await base["mensajes"].find({"corrida_id": corrida_id}).to_list(None)
    jobs = await base["jobs"].find({"corrida_id": corrida_id}).to_list(None)

    por_estado: dict[str, int] = {}
    for mensaje in mensajes:
        por_estado[mensaje["estado"]] = por_estado.get(mensaje["estado"], 0) + 1

    editados = sum(1 for m in mensajes if m.get("editado_por"))
    revisables = sum(
        1 for m in mensajes if m["estado"] in (Estado.EN_ESPERA, Estado.ENVIADO, Estado.RETENIDO)
    )

    return {
        "mensajes": len(mensajes),
        "por_estado": por_estado,
        "enviados": por_estado.get(str(Estado.ENVIADO), 0),
        "descartados": por_estado.get(str(Estado.DESCARTADO), 0),
        "costo_usd": round(sum(j.get("costo_usd", 0.0) for j in jobs), 4),
        # Sobre lo que una persona pudo mirar. Un rechazado por guardrail nunca
        # estuvo sobre la mesa, así que no dice nada de la calidad del prompt.
        "tasa_edicion": round(editados / revisables, 3) if revisables else 0.0,
        "editados": editados,
    }


async def sincronizar_costo(base, corrida_id: ObjectId) -> float:
    """Suma lo que costaron los jobs y lo guarda en la corrida.

    El costo vive en cada job porque es ahí donde se mide. Acá se acumula para
    que el panel no tenga que sumar cientos de documentos cada vez que alguien
    mira la pantalla.
    """
    jobs = await base["jobs"].find({"corrida_id": corrida_id}).to_list(None)
    total = round(sum(j.get("costo_usd", 0.0) for j in jobs), 4)
    await base["corridas"].update_one({"_id": corrida_id}, {"$set": {"costo_usd": total}})
    return total


async def del_periodo(base, *, dias: int = 30, ahora: datetime | None = None) -> dict[str, Any]:
    """El resumen de los últimos `dias`. Es lo que se mira una vez por semana."""
    momento = ahora or datetime.now(UTC)
    desde = momento - timedelta(days=dias)

    corridas = await base["corridas"].find({"creada_en": {"$gte": desde}}).to_list(None)
    mensajes = await base["mensajes"].find({"creado_en": {"$gte": desde}}).to_list(None)

    enviados = sum(1 for m in mensajes if m["estado"] == Estado.ENVIADO)
    editados = sum(1 for m in mensajes if m.get("editado_por"))
    revisables = sum(
        1 for m in mensajes if m["estado"] in (Estado.EN_ESPERA, Estado.ENVIADO, Estado.RETENIDO)
    )
    retenidos = sum(1 for m in mensajes if m.get("senales") and m["estado"] != Estado.DESCARTADO)

    costo = round(sum(c.get("costo_usd", 0.0) for c in corridas), 4)

    return {
        "dias": dias,
        "corridas": len(corridas),
        "mensajes": len(mensajes),
        "enviados": enviados,
        "costo_usd": costo,
        # Lo que cuesta cada mensaje que efectivamente llegó. Es el número con
        # el que se decide si el sistema es viable, no el total del mes.
        "costo_por_enviado": round(costo / enviados, 4) if enviados else 0.0,
        "tasa_edicion": round(editados / revisables, 3) if revisables else 0.0,
        # El objetivo es 10 a 20%. Fuera de ahí, el triage hay que calibrarlo:
        # por encima molesta y alguien lo va a apagar, por debajo no está
        # atrapando los casos raros que son los caros.
        "tasa_retencion": round(retenidos / revisables, 3) if revisables else 0.0,
        "fallidos": await _fallidos(base, desde),
    }


async def _fallidos(base, desde: datetime) -> dict[str, int]:
    """Por qué fallaron los envíos. Agrupado por código, no un total.

    "Cinco envíos fallaron" no dice nada; "cinco fallaron porque no coincidía el
    contacto" es un incidente y "cinco porque se cayó la sesión" es un martes.
    """
    jobs = (
        await base["jobs"]
        .find(
            {
                "tipo": str(cola.Tipo.ENVIAR),
                "estado": str(cola.EstadoJob.FALLIDO),
                "terminado_en": {"$gte": desde},
            }
        )
        .to_list(None)
    )

    por_codigo: dict[str, int] = {}
    for job in jobs:
        codigo = job.get("codigo") or "sin_codigo"
        por_codigo[codigo] = por_codigo.get(codigo, 0) + 1
    return por_codigo


async def enviados_hoy(base, *, ahora: datetime | None = None) -> int:
    """Cuántos salieron hoy, contados desde la auditoría.

    Desde la auditoría y no desde `mensajes` a propósito: la auditoría es la
    única colección que nadie pudo haber editado, ni siquiera el backend.
    """
    momento = ahora or datetime.now(UTC)
    medianoche = momento.replace(hour=0, minute=0, second=0, microsecond=0)
    return await auditoria.contar(base, que=auditoria.Que.MENSAJE_ENVIADO, desde=medianoche)


async def sin_confirmar(base, *, dias: int = 7, ahora: datetime | None = None) -> int:
    """Cuántos se mandaron sin poder confirmar que llegaron.

    Se cuenta aparte de los fallidos porque no es lo mismo: un fallido no salió,
    y éste **puede haber salido**. Si el número crece, hay algo raro en la
    confirmación y conviene mirarlo antes de que se vuelva costumbre.
    """
    momento = ahora or datetime.now(UTC)
    return await base["mensajes"].count_documents(
        {
            "estado": str(Estado.DESCARTADO),
            "motivo": str(Motivo.SIN_CONFIRMAR),
            "creado_en": {"$gte": momento - timedelta(days=dias)},
        }
    )
