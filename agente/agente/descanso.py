"""El descanso (D64): de noche y los domingos, el agente suspende la computadora.

El backend dice en cada latido si es la hora del descanso y hasta cuándo dura.
Con eso, y sin un job en curso, el agente:

1. deja `~/.centonara/estado/descanso.json` — el guardián del actualizador
   (D62) no revive a un agente que está quieto a propósito;
2. suspende la computadora.

**No programa ningún despertar**: a la mañana la despierta el vendedor cuando
llega al negocio (decisión del dueño, 02/10/2026). Si no la despierta, D59 la
deja afuera de la corrida y el panel avisa antes.

Una vez por descanso: si alguien despierta la máquina a mano a las 3 de la
mañana, el agente no la vuelve a dormir.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agente.logging import obtener_logger
from agente.reinicio import carpeta_estado

log = obtener_logger(__name__)

ARCHIVO = "descanso.json"
INTERVALO = 30.0

Correr = Callable[[list[str], float], tuple[int, str]]


def _correr_real(comando: list[str], timeout: float) -> tuple[int, str]:
    try:
        hecho = subprocess.run(
            comando, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 127, str(error)
    return hecho.returncode, ((hecho.stdout or "") + (hecho.stderr or "")).strip()


class Descanso:
    def __init__(
        self,
        *,
        plataforma: str | None = None,
        casa: Path | None = None,
        correr: Correr | None = None,
        ahora: Callable[[], datetime] | None = None,
    ) -> None:
        self._plataforma = plataforma or sys.platform
        self._casa = casa or Path.home()
        self._correr = correr or _correr_real
        self._ahora = ahora or (lambda: datetime.now(UTC))
        self._hasta: datetime | None = None
        self._suspender = True
        #  Lo que viaja en el latido: "suspende" o "descansa_sin_suspender".
        #  `None` hasta que haya algo.
        self.estado: str | None = None

    # -- lo que manda el backend ----------------------------------------------

    def recibir(self, horarios: dict[str, Any] | None) -> None:
        if not isinstance(horarios, dict):
            return
        crudo = horarios.get("descanso_hasta")
        try:
            hasta = datetime.fromisoformat(crudo) if isinstance(crudo, str) and crudo else None
        except ValueError:
            hasta = None
        if hasta is not None and hasta.tzinfo is None:
            hasta = hasta.replace(tzinfo=UTC)
        self._hasta = hasta
        self._suspender = bool(horarios.get("suspender", True))

    # -- la vuelta --------------------------------------------------------------

    async def vigilar(
        self,
        ocupado: Callable[[], bool],
        *,
        parar: asyncio.Event,
        dormir: Callable[[float], Any] | None = None,
        vueltas: int | None = None,
    ) -> None:
        """Cada 30 s, en paralelo al bucle. Los comandos del sistema van a un hilo."""
        esperar = dormir or asyncio.sleep
        dadas = 0
        while not parar.is_set():
            try:
                await asyncio.to_thread(self.revisar, ocupado())
            except Exception as error:  # el descanso nunca puede tumbar al agente
                log.warning("descanso_fallo", error=str(error)[:200])
            dadas += 1
            if vueltas is not None and dadas >= vueltas:
                return
            await esperar(INTERVALO)

    def revisar(self, ocupado: bool) -> str | None:
        """Una vuelta. Devuelve qué hizo, para los tests y el log."""
        ahora = self._ahora()
        if self._hasta is None or ahora >= self._hasta:
            self._olvidar()
            return None

        marca = self._leer()
        if marca.get("hasta") != self._hasta.isoformat():
            marca = {"hasta": self._hasta.isoformat(), "suspendida": False}
            self._guardar(marca)
        if ocupado or marca.get("suspendida"):
            return None

        #  Una vez por descanso, se suspenda o no: no se reintenta cada 30 s.
        marca["suspendida"] = True
        self._guardar(marca)

        if not self._suspender:
            self.estado = "descansa_sin_suspender"
            return self.estado

        self.estado = "suspende"
        log.info("descanso_suspende", hasta=self._hasta.isoformat())
        self._suspender_ahora()
        return self.estado

    def _suspender_ahora(self) -> None:
        if self._plataforma == "win32":
            self._correr(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], 60)
        elif self._plataforma == "darwin":
            self._correr(["pmset", "sleepnow"], 30)

    # -- disco ------------------------------------------------------------------

    def _olvidar(self) -> None:
        with contextlib.suppress(OSError):
            (carpeta_estado(self._casa) / ARCHIVO).unlink(missing_ok=True)

    def _leer(self) -> dict[str, Any]:
        try:
            return json.loads((carpeta_estado(self._casa) / ARCHIVO).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _guardar(self, datos: dict[str, Any]) -> None:
        try:
            (carpeta_estado(self._casa) / ARCHIVO).write_text(json.dumps(datos), encoding="utf-8")
        except OSError as error:
            log.warning("descanso_no_guardado", error=str(error)[:200])
