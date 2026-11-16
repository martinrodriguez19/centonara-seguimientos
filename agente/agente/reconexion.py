"""Las reconexiones: lo que hace la máquina cuando alguien aprieta el botón (D70).

Las acciones llegan en la respuesta del latido —no por la cola, que contesta
423 justo cuando más hacen falta— y se ejecutan acá, entre latidos:

    abrir_whatsapp  Chrome en el perfil bueno, en web.whatsapp.com, al frente,
                    con un aviso del sistema. El vendedor escanea el QR.
                    Si lo caído es el WhatsApp del navegador dedicado (D24),
                    abre ése, como `--vincular`.
    abrir_claude    Chrome en el inicio de sesión de claude.ai, con un aviso
                    que dice con qué mail entrar.
    verificar       la sonda: una llamada corta por la extensión que confirma
                    WhatsApp, la extensión y Claude Code juntos. Cuesta una
                    llamada, así que sólo con la máquina libre.

Además, solo, sin que nadie apriete nada:

- **la revisión diaria**: una sonda por día, en horario de trabajo y con la
  máquina libre, salvo que un job ya haya confirmado las sesiones en las
  últimas `HORAS_SIN_CONFIRMAR`. Es lo que hace que una sesión caída se vea en
  la página **antes** de la corrida. El disco del perfil no sirve para esto
  (ver `sesiones.py`);
- después de abrir una ventana de reconexión, verifica un par de veces solo,
  para que la página llegue al "¡Listo!" sin que el vendedor apriete nada más;
- si WhatsApp se cae con la máquina despierta, abre la ventana del QR —a lo
  sumo una vez cada `HORAS_ENTRE_APERTURAS`—;
- si un job dijo que WhatsApp o la extensión se cayeron, vuelve a verificar un
  rato después, por si fue un tropiezo (la máquina queda afuera de las corridas
  mientras tanto, D69.4).

Nada de esto puede tumbar al agente: cada paso se protege solo.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from agente import sesiones as sesiones_mod
from agente.logging import obtener_logger

log = obtener_logger(__name__)

URL_WHATSAPP = "https://web.whatsapp.com"
URL_CLAUDE = "https://claude.ai/login"

# La revisión diaria: si nadie confirmó las sesiones en este tiempo, una sonda.
HORAS_SIN_CONFIRMAR = 20
# La primera, un rato después de arrancar: no en el medio del arranque.
MINUTOS_PRIMERA_REVISION = 10

# Después de abrir una ventana de reconexión: cuándo se verifica solo (desde
# que se abrió). El vendedor tarda en tomar el teléfono; el de Claude, en
# conseguir el código.
MINUTOS_VERIFICAR_WHATSAPP = (2, 5)
MINUTOS_VERIFICAR_CLAUDE = (4, 9)

# La apertura automática del QR (D70): a lo sumo una vez cada dos horas.
HORAS_ENTRE_APERTURAS = 2

# La reverificación tras una caída que dijo un job.
MINUTOS_ANTES_DE_REVERIFICAR = 20
HORAS_ENTRE_REVERIFICACIONES = 3

# Cuánto se recuerdan las acciones hechas, para volver a reportarlas si un
# latido se perdió (el backend ignora las que ya marcó).
MINUTOS_RECUERDO = 15

# Cuánto espera `verificar` a que termine un job en curso.
MINUTOS_ESPERA_LIBRE = 10

TICK = 2.0


@dataclass
class _Hecha:
    resultado: str
    cuando: float


@dataclass
class _Pendiente:
    """Una verificación programada: cuándo, y qué sesión tiene que estar ok para no hacerla."""

    cuando: float
    sesion: str


class Reconexion:
    def __init__(
        self,
        estado: sesiones_mod.Sesiones,
        *,
        abrir_url: Callable[[str], Any],
        verificar: Callable[[], Awaitable[Any]] | None,
        avisar: Callable[[str, str], Any],
        ocupado: Callable[[], bool],
        descansando: Callable[[], bool] = lambda: False,
        vincular_motor: Callable[[], Awaitable[bool]] | None = None,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sesiones = estado
        self._abrir_url = abrir_url
        self._verificar = verificar
        self._avisar = avisar
        self._ocupado = ocupado
        self._descansando = descansando
        self._vincular_motor = vincular_motor
        self._reloj = reloj

        self._cola: list[dict[str, Any]] = []
        self._hechas: dict[str, _Hecha] = {}
        self._programadas: list[_Pendiente] = []
        self._proxima_revision = reloj() + MINUTOS_PRIMERA_REVISION * 60
        self._ultima_apertura: float | None = None
        self._ultima_reverificacion: float | None = None
        self._motor: asyncio.Task | None = None

        estado.al_caer(self._se_cayo)

    # -- lo que llega y lo que se reporta -------------------------------------

    def recibir(self, acciones: Any) -> None:
        """Las acciones de la respuesta del latido. Repetidas o ya hechas se ignoran."""
        if not isinstance(acciones, list):
            return
        en_cola = {a["id"] for a in self._cola}
        for accion in acciones:
            if not isinstance(accion, dict):
                continue
            ident = str(accion.get("id") or "")
            if not ident or ident in self._hechas or ident in en_cola:
                continue
            self._cola.append(
                {
                    "id": ident,
                    "tipo": str(accion.get("tipo") or ""),
                    "datos": accion.get("datos") or {},
                }
            )
            en_cola.add(ident)

    def hechas(self) -> list[dict[str, str]]:
        """Lo que viaja en el latido. Se repite hasta `MINUTOS_RECUERDO`, por si uno se pierde."""
        ahora = self._reloj()
        self._hechas = {
            i: h for i, h in self._hechas.items() if ahora - h.cuando < MINUTOS_RECUERDO * 60
        }
        return [
            {"id": i, "resultado": h.resultado}
            for i, h in self._hechas.items()
            if not i.startswith("auto-")
        ]

    # -- lo automático ----------------------------------------------------------

    def _se_cayo(self, nombre: str, fuente: str) -> None:
        ahora = self._reloj()
        reverificar = self._ultima_reverificacion is None or (
            ahora - self._ultima_reverificacion >= HORAS_ENTRE_REVERIFICACIONES * 3600
        )
        if nombre in ("whatsapp", "claude_extension") and fuente == "job" and reverificar:
            self._ultima_reverificacion = ahora
            self._programar((MINUTOS_ANTES_DE_REVERIFICAR,), nombre, desde=ahora)
        if nombre != "whatsapp" or self._descansando():
            return
        if self._ultima_apertura is not None and (
            ahora - self._ultima_apertura < HORAS_ENTRE_APERTURAS * 3600
        ):
            return
        self._ultima_apertura = ahora
        log.info("reconexion_automatica", sesion=nombre, fuente=fuente)
        self._cola.append({"id": f"auto-{int(ahora)}", "tipo": "abrir_whatsapp", "datos": {}})

    def _programar(self, minutos: tuple[int, ...], sesion: str, *, desde: float) -> None:
        if self._verificar is None:
            return
        for m in minutos:
            self._programadas.append(_Pendiente(desde + m * 60, sesion))

    def _toca_revision_diaria(self, ahora: float) -> bool:
        if self._verificar is None or ahora < self._proxima_revision:
            return False
        confirmadas = [self._sesiones.confirmada_hace(n) for n in ("whatsapp", "claude_extension")]
        if all(c is not None and c < HORAS_SIN_CONFIRMAR * 3600 for c in confirmadas):
            #  Un job ya las confirmó hace poco: no hace falta gastar una llamada.
            self._proxima_revision = ahora + 3600
            return False
        return True

    # -- la vuelta --------------------------------------------------------------

    async def vigilar(self, *, parar: asyncio.Event, vueltas: int | None = None) -> None:
        dadas = 0
        while not parar.is_set():
            try:
                await self.una_vuelta()
            except Exception as error:  # la reconexión nunca puede tumbar al agente
                log.warning("reconexion_fallo", error=str(error)[:200])
            dadas += 1
            if vueltas is not None and dadas >= vueltas:
                return
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(parar.wait(), timeout=TICK)

    async def una_vuelta(self) -> None:
        ahora = self._reloj()

        if self._cola:
            accion = self._cola[0]
            if accion["tipo"] == "verificar" and self._ocupado():
                return  # se espera a que termine el job; `abrir_*` no tienen por qué
            self._cola.pop(0)
            resultado = await self._ejecutar(accion)
            self._hechas[accion["id"]] = _Hecha(resultado, self._reloj())
            log.info("reconexion_hecha", tipo=accion["tipo"], resultado=resultado)
            return

        #  Lo de acá para abajo gasta una llamada: nunca con un job en curso ni
        #  de noche.
        if self._ocupado() or self._descansando():
            return

        vencidas = [p for p in self._programadas if p.cuando <= ahora]
        if vencidas:
            self._programadas = [p for p in self._programadas if p.cuando > ahora]
            if any(self._sesiones.estado(p.sesion) != sesiones_mod.OK for p in vencidas):
                log.info("verificacion_programada", sesiones=sorted({p.sesion for p in vencidas}))
                await self._correr_verificacion()
            return

        if self._toca_revision_diaria(ahora):
            log.info("revision_diaria")
            self._proxima_revision = ahora + HORAS_SIN_CONFIRMAR * 3600
            await self._correr_verificacion()

    async def _ejecutar(self, accion: dict[str, Any]) -> str:
        tipo = accion["tipo"]
        if tipo == "abrir_whatsapp":
            return await self._abrir_whatsapp()
        if tipo == "abrir_claude":
            return self._abrir_claude(str((accion.get("datos") or {}).get("mail") or ""))
        if tipo == "verificar":
            return await self._correr_verificacion()
        return f"acción desconocida: {tipo}"

    async def _abrir_whatsapp(self) -> str:
        motor_caido = self._sesiones.estado("whatsapp_motor") == sesiones_mod.CAIDA
        vendedor_caido = self._sesiones.estado("whatsapp") != sesiones_mod.OK
        hecho = []
        if (
            motor_caido
            and self._vincular_motor is not None
            and (self._motor is None or self._motor.done())
        ):
            #  El navegador dedicado espera el QR varios minutos: en paralelo,
            #  para no frenar los latidos ni las otras acciones.
            self._motor = asyncio.create_task(self._vincular_motor_y_anotar())
            hecho.append("motor")
        if vendedor_caido or not hecho:
            resultado = self._abrir_url(URL_WHATSAPP)
            if not getattr(resultado, "utilizable", True):
                return f"no se pudo abrir Chrome: {getattr(resultado, 'detalle', '')}"[:300]
            hecho.append("chrome")
            self._programar(MINUTOS_VERIFICAR_WHATSAPP, "whatsapp", desde=self._reloj())
        self._avisar(
            "Volvé a conectar WhatsApp",
            "En tu celular: WhatsApp → Dispositivos vinculados → Vincular un dispositivo, "
            "y apuntá al código de la pantalla.",
        )
        return "abierto: " + ", ".join(hecho)

    async def _vincular_motor_y_anotar(self) -> None:
        try:
            quedo = await self._vincular_motor()
        except Exception as error:
            log.warning("motor_no_vinculado", error=str(error)[:200])
            return
        if quedo:
            self._sesiones.observar("whatsapp_motor", sesiones_mod.OK, "vigia", "vinculado")

    def _abrir_claude(self, mail: str) -> str:
        resultado = self._abrir_url(URL_CLAUDE)
        if not getattr(resultado, "utilizable", True):
            return f"no se pudo abrir Chrome: {getattr(resultado, 'detalle', '')}"[:300]
        texto = (
            f"Entrá con {mail} y escribí el código que te pasen."
            if mail
            else "Iniciá sesión con la cuenta de la empresa y escribí el código que te pasen."
        )
        self._avisar("Volvé a conectar Claude", texto)
        self._programar(MINUTOS_VERIFICAR_CLAUDE, "claude_extension", desde=self._reloj())
        return "abierto"

    async def _correr_verificacion(self) -> str:
        if self._verificar is None:
            return "esta máquina no puede verificar"
        limite = self._reloj() + MINUTOS_ESPERA_LIBRE * 60
        #  Un sondeo y no un Event: "ocupado" es un booleano del bucle, que no
        #  avisa cuando cambia, y esto corre a lo sumo un par de veces por día.
        while self._ocupado() and self._reloj() < limite:  # noqa: ASYNC110
            await asyncio.sleep(TICK)
        resultado = await self._verificar()
        self._sesiones.resultado_de_sonda(resultado)
        return "ok" if resultado.ok else f"falla: {resultado.motivo}"[:300]
