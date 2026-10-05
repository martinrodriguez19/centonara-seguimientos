"""Sin tokens de Claude: la máquina se pausa sola hasta que vuelvan (D60).

El agente reconoce el aviso de cuota agotada de Claude Code y reporta el job con
`LIMITE_USO`, a veces con la hora a la que la cuota vuelve. Acá se decide qué
hace el sistema con eso: pausar esa máquina, cerrar lo que le quedaba vivo para
que la corrida termine con las demás, y dejarlo anotado.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core import auditoria, configuracion, corridas, vendedores
from app.logging import obtener_logger

log = obtener_logger(__name__)

# Margen sobre la hora que dice Claude: la cuota vuelve "a las 21", no a las
# 21:00:00 en punto de nuestro reloj.
MARGEN_REINICIO = timedelta(minutes=10)

# Más allá de esto, la hora que vino se considera mal leída. El límite semanal
# de Claude es lo más largo que existe.
REINICIO_MAXIMO = timedelta(days=8)


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
    """La máquina se quedó sin cuota: pausarla y cerrar lo que tenía vivo.

    Devuelve hasta cuándo quedó pausada. Los jobs vivos de la máquina en
    cualquier corrida se cierran como `LIMITE_USO`: durante la pausa no los va
    a tomar, y dejarlos vivos tendría la corrida abierta hasta el techo (D59).
    """
    from app.core.cola import Codigo

    momento = ahora or datetime.now(UTC)
    config = await configuracion.obtener(base)
    hasta = hasta_cuando(detalle, config, momento)
    await vendedores.pausar_por_cuota(base, maquina, hasta=hasta)

    vivas = await base["jobs"].distinct(
        "corrida_id", {"maquina": maquina, "estado": {"$in": ["pendiente", "tomado"]}}
    )
    for corrida in await base["corridas"].find({"_id": {"$in": vivas}}).to_list(None):
        await corridas.cortar_maquina(
            base,
            corrida,
            maquina=maquina,
            codigo=Codigo.LIMITE_USO,
            motivo="la máquina se quedó sin cuota de Claude",
            ahora=momento,
        )

    await auditoria.registrar(
        base,
        que=auditoria.Que.CUOTA_AGOTADA,
        quien=maquina,
        detalle={
            "maquina": maquina,
            "hasta": hasta.isoformat(),
            "dijo_cuando": bool(detalle.get("reinicia_en")),
        },
        ahora=momento,
    )
    log.warning("maquina_sin_cuota", maquina=maquina, hasta=hasta.isoformat())
    return hasta
