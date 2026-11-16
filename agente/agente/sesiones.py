"""Las cuatro sesiones de esta máquina, como las ve el agente (D69).

    whatsapp          WhatsApp Web en el Chrome del vendedor (la ruta de producción)
    claude_extension  la extensión Claude in Chrome, en ese mismo perfil
    claude_cli        Claude Code, que corre cada job
    whatsapp_motor    el WhatsApp del navegador dedicado (D24)

Cada una es `ok`, `caida` o `desconocido`, con la **fuente** que lo dijo:

- `job`: un job que la usó (lo que pasó de verdad);
- `sonda`: la verificación corta por la extensión (`--sonda`, o el botón);
- `vigia`: la revisión del navegador dedicado (`vigia_sesion.py`);
- `token`: llegó un token de Claude nuevo y lo que dijo el último 401 ya no vale.

**No se lee el disco del perfil.** Se probó (16/11, D69): el WhatsApp Web
actual guarda su `localStorage` con los nombres de las claves cifrados, así
que no hay forma estable de saber desde el disco si la sesión vive. Lo que
avisa antes de la corrida es la revisión diaria con la sonda (`reconexion.py`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agente.logging import obtener_logger

log = obtener_logger(__name__)

OK = "ok"
CAIDA = "caida"
DESCONOCIDO = "desconocido"

NOMBRES = ("whatsapp", "claude_extension", "claude_cli", "whatsapp_motor")


@dataclass
class Observacion:
    estado: str
    fuente: str
    detalle: str = ""
    cuando: float = field(default_factory=time.monotonic)

    def a_dict(self) -> dict[str, str]:
        return {"estado": self.estado, "fuente": self.fuente, "detalle": self.detalle[:300]}


class Sesiones:
    """Lo que el agente sabe de cada sesión. Lo manda el latido."""

    def __init__(self, reloj=time.monotonic) -> None:
        self._reloj = reloj
        self._estado: dict[str, Observacion] = {}
        #  Quién quiere enterarse de una caída (la apertura automática, D70).
        self._al_caer: list = []

    def al_caer(self, quien) -> None:
        self._al_caer.append(quien)

    def observar(self, nombre: str, estado: str, fuente: str, detalle: str = "") -> None:
        if nombre not in NOMBRES or estado not in (OK, CAIDA, DESCONOCIDO):
            return
        previa = self._estado.get(nombre)
        self._estado[nombre] = Observacion(estado, fuente, detalle, self._reloj())
        if previa is None or previa.estado != estado:
            log.info("sesion_observada", sesion=nombre, estado=estado, fuente=fuente)
            if estado == CAIDA:
                for quien in self._al_caer:
                    try:
                        quien(nombre, fuente)
                    except Exception as error:  # avisar nunca puede tumbar al agente
                        log.warning("aviso_de_caida_fallo", error=str(error)[:200])

    def estado(self, nombre: str) -> str:
        observacion = self._estado.get(nombre)
        return observacion.estado if observacion else DESCONOCIDO

    def observacion(self, nombre: str) -> Observacion | None:
        return self._estado.get(nombre)

    def confirmada_hace(self, nombre: str, fuentes=("job", "sonda")) -> float | None:
        """Segundos desde la última vez que un job o la sonda dijeron algo de ésta."""
        observacion = self._estado.get(nombre)
        if observacion is None or observacion.fuente not in fuentes:
            return None
        return self._reloj() - observacion.cuando

    def a_dict(self) -> dict[str, dict[str, str]]:
        return {nombre: o.a_dict() for nombre, o in self._estado.items()}

    # -- lo que dicen los jobs ------------------------------------------------

    def resultado_de_job(self, tipo: str, resultado: dict[str, Any]) -> None:
        """Lo que un job terminado dice de las sesiones que usó."""
        codigo = resultado.get("codigo")
        ok = bool(resultado.get("ok"))
        motivo = str((resultado.get("detalle") or {}).get("motivo") or "")[:200]

        if codigo == "CLAUDE_SIN_SESION":
            self.observar("claude_cli", CAIDA, "job", motivo)
            return
        if codigo == "LIMITE_USO":
            return  # sin cuota no dice nada de las sesiones

        usa_claude = tipo in ("LISTAR", "BORRADORES", "REDACTAR")
        if usa_claude and (ok or codigo in ("SESION_CAIDA", "NAVEGADOR_AUSENTE", "TEXTO_ENVIADO")):
            #  Claude Code contestó algo con sentido: tiene sesión.
            self.observar("claude_cli", OK, "job")

        if tipo in ("LISTAR", "BORRADORES"):
            if ok:
                self.observar("whatsapp", OK, "job")
                self.observar("claude_extension", OK, "job")
            elif codigo == "SESION_CAIDA":
                self.observar("whatsapp", CAIDA, "job", motivo)
                #  Llegó a la página: la extensión anda.
                self.observar("claude_extension", OK, "job")
            elif codigo == "NAVEGADOR_AUSENTE":
                #  El agente ya abrió Chrome en el perfil bueno antes de la
                #  tanda (D66.3): si la extensión no aparece, casi siempre es
                #  que se le cerró la sesión.
                self.observar("claude_extension", CAIDA, "job", motivo)
        elif tipo in ("ENVIAR", "RESOLVER"):
            if ok:
                self.observar("whatsapp_motor", OK, "job")
            elif codigo == "SESION_CAIDA":
                self.observar("whatsapp_motor", CAIDA, "job", motivo)

    def resultado_de_sonda(self, resultado) -> None:
        """Lo que dijo la sonda (`agente.sonda.Resultado`)."""
        if resultado.ok:
            for nombre in ("whatsapp", "claude_extension", "claude_cli"):
                self.observar(nombre, OK, "sonda")
            return
        motivo = resultado.motivo
        if motivo == "sesion_no_iniciada":
            self.observar("whatsapp", CAIDA, "sonda", "WhatsApp Web pide el código QR")
            self.observar("claude_extension", OK, "sonda")
            self.observar("claude_cli", OK, "sonda")
        elif motivo in ("browser_no_disponible", "NAVEGADOR_AUSENTE"):
            self.observar("claude_extension", CAIDA, "sonda", resultado.detalle)
            self.observar("claude_cli", OK, "sonda")
        elif motivo == "CLAUDE_SIN_SESION":
            self.observar("claude_cli", CAIDA, "sonda", resultado.detalle)
