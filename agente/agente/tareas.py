"""Los horarios del panel, copiados a la tarea del actualizador de esta máquina (D63).

El instalador deja al actualizador despertándose al iniciar sesión y cada hora.
Con la actualización programada prendida en el panel, el backend manda en cada
latido los disparadores que tiene que tener —la hora de actualizar, y 15
minutos antes de la corrida y de la repesca—, y esto los aplica:

- **Windows**: `Set-ScheduledTask` sobre "Centonara Actualizador". La tarea se
  registró como el usuario con `-RunLevel Limited`, así que el mismo usuario la
  puede cambiar sin administrador.
- **Mac**: reescribe el `StartCalendarInterval` del plist del actualizador y
  recarga *ese* servicio con `launchctl`. Es un LaunchAgent del usuario: no
  hace falta `sudo`, y el agente es otro servicio, así que no se mata solo.

Nunca deja la máquina peor: si algo falla, la tarea queda como estaba (cada
hora, que anda) y el motivo viaja en el latido para que el panel lo muestre.
Nada de esto pide tocar la computadora.
"""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agente.logging import obtener_logger

log = obtener_logger(__name__)

TAREA_ACTUALIZADOR = "Centonara Actualizador"
ETIQUETA_ACTUALIZADOR = "com.centonara.actualizador"

# Las horas del panel son argentinas. Argentina no tiene horario de verano:
# un corrimiento fijo alcanza, y no depende de que Windows tenga `tzdata`.
ARGENTINA = timezone(timedelta(hours=-3))

_DIAS_WINDOWS = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}

Correr = Callable[[list[str]], tuple[int, str]]


