"""La hora del negocio: Argentina.

Todo el sistema trabaja en UTC —las marcas de tiempo, la cola, los
vencimientos— y está bien que así sea. Esto es la excepción, y es una sola:
lo que describe la vida de una persona (el horario de envío, el "hoy" de un
tope diario, la hora a la que arranca la corrida) se mide en la hora en que
esa persona vive.

Vive en un módulo propio y chico porque lo necesitan `guardrails` (la ventana
horaria) y `mensajes` (los topes diarios, D51), y `guardrails` importa
`mensajes`: si la constante viviera en cualquiera de los dos, el otro
importaría en círculo.

Sólo Argentina, igual que `contactos.py`: el día que haga falta otro país, esto
pasa a ser un campo de la configuración y no una constante.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

HUSO_COMERCIAL = ZoneInfo("America/Argentina/Buenos_Aires")


def inicio_del_dia(momento: datetime) -> datetime:
    """La medianoche argentina del día en que cae `momento`, como instante UTC.

    Es lo que decide qué cuenta como "hoy" para un tope diario (D51). Antes se
    cortaba a medianoche UTC —las 21:00 en Argentina— y daba igual, porque
    ninguna corrida pasaba de las 19:00. Con la corrida programada de las 17:00
    ya no da igual: una que dura tres horas cruzaría la medianoche UTC en el
    medio y el contador se reiniciaría a mitad de corrida.
    """
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    local = momento.astimezone(HUSO_COMERCIAL)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
