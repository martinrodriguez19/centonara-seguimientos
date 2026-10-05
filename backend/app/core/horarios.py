"""Los horarios de cada máquina: cuándo se actualiza y cuándo se revisa (D63).

El actualizador de cada máquina se despertaba al iniciar sesión y cada hora.
Con la actualización programada prendida en el panel:

- el backend sólo entrega la versión nueva dentro de la ventana del día
  (`[hora, hora + 2 h)`) o mientras dure un "Actualizar ahora";
- y le manda a cada agente los disparadores que su actualizador tiene que
  tener: la hora de actualizar, y 15 minutos antes de la corrida y de la
  repesca, que es cuando el actualizador revisa que el agente esté vivo (D62).

Todo en hora argentina, como lo escribe el dueño en el panel. Puro: sólo mira
la configuración y el reloj.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.huso import HUSO_COMERCIAL

# Cuánto dura la ventana de actualización. Igual que la gracia de la corrida
# programada: cubre una PC que se prende un rato tarde, no "a la noche".
HORAS_VENTANA = 2

# Cuánto antes de la corrida y de la repesca se revisa que el agente esté vivo.
MINUTOS_ANTES = 15

# Cuánto queda abierto un "Actualizar ahora": una vuelta del actualizador entra
# seguro, y no queda abierto hasta mañana.
MINUTOS_ACTUALIZAR_YA = 70

TODOS_LOS_DIAS = [1, 2, 3, 4, 5, 6, 7]


def _minutos(hhmm: str) -> int:
    horas, _, minutos = str(hhmm).partition(":")
    return int(horas) * 60 + int(minutos)


def _hhmm(minutos: int) -> str:
    minutos %= 24 * 60
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def programada(config: dict[str, Any]) -> bool:
    """¿La actualización programada está prendida?"""
    return bool((config.get("actualizacion") or {}).get("activa"))


def actualizar_ya(config: dict[str, Any], ahora: datetime) -> bool:
    """¿Hay un "Actualizar ahora" vigente?"""
    hasta = config.get("actualizar_ya_hasta")
    if hasta is None:
        return False
    if hasta.tzinfo is None:
        hasta = hasta.replace(tzinfo=UTC)
    return hasta > ahora


def toca_actualizar(config: dict[str, Any], ahora: datetime) -> bool:
    """¿Se le entrega la versión nueva a una máquina que pregunta ahora?

    Con la actualización programada apagada, siempre: es lo de antes de D63.
    """
    if en_descanso(config, ahora):
        return False  # D64: de noche no se actualiza nadie
    if not programada(config) or actualizar_ya(config, ahora):
        return True
    inicio, fin = ultima_ventana(config, ahora)
    return inicio <= ahora < fin


def ultima_ventana(config: dict[str, Any], ahora: datetime) -> tuple[datetime, datetime]:
    """La ventana de actualización más reciente que ya empezó (UTC).

    Hoy si ya pasó la hora; si no, la de ayer.
    """
    hora = _minutos((config.get("actualizacion") or {}).get("hora") or "15:00")
    local = ahora.astimezone(HUSO_COMERCIAL)
    inicio = local.replace(hour=hora // 60, minute=hora % 60, second=0, microsecond=0)
    if inicio > local:
        inicio -= timedelta(days=1)
    inicio_utc = inicio.astimezone(UTC)
    return inicio_utc, inicio_utc + timedelta(hours=HORAS_VENTANA)


def para_agente(config: dict[str, Any], ahora: datetime) -> dict[str, Any]:
    """Lo que el agente necesita saber de sus horarios. Va en el registro y el latido.

    `disparadores` vacío significa "dejá el actualizador como lo dejó el
    instalador" (cada hora): es lo que pasa con la actualización programada
    apagada. Cada disparador es una hora argentina y los días en que corre.
    """
    disparadores: list[dict[str, Any]] = []
    if programada(config):
        hora = (config.get("actualizacion") or {}).get("hora") or "15:00"
        disparadores.append({"hora": hora, "dias": TODOS_LOS_DIAS, "para": "actualizar"})
        for clave, para in (("programacion", "corrida"), ("repesca", "repesca")):
            programa = config.get(clave) or {}
            if programa.get("activa") and programa.get("dias"):
                disparadores.append(
                    {
                        "hora": _hhmm(_minutos(programa.get("hora") or "17:00") - MINUTOS_ANTES),
                        "dias": sorted(programa["dias"]),
                        "para": f"revisar_antes_de_{para}",
                    }
                )
    hasta = descanso_hasta(config, ahora)
    return {
        "disparadores": disparadores,
        "actualizar_ya": actualizar_ya(config, ahora),
        # D64: el descanso en curso. A la mañana la despierta el vendedor.
        "descanso_hasta": hasta.isoformat() if hasta else None,
        "suspender": bool(_descanso(config).get("suspender", True)),
    }


# ---------------------------------------------------------------------------
# El descanso (D64)
# ---------------------------------------------------------------------------


def _descanso(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("descanso") or {}


def en_descanso(config: dict[str, Any], ahora: datetime) -> bool:
    """¿Las máquinas tienen que estar descansando ahora? Puro.

    Las noches de `dias` de `desde` a `hasta` (si `desde` es mayor que `hasta`,
    la noche cruza la medianoche y termina al día siguiente), y los días de
    `dia_libre` enteros.
    """
    descanso = _descanso(config)
    if not descanso.get("activa"):
        return False
    local = ahora.astimezone(HUSO_COMERCIAL)
    dia = local.isoweekday()
    if dia in (descanso.get("dia_libre") or []):
        return True
    dias = descanso.get("dias") or []
    minuto = local.hour * 60 + local.minute
    desde = _minutos(descanso.get("desde") or "00:00")
    hasta = _minutos(descanso.get("hasta") or "08:00")
    if desde < hasta:
        return dia in dias and desde <= minuto < hasta
    anterior = (dia - 2) % 7 + 1
    return (dia in dias and minuto >= desde) or (anterior in dias and minuto < hasta)


def _fronteras(config: dict[str, Any], ahora: datetime, dias: range) -> list[datetime]:
    """Los únicos instantes en que un descanso puede terminar: la hora de fin y
    la medianoche siguiente a un día libre. Ordenados, en UTC."""
    hasta = _minutos(_descanso(config).get("hasta") or "08:00")
    local = ahora.astimezone(HUSO_COMERCIAL).replace(second=0, microsecond=0)
    candidatos = []
    for desplazamiento in dias:
        dia = local + timedelta(days=desplazamiento)
        candidatos.append(dia.replace(hour=hasta // 60, minute=hasta % 60))
        candidatos.append(dia.replace(hour=0, minute=0))
    return sorted(c.astimezone(UTC) for c in candidatos)


def descanso_hasta(config: dict[str, Any], ahora: datetime) -> datetime | None:
    """Hasta cuándo dura el descanso en curso (UTC), o `None` si no hay descanso ahora."""
    if not en_descanso(config, ahora):
        return None
    for frontera in _fronteras(config, ahora, range(0, 9)):
        if frontera > ahora and not en_descanso(config, frontera):
            return frontera
    return None


def ultimo_fin_de_descanso(config: dict[str, Any], ahora: datetime) -> datetime | None:
    """El último momento en que terminó un descanso, hasta `ahora` (UTC)."""
    if not _descanso(config).get("activa") or en_descanso(config, ahora):
        return None
    for frontera in reversed(_fronteras(config, ahora, range(-8, 1))):
        if (
            frontera <= ahora
            and not en_descanso(config, frontera)
            and en_descanso(config, frontera - timedelta(minutes=1))
        ):
            return frontera
    return None


def inicio_del_descanso(config: dict[str, Any], fin: datetime) -> datetime | None:
    """Cuándo empezó el descanso que terminó en `fin` (UTC).

    Un descanso sólo puede empezar a la hora `desde` o a la medianoche de un
    día libre: se busca hacia atrás la última de esas fronteras en que se pasó
    de trabajar a descansar.
    """
    desde = _minutos(_descanso(config).get("desde") or "00:00")
    local = fin.astimezone(HUSO_COMERCIAL).replace(second=0, microsecond=0)
    candidatos = []
    for desplazamiento in range(-9, 1):
        dia = local + timedelta(days=desplazamiento)
        candidatos.append(dia.replace(hour=desde // 60, minute=desde % 60))
        candidatos.append(dia.replace(hour=0, minute=0))
    for candidato in sorted((c.astimezone(UTC) for c in candidatos), reverse=True):
        if (
            candidato < fin
            and en_descanso(config, candidato)
            and not en_descanso(config, candidato - timedelta(minutes=1))
        ):
            return candidato
    return None


def dormida_desde_el_descanso(
    config: dict[str, Any], ultimo_latido: datetime | None, ahora: datetime
) -> bool:
    """¿La máquina se calló durante el último descanso y nadie la despertó todavía?

    Es lo esperado hasta que llega el vendedor (D64): el panel la muestra
    "dormida", no "sin conexión". Una máquina que se calló antes del descanso
    está caída, no dormida.
    """
    if ultimo_latido is None:
        return False
    if ultimo_latido.tzinfo is None:
        ultimo_latido = ultimo_latido.replace(tzinfo=UTC)
    fin = ultimo_fin_de_descanso(config, ahora)
    if fin is None or ultimo_latido >= fin:
        return False
    inicio = inicio_del_descanso(config, fin)
    return inicio is not None and ultimo_latido >= inicio - timedelta(minutes=10)
