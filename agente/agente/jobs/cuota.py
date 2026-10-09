"""Reconocer que Claude Code se quedó sin cuota, y cuándo vuelve (D60).

Claude Code no tiene un código de error para esto: avisa con texto, y el texto
cambia entre versiones y planes. Por eso es una lista de frases, en un solo
lugar, y sólo se mira en los caminos de falla —nunca en una respuesta sana, que
podría hablar de "límites" por cualquier otro motivo.

Lo que se reconoce se reporta como `LIMITE_USO`: el backend pausa la máquina
hasta que la cuota vuelva y no reintenta. Lo que no se reconoce sigue el camino
de siempre (`ERROR_INESPERADO`, tres intentos); el texto queda en el motivo del
job, a la vista en el panel, para sumarlo acá.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# En minúsculas. Lo que Claude Code imprime al quedarse sin cuota en sus
# distintas versiones: "Claude AI usage limit reached|<epoch>", "5-hour limit
# reached ∙ resets 9pm", "You've hit your limit · resets 3pm", "Weekly limit
# reached", "Credit balance is too low", "You've hit your session limit ·
# resets 10:30pm" (D65, mac-lautaro, 03/10).
#
# ⚠️ No está `rate_limit_error` suelto: un 429 de la API puede ser un límite por
# minuto, que pasa solo, y pausar la máquina cuatro horas por eso sería peor
# que reintentar. Un 429 cuenta sólo si dice a qué hora vuelve (`_CON_429`).
FRASES = (
    "usage limit",
    "limit reached",
    "hit your limit",
    "hit your session limit",
    "session limit reached",
    "reached your limit",
    "out of extra usage",
    "credit balance is too low",
)

_CON_429 = re.compile(r'"api_error_status"\s*:\s*429\b')

_EPOCH = re.compile(r"\|(\d{10})\b")
_RESETS = re.compile(
    r"resets?\s+(?:at\s+)?"
    r"(?:(?P<mes>[a-z]{3,9})\.?\s+(?P<dia>\d{1,2}),?\s+(?:at\s+)?)?"
    r"(?P<hora>\d{1,2})(?::(?P<minuto>\d{2}))?\s*(?P<ampm>am|pm)"
    r"(?:\s*\((?P<huso>[^)]+)\))?",
    re.IGNORECASE,
)
_MESES = {
    nombre: numero
    for numero, nombres in enumerate(
        (
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for nombre in nombres
}


def agotada(texto: str) -> bool:
    """¿Este texto es el aviso de cuota agotada de Claude Code?"""
    bajo = texto.lower()
    if any(frase in bajo for frase in FRASES):
        return True
    # D65: el texto cambia antes que el sobre. Un 429 que trae la hora de
    # reinicio es cuota aunque la frase sea nueva; uno por minuto no la trae.
    return bool(_CON_429.search(texto)) and _RESETS.search(texto) is not None


def reinicio(texto: str, *, ahora: datetime | None = None) -> datetime | None:
    """La hora (UTC) a la que vuelve la cuota, si el aviso la dice. `None` si no.

    `ahora` tiene que tener zona: es la referencia para "resets 9pm", que habla
    de la hora local de la máquina —o de la zona entre paréntesis, si viene—.
    """
    momento = ahora or datetime.now(UTC).astimezone()

    epoch = _EPOCH.search(texto)
    if epoch:
        return datetime.fromtimestamp(int(epoch.group(1)), tz=UTC)

    dicho = _RESETS.search(texto)
    if not dicho:
        return None

    hora = int(dicho.group("hora")) % 12 + (12 if dicho.group("ampm").lower() == "pm" else 0)
    minuto = int(dicho.group("minuto") or 0)
    if minuto > 59:
        return None
    local = momento.astimezone(_zona(dicho.group("huso"), momento))

    if dicho.group("mes"):
        mes = _MESES.get(dicho.group("mes").lower())
        if mes is None:
            return None
        try:
            candidato = local.replace(
                month=mes, day=int(dicho.group("dia")), hour=hora, minute=minuto,
                second=0, microsecond=0,
            )  # fmt: skip
        except ValueError:
            return None
        if candidato < local - timedelta(days=1):
            candidato = candidato.replace(year=candidato.year + 1)
    else:
        candidato = local.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if candidato <= local:
            candidato += timedelta(days=1)
    return candidato.astimezone(UTC)


# Las zonas que se reconocen sin base de husos. En Windows `zoneinfo` no trae
# `tzdata` y no sabe ninguna; éstas son las que pueden aparecer en el parque.
# Argentina no tiene horario de verano: un corrimiento fijo es exacto.
_ARGENTINA = timezone(timedelta(hours=-3))
_CONOCIDAS: dict[str, tzinfo] = {"utc": UTC, "gmt": UTC, "etc/utc": UTC, "z": UTC}


def _zona(nombre: str | None, momento: datetime) -> tzinfo:
    """La zona que nombra el aviso, o la de la máquina si no se la conoce."""
    if nombre:
        limpio = nombre.strip()
        if limpio.lower() in _CONOCIDAS:
            return _CONOCIDAS[limpio.lower()]
        if limpio.startswith(("America/Argentina", "America/Buenos_Aires")):
            return _ARGENTINA
        try:
            return ZoneInfo(limpio)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return momento.tzinfo or UTC
