"""La corrida programada (D51): que arranque sola, a la hora que fija el panel.

Hasta acá el sistema no se despertaba solo: si nadie apretaba el botón, no
pasaba nada (D4). El dueño pidió que la corrida arranque todos los días a las
17:00, hora argentina, y D4 ya preveía cómo: un temporizador configurable,
apagado por defecto.

No hay cron. `mantenimiento_periodico` (`main.py`) ya da una vuelta cada cinco
minutos, y en cada vuelta esto pregunta si es la hora. Tres cosas hacen que
"cada cinco minutos" no se convierta en "cinco veces":

- **Una marca por día**, tomada con un `find_one_and_update` atómico en la
  colección `programacion`: aunque dos procesos preguntaran a la vez, la marca
  se la lleva uno solo.
- **Una ventana de gracia** de `HORAS_DE_GRACIA`: si el backend estaba caído o
  se estaba desplegando a las 17:00, la corrida sale cuando vuelve — pero a las
  23:00 ya no arranca nada. Una corrida de la noche no es lo que se pidió.
- **Saltear también consume el día.** Con pausa global o una corrida todavía en
  curso no se dispara, y queda en la auditoría como
  `CORRIDA_PROGRAMADA_SALTEADA` con el motivo. Si no consumiera el día, se
  volvería a intentar cada cinco minutos hasta que venza la gracia, y eso es
  lo mismo que disparar en cuanto termine la corrida anterior — que nadie pidió.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core import auditoria, configuracion, corridas
from app.core.huso import HUSO_COMERCIAL
from app.logging import obtener_logger

log = obtener_logger(__name__)

# Cuánto después de la hora todavía tiene sentido disparar. Cubre un deploy o
# una caída del backend a la hora justa; no cubre "a la noche".
HORAS_DE_GRACIA = 2

ID = "unica"


def _minutos(hhmm: str) -> int:
    horas, _, minutos = str(hhmm).partition(":")
    return int(horas) * 60 + int(minutos)


def _toca(programa: dict[str, Any], ahora: datetime) -> bool:
    """¿Es un momento en el que corresponde disparar? Puro: sólo mira el reloj."""
    if not programa.get("activa"):
        return False
    local = ahora.astimezone(HUSO_COMERCIAL)
    if local.isoweekday() not in (programa.get("dias") or []):
        return False
    minuto = local.hour * 60 + local.minute
    objetivo = _minutos(programa.get("hora") or "17:00")
    return objetivo <= minuto < objetivo + HORAS_DE_GRACIA * 60


def proxima(programa: dict[str, Any], *, ahora: datetime) -> datetime | None:
    """Cuándo es la próxima corrida programada (UTC), o `None` si está apagada.

    Para el panel: "próxima corrida: hoy 17:00". Mira hasta siete días adelante,
    que es lo más que puede tardar un día habilitado en volver a aparecer.
    """
    if not programa.get("activa") or not (programa.get("dias") or []):
        return None
    local = ahora.astimezone(HUSO_COMERCIAL)
    objetivo = _minutos(programa.get("hora") or "17:00")
    for dias_adelante in range(8):
        candidato = (local + timedelta(days=dias_adelante)).replace(
            hour=objetivo // 60, minute=objetivo % 60, second=0, microsecond=0
        )
        if candidato.isoweekday() not in programa["dias"]:
            continue
        if candidato > local:
            return candidato.astimezone(UTC)
    return None


async def _tomar_el_dia(base, dia: str) -> bool:
    """La marca de "hoy ya se disparó". `True` sólo para quien la toma primero."""
    tomada = await base["programacion"].find_one_and_update(
        {"_id": ID, "ultimo_dia": {"$ne": dia}},
        {"$set": {"ultimo_dia": dia, "tomado_en": datetime.now(UTC)}},
    )
    if tomada is not None:
        return True
    # No matcheó: o ya es de hoy, o el documento no existe todavía.
    try:
        await base["programacion"].insert_one({"_id": ID, "ultimo_dia": dia})
    except Exception:  # DuplicateKeyError: otro llegó primero, o ya era de hoy
        return False
    return True


async def _saltear(base, *, motivo: str, ahora: datetime) -> str:
    await auditoria.registrar(
        base,
        que=auditoria.Que.CORRIDA_PROGRAMADA_SALTEADA,
        quien="programacion",
        detalle={"motivo": motivo},
        ahora=ahora,
    )
    log.warning("corrida_programada_salteada", motivo=motivo)
    return f"salteada:{motivo}"


async def revisar(base, *, ahora: datetime | None = None) -> str | None:
    """Dispara la corrida del día si es la hora. Devuelve qué hizo, o `None`.

    `"disparada"` cuando salió; `"salteada:<motivo>"` cuando era la hora y no
    se pudo; `None` cuando no tocaba (apagada, otro día, otra hora, o ya se
    disparó hoy). Nunca levanta por una causa de negocio: eso lo dice el
    resultado y la auditoría, no una excepción en el loop de mantenimiento.
    """
    momento = ahora or datetime.now(UTC)
    config = await configuracion.obtener(base)
    programa = config.get("programacion") or {}
    if not _toca(programa, momento):
        return None

    dia = momento.astimezone(HUSO_COMERCIAL).strftime("%Y-%m-%d")
    if not await _tomar_el_dia(base, dia):
        return None

    if bool(config.get("pausa_global")):
        return await _saltear(base, motivo="pausa_global", ahora=momento)
    if await corridas.en_curso(base) is not None:
        return await _saltear(base, motivo="corrida_en_curso", ahora=momento)

    try:
        disparo = await corridas.disparar(
            base, quien="programacion", tipo=corridas.TipoCorrida.GENERACION, ahora=momento
        )
    except corridas.NoHayMaquinas:
        return await _saltear(base, motivo="sin_maquinas", ahora=momento)
    except corridas.Pausado:
        return await _saltear(base, motivo="pausa_global", ahora=momento)

    log.info(
        "corrida_programada_disparada",
        corrida=str(disparo.corrida_id),
        maquinas=len(disparo.maquinas),
        hora=programa.get("hora"),
    )
    return "disparada"
