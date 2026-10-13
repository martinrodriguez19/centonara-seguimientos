"""Sin tokens de Claude: las máquinas se pausan solas hasta que vuelvan (D60, D65).

El agente reconoce el aviso de cuota agotada de Claude Code y reporta el job con
`LIMITE_USO`, a veces con la hora a la que la cuota vuelve. Acá se decide qué
hace el sistema con eso: pausar **todas** las máquinas —comparten una sola
cuenta de Claude (D65)—, cerrar lo que les quedaba vivo para que la corrida
termine, y dejarlo anotado.

Y cuando la pausa vence, `revisar_vuelta` completa el día: una corrida sólo
para las máquinas que no llegaron a su tope, con la lógica de la repesca.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core import auditoria, configuracion, corridas, horarios, programacion
from app.core.huso import HUSO_COMERCIAL
from app.logging import obtener_logger

log = obtener_logger(__name__)

# Margen sobre la hora que dice Claude: la cuota vuelve "a las 21", no a las
# 21:00:00 en punto de nuestro reloj.
MARGEN_REINICIO = timedelta(minutes=10)

# Más allá de esto, la hora que vino se considera mal leída. El límite semanal
# de Claude es lo más largo que existe.
REINICIO_MAXIMO = timedelta(days=8)

# La marca diaria de la corrida que completa el día cuando vuelve la cuota
# (D65.3), en la misma colección que la programada y la repesca. El documento
# guarda además `vuelve_en`: hasta cuándo dura la pausa más larga.
MARCA = "cuota"


def hasta_cuando(detalle: dict[str, Any], config: dict[str, Any], ahora: datetime) -> datetime:
    """Hasta cuándo se pausa la máquina. Puro.

    La hora que mandó el agente, con margen, si es creíble; si no, las
    `horas_pausa_cuota` de la configuración.
    """
    crudo = detalle.get("reinicia_en")
    if isinstance(crudo, str) and crudo:
        try:
            reinicio = datetime.fromisoformat(crudo.replace("Z", "+00:00"))
        except ValueError:
            reinicio = None
        if reinicio is not None:
            if reinicio.tzinfo is None:
                reinicio = reinicio.replace(tzinfo=UTC)
            if ahora < reinicio <= ahora + REINICIO_MAXIMO:
                return reinicio + MARGEN_REINICIO
    horas = int(config.get("horas_pausa_cuota") or 4)
    return ahora + timedelta(hours=horas)


async def registrar(
    base, *, maquina: str, detalle: dict[str, Any], ahora: datetime | None = None
) -> datetime:
    """Una máquina se quedó sin cuota: pausarlas a todas y cerrar lo que tenían vivo.

    Devuelve hasta cuándo quedaron pausadas. Todas, y no sólo la que avisó
    (D65.2): la cuenta de Claude es una, y la segunda máquina se enteraría
    pagando una llamada fallida. Una pausa por cuota más larga que ya tuviera
    alguna no se acorta.

    Los jobs vivos de las pausadas, en cualquier corrida, se cierran como
    `LIMITE_USO`: durante la pausa no los van a tomar, y dejarlos vivos tendría
    la corrida abierta hasta el techo (D59).
    """
    from app.core.cola import Codigo

    momento = ahora or datetime.now(UTC)
    config = await configuracion.obtener(base)
    hasta = hasta_cuando(detalle, config, momento)

    activas = [
        v["maquina"]
        for v in await base["vendedores"].find({"activo": True}, {"maquina": 1}).to_list(None)
    ]
    pausadas = sorted({maquina, *activas})
    await base["vendedores"].update_many(
        {
            "maquina": {"$in": pausadas},
            "$or": [{"pausa_cuota_hasta": None}, {"pausa_cuota_hasta": {"$lt": hasta}}],
        },
        {"$set": {"pausa_cuota_hasta": hasta}},
    )
    #  Para `revisar_vuelta`: cuándo termina la pausa más larga. `$max` porque
    #  dos avisos seguidos pueden traer horas distintas.
    await base["programacion"].update_one(
        {"_id": MARCA}, {"$max": {"vuelve_en": hasta}}, upsert=True
    )

    vivas = await base["jobs"].distinct(
        "corrida_id",
        {"maquina": {"$in": pausadas}, "estado": {"$in": ["pendiente", "tomado"]}},
    )
    for corrida in await base["corridas"].find({"_id": {"$in": vivas}}).to_list(None):
        await corridas.cortar_maquinas(
            base,
            corrida,
            maquinas=pausadas,
            codigo=Codigo.LIMITE_USO,
            motivo="la cuenta de Claude se quedó sin cuota",
            ahora=momento,
        )

    await auditoria.registrar(
        base,
        que=auditoria.Que.CUOTA_AGOTADA,
        quien=maquina,
        detalle={
            "maquina": maquina,
            "pausadas": pausadas,
            "hasta": hasta.isoformat(),
            "dijo_cuando": bool(detalle.get("reinicia_en")),
        },
        ahora=momento,
    )
    log.warning("cuota_agotada", aviso=maquina, pausadas=pausadas, hasta=hasta.isoformat())
    return hasta


async def revisar_vuelta(base, *, ahora: datetime | None = None) -> str | None:
    """Volvió la cuota: completar el día de las que no llegaron (D65.3).

    La llama el mantenimiento cada cinco minutos. Devuelve `None` mientras no
    hay nada que hacer —sin pausa registrada, la pausa no venció, o hay una
    corrida en curso y se la espera—; si no, lo mismo que la repesca:
    `"disparada"`, `"completo"`, `"revisada:<motivo>"` o `"salteada:<motivo>"`.
    """
    from app.core import repesca

    momento = ahora or datetime.now(UTC)
    marca = await base["programacion"].find_one({"_id": MARCA})
    vuelve = (marca or {}).get("vuelve_en")
    if vuelve is None:
        return None
    if vuelve.tzinfo is None:
        vuelve = vuelve.replace(tzinfo=UTC)
    if vuelve > momento:
        return None

    dia = vuelve.astimezone(HUSO_COMERCIAL).strftime("%Y-%m-%d")
    if (marca or {}).get("ultimo_dia") == dia:
        return None  # ya se atendió hoy

    config = await configuracion.obtener(base)
    #  La cuota volvió de noche, un domingo, o ayer con el backend caído: el
    #  día ya terminó. Se consume la marca para no preguntar más.
    hoy = momento.astimezone(HUSO_COMERCIAL).strftime("%Y-%m-%d")
    descanso = horarios.en_descanso(config, vuelve) or horarios.en_descanso(config, momento)
    if descanso or dia != hoy:
        if not await programacion._tomar_el_dia(base, dia, marca=MARCA):
            return None
        motivo = "descanso" if descanso else "dia_terminado"
        return await programacion._saltear(base, motivo=motivo, ahora=momento, quien=MARCA)

    if await corridas.en_curso(base) is not None:
        if momento - vuelve < timedelta(hours=programacion.HORAS_DE_GRACIA):
            return None  # se espera: en cinco minutos vuelve a preguntar
        if not await programacion._tomar_el_dia(base, dia, marca=MARCA):
            return None
        return await programacion._saltear(
            base, motivo="corrida_en_curso", ahora=momento, quien=MARCA
        )

    if not await programacion._tomar_el_dia(base, dia, marca=MARCA):
        return None
    return await repesca.completar(
        base, config=config, quien=MARCA, que=auditoria.Que.CUOTA_RETOMADA, ahora=momento
    )