def _correr_real(comando: list[str]) -> tuple[int, str]:
    try:
        hecho = subprocess.run(comando, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return 127, str(error)
    return hecho.returncode, (hecho.stderr or hecho.stdout).strip()


def a_hora_local(hhmm: str, dias: list[int], *, zona_local: Any) -> tuple[int, int, list[int]]:
    """Una hora argentina y sus días, en la hora de esta máquina. Puro.

    Si el corrimiento cruza la medianoche, los días se corren con ella.
    """
    horas, _, minutos = hhmm.partition(":")
    referencia = datetime(2026, 1, 5, int(horas), int(minutos), tzinfo=ARGENTINA)  # un lunes
    local = referencia.astimezone(zona_local)
    corrimiento = (local.date() - referencia.date()).days
    corridos = sorted({((d - 1 + corrimiento) % 7) + 1 for d in dias})
    return local.hour, local.minute, corridos


class Reprogramador:
    """Mantiene la tarea del actualizador al día con los horarios del panel."""

    def __init__(
        self,
        *,
        plataforma: str | None = None,
        casa: Path | None = None,
        correr: Correr | None = None,
        zona_local: Any = None,
    ) -> None:
        self._plataforma = plataforma or sys.platform
        self._casa = casa or Path.home()
        self._correr = correr or _correr_real
        self._zona = zona_local or datetime.now().astimezone().tzinfo
        self._aplicada: str | None = None
        self._ya_pedido = False
        #  Lo que viaja en el latido. `None` hasta que el backend mande
        #  horarios: un backend viejo no conoce el campo.
        self.estado: str | None = None

    # -- lo que llama el agente ---------------------------------------------

    def recibir(self, horarios: dict[str, Any] | None) -> None:
        """Lo que mandó el backend en el registro o en un latido. Nunca levanta."""
        if not isinstance(horarios, dict):
            return
        try:
            self._aplicar(list(horarios.get("disparadores") or []))
        except Exception as error:  # un horario nunca puede tumbar al agente
            self.estado = f"falla: {str(error)[:180]}"
            log.warning("horarios_no_aplicados", error=str(error)[:200])
        #  Aparte: que no se pueda reprogramar la tarea no impide un
        #  "Actualizar ahora", que es justo para arreglar algo.
        try:
            self._actualizar_ya(bool(horarios.get("actualizar_ya")))
        except Exception as error:
            log.warning("actualizar_ya_fallo", error=str(error)[:200])

    # -- aplicar --------------------------------------------------------------

    def _aplicar(self, disparadores: list[dict[str, Any]]) -> None:
        #  Una vez por arranque del agente y cada vez que cambien. No se guarda
        #  en disco a propósito: un instalador corrido de nuevo deja la tarea
        #  cada hora, y un "ya lo apliqué" guardado no lo vería.
        firma = json.dumps(disparadores, sort_keys=True)
        if firma == self._aplicada:
            return
        if self._actualizador_corriendo():
            #  Recargar el servicio a mitad de una actualización la cortaría.
            #  Se reintenta en el próximo latido.
            return

        if self._plataforma == "win32":
            self._windows(disparadores)
        elif self._plataforma == "darwin":
            self._mac(disparadores)
        else:
            self._aplicada = firma
            return
        self.estado = "ok" if disparadores else "cada_hora"
        self._aplicada = firma
        log.info("horarios_aplicados", disparadores=len(disparadores), estado=self.estado)

    def _windows(self, disparadores: list[dict[str, Any]]) -> None:
        lineas = [
            "$ErrorActionPreference = 'Stop'",
            "$t = @(New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME)",
        ]
        if disparadores:
            for d in disparadores:
                hora, minuto, dias = a_hora_local(
                    str(d["hora"]), list(d.get("dias") or []), zona_local=self._zona
                )
                nombres = ",".join(_DIAS_WINDOWS[x] for x in dias) or "Monday"
                lineas.append(
                    f"$t += New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 "
                    f"-DaysOfWeek {nombres} -At '{hora:02d}:{minuto:02d}'"
                )
        else:
            #  Lo que deja el instalador: al iniciar sesión, y cada hora.
            lineas.append(
                "$t[0].Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) "
                "-RepetitionInterval (New-TimeSpan -Hours 1) "
                "-RepetitionDuration (New-TimeSpan -Days 3650)).Repetition"
            )
        lineas.append(f"Set-ScheduledTask -TaskName '{TAREA_ACTUALIZADOR}' -Trigger $t | Out-Null")
        codigo, salida = self._correr(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "; ".join(lineas)]
        )
        if codigo != 0:
            raise RuntimeError(f"Set-ScheduledTask devolvió {codigo}: {salida[-150:]}")

    def _mac(self, disparadores: list[dict[str, Any]]) -> None:
        plist = self._casa / "Library" / "LaunchAgents" / f"{ETIQUETA_ACTUALIZADOR}.plist"
        try:
            datos = plistlib.loads(plist.read_bytes())
        except (OSError, plistlib.InvalidFileException) as error:
            raise RuntimeError(f"no se pudo leer {plist.name}: {error}") from error

        datos.pop("StartInterval", None)
        datos.pop("StartCalendarInterval", None)
        if disparadores:
            calendario = []
            for d in disparadores:
                hora, minuto, dias = a_hora_local(
                    str(d["hora"]), list(d.get("dias") or []), zona_local=self._zona
                )
                #  launchd cuenta el domingo como 0.
                calendario += [{"Hour": hora, "Minute": minuto, "Weekday": dia % 7} for dia in dias]
            datos["StartCalendarInterval"] = calendario
        else:
            datos["StartInterval"] = 3600

        temporal = plist.with_suffix(".tmp")
        temporal.write_bytes(plistlib.dumps(datos))
        os.replace(temporal, plist)

        dominio = f"gui/{os.getuid() if hasattr(os, 'getuid') else 501}"
        self._correr(["launchctl", "bootout", f"{dominio}/{ETIQUETA_ACTUALIZADOR}"])
        codigo, salida = self._correr(["launchctl", "bootstrap", dominio, str(plist)])
        if codigo != 0:
            raise RuntimeError(f"launchctl bootstrap devolvió {codigo}: {salida[-150:]}")

    # -- "Actualizar ahora" ----------------------------------------------------

    def _actualizar_ya(self, pedido: bool) -> None:
        """Dispara el actualizador una vez por pedido del panel."""
        if not pedido:
            self._ya_pedido = False
            return
        if self._ya_pedido:
            return
        self._ya_pedido = True
        if self._plataforma == "win32":
            self._correr(["schtasks", "/Run", "/TN", TAREA_ACTUALIZADOR])
        elif self._plataforma == "darwin":
            dominio = f"gui/{os.getuid() if hasattr(os, 'getuid') else 501}"
            self._correr(["launchctl", "kickstart", f"{dominio}/{ETIQUETA_ACTUALIZADOR}"])
        log.info("actualizador_disparado_desde_el_panel")

    def _actualizador_corriendo(self) -> bool:
        return (self._casa / ".centonara" / "actualizador.lock").exists()
