"""La repesca (D61): una segunda vuelta que revisa el día y completa lo que faltó.

A la hora que fija el panel, mira qué hizo cada máquina hoy contra lo que tenía
que hacer —`tope_diario_borradores`, el número que el dueño piensa (D39)— y a la
que le faltó le larga una corrida sólo a ella. No hay número nuevo: el
presupuesto del pase único ya resta lo dejado hoy, así que una máquina que dejó
14 de 20 hace 6.

Envía si el cliente lo decidió, con la regla de siempre: envío automático
prendido y dentro de la ventana de envío (D52). Fuera de la ventana deja
borradores.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core import (
    auditoria,
    configuracion,
    corridas,
    horarios,
    mensajes,
    programacion,
    vendedores,
)
from app.core.huso import HUSO_COMERCIAL, inicio_del_dia
from app.logging import obtener_logger

log = obtener_logger(__name__)

MARCA = "repesca"

# El final de la tanda que significa "no quedaban chats": la máquina hizo todo
# lo que había, aunque no haya llegado al tope.
SIN_CHATS = frozenset({"fin_de_ventana", "tanda_vacia"})

# Si a la hora de la repesca hay una corrida en curso, se espera; en los
# últimos minutos de la gracia se da por salteada, así queda en la auditoría.
MINUTOS_FINALES_DE_GRACIA = 10

MODOS_CON_PRESUPUESTO = ("extension", "extension_con_respaldo")


async def resumen_del_dia(base, config: dict[str, Any], ahora: datetime) -> list[dict[str, Any]]:
    """Qué hizo hoy cada máquina activa, y en qué quedó. Sin efectos.

    Un resultado por máquina, en este orden de precedencia: `completa`,
    `sin_chats`, `sin_cuota`, `pausada`, `ausente`, `repescada`.
    """
    tope = int(config.get("tope_diario_borradores") or 20)
    desde = inicio_del_dia(ahora)
    corte = ahora - timedelta(minutes=corridas.MINUTOS_SIN_LATIDO)

    ultimas_tandas: dict[str, dict[str, Any]] = {}
    de_hoy = (
        await base["corridas"]
        .find({"creada_en": {"$gte": desde}, "tipo": str(corridas.TipoCorrida.GENERACION)})
        .sort("creada_en", 1)
        .to_list(None)
    )
    for corrida in de_hoy:
        for tanda in corrida.get("tandas") or []:
            if isinstance(tanda, dict) and tanda.get("maquina"):
                ultimas_tandas[tanda["maquina"]] = tanda

    resumen: list[dict[str, Any]] = []
    for vendedor in (
        await base["vendedores"].find({"activo": True}).sort("maquina", 1).to_list(None)
    ):
        maquina = vendedor["maquina"]
        dejados = await mensajes.borradores_dejados_hoy(base, maquina, ahora=ahora)
        latido = vendedor.get("ultimo_latido")
        if latido is not None and latido.tzinfo is None:
            latido = latido.replace(tzinfo=UTC)

        if dejados >= tope:
            resultado = "completa"
        elif (ultimas_tandas.get(maquina) or {}).get("fin") in SIN_CHATS:
            resultado = "sin_chats"
        elif vendedores.sin_cuota_hasta(vendedor, ahora=ahora) is not None:
            resultado = "sin_cuota"
        elif vendedores.esta_pausada(vendedor, ahora=ahora):
            resultado = "pausada"
        elif latido is None or latido < corte:
            resultado = "ausente"
        else:
            resultado = "repescada"

        resumen.append(
            {
                "maquina": maquina,
                "nombre": vendedor.get("nombre") or maquina,
                "dejados": dejados,
                "tope": tope,
                "resultado": resultado,
            }
        )
    return resumen


async def revisar(base, *, ahora: datetime | None = None) -> str | None:
    """La repesca del día, si es la hora. Devuelve qué hizo, o `None`.

    `"disparada"`, `"completo"` (no hacía falta), `"revisada:<motivo>"` (revisó
    pero no largó nada: pausa global, circuito viejo), `"salteada:<motivo>"`, o
    `None` cuando no tocaba o está esperando que termine una corrida en curso.
    """
    momento = ahora or datetime.now(UTC)
    config = await configuracion.obtener(base)
    programa = config.get("repesca") or {}
    if not programacion._toca(programa, momento):
        return None
    if horarios.en_descanso(config, momento):
        return None  # D64

    dia = momento.astimezone(HUSO_COMERCIAL).strftime("%Y-%m-%d")
    if await corridas.en_curso(base) is not None:
        gracia = programacion.HORAS_DE_GRACIA * 60 - MINUTOS_FINALES_DE_GRACIA
        if programacion.minutos_desde_la_hora(programa, momento) < gracia:
            return None  # espera: en cinco minutos vuelve a preguntar
        if not await programacion._tomar_el_dia(base, dia, marca=MARCA):
            return None
        return await programacion._saltear(
            base, motivo="corrida_en_curso", ahora=momento, quien=MARCA
        )

    if not await programacion._tomar_el_dia(base, dia, marca=MARCA):
        return None

    resumen = await resumen_del_dia(base, config, momento)
    faltan = [r["maquina"] for r in resumen if r["resultado"] == "repescada"]

    por_que_no = None
    if not faltan:
        por_que_no = "completo"
    elif bool(config.get("pausa_global")):
        por_que_no = "pausa_global"
    elif str(config.get("modo_borrador", "playwright")) not in MODOS_CON_PRESUPUESTO:
        por_que_no = "circuito_viejo"

    disparo = None
    if por_que_no is None:
        try:
            disparo = await corridas.disparar(
                base,
                quien=MARCA,
                tipo=corridas.TipoCorrida.GENERACION,
                solo=faltan,
                extra={"motivo": MARCA, "revision_del_dia": resumen},
                ahora=momento,
            )
        except corridas.NoHayMaquinas:
            por_que_no = "sin_maquinas"
        except (corridas.Pausado, corridas.CorridaEnCurso) as error:
            por_que_no = type(error).__name__.lower()

    await auditoria.registrar(
        base,
        que=auditoria.Que.REPESCA_REVISADA,
        quien=MARCA,
        corrida_id=disparo.corrida_id if disparo else None,
        detalle={"resumen": resumen, "sin_disparo": por_que_no},
        ahora=momento,
    )
    log.info(
        "repesca_revisada",
        repescadas=faltan,
        corrida=str(disparo.corrida_id) if disparo else None,
        sin_disparo=por_que_no,
    )
    if disparo is not None:
        return "disparada"
    return "completo" if por_que_no == "completo" else f"revisada:{por_que_no}"


async def ultima_revision(base, *, ahora: datetime | None = None) -> dict[str, Any] | None:
    """La revisión de hoy, para el inicio del panel. `None` si hoy no hubo."""
    momento = ahora or datetime.now(UTC)
    evento = await base["auditoria"].find_one(
        {"que": str(auditoria.Que.REPESCA_REVISADA), "cuando": {"$gte": inicio_del_dia(momento)}},
        sort=[("cuando", -1)],
    )
    if evento is None:
        return None
    detalle = evento.get("detalle") or {}
    return {
        "cuando": evento["cuando"],
        "corrida_id": str(evento["corrida_id"]) if evento.get("corrida_id") else None,
        "sin_disparo": detalle.get("sin_disparo"),
        "maquinas": list(detalle.get("resumen") or []),
    }
