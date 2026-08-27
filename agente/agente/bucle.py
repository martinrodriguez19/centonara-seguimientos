"""El bucle: preguntar, ejecutar, reportar. Para siempre.

**Nunca se rinde.** La Mac de un vendedor se queda sin wifi, se suspende, se
lleva a una obra. Un agente que se muere después de N intentos fallidos es un
agente que hay que ir a reiniciar a mano, en la computadora de otra persona.

Lo que sí hace es **esperar cada vez más** entre intentos fallidos, hasta un
techo. Así una caída de red de cinco minutos no genera trescientas peticiones
contra un backend que ya está mal.

El reloj y la espera se inyectan. No es ceremonia: sin eso, el test de "se corta
la red cinco minutos y el agente sigue vivo" tardaría cinco minutos.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

from agente.cliente import Cliente, Job, NoAutorizado, Pausado, SinTrabajo
from agente.diagnostico import Diagnostico
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# Cada cuánto se pregunta si hay trabajo, cuando todo anda bien.
INTERVALO_CONSULTA = 10.0

# Cada cuánto se manda un latido aparte. La consulta de trabajo también cuenta
# como latido en el backend, así que esto es para cuando el agente está pausado
# y no está preguntando por trabajo — que es justo cuando el panel necesita
# saber que sigue vivo.
INTERVALO_LATIDO = 30.0

# Cuánto se espera con la pausa puesta. Más largo que el intervalo normal: no
# tiene sentido insistir cada 10 s contra un kill switch, y acorta la reacción
# cuando lo sueltan sólo en un minuto.
ESPERA_PAUSADO = 60.0

# Backoff ante errores de red. Arranca en el intervalo normal y se duplica.
ESPERA_MAXIMA = 300.0


@dataclass
class Estado:
    """Lo que el bucle sabe de sí mismo. Lo lee el ícono de la barra de menú."""

    conectado: bool = False
    pausado: bool = False
    token_rechazado: bool = False
    jobs_hechos: int = 0
    fallos_seguidos: int = 0
    ultimo_error: str = ""
    diagnostico: Diagnostico = field(default_factory=Diagnostico)

    @property
    def color(self) -> str:
        """🟢 conectado · 🟡 degradado · 🔴 sin conexión · ⏸️ pausado."""
        if self.token_rechazado or not self.conectado:
            return "rojo"
        if self.pausado:
            return "pausado"
        if not self.diagnostico.puede_enviar:
            return "amarillo"
        return "verde"


Ejecutor = Callable[[Job], Awaitable[dict]]


async def _no_sabe_hacer_nada(job: Job) -> dict:
    """El ejecutor por defecto: reporta que no sabe hacer ese trabajo.

    Falla explícito y no en silencio. Un job que se toma y nadie reporta queda
    colgado hasta que lo recupere el barrido, y el panel muestra una corrida que
    nunca termina sin decir por qué.
    """
    return {
        "ok": False,
        "codigo": "ERROR_INESPERADO",
        "detalle": {"motivo": f"este agente no sabe ejecutar {job.tipo}"},
    }


class Bucle:
    def __init__(
        self,
        cliente: Cliente,
        *,
        version: str,
        diagnosticar: Callable[[], Diagnostico],
        ejecutor: Ejecutor | None = None,
        intervalo: float = INTERVALO_CONSULTA,
        espera_pausado: float = ESPERA_PAUSADO,
        espera_maxima: float = ESPERA_MAXIMA,
        dormir: Callable[[float], Awaitable[None]] | None = None,
        modo: str = "",
    ) -> None:
        self._cliente = cliente
        self._version = version
        # El modo resuelto de esta máquina. Viaja en el registro para que el
        # panel pueda decir "esta Mac está en simulado" — la causa del 26/08
        # que hubo que diagnosticar entrando al `.env` por ssh.
        self._modo = modo
        self._diagnosticar = diagnosticar
        self._ejecutar = ejecutor or _no_sabe_hacer_nada
        self._intervalo = intervalo
        self._espera_pausado = espera_pausado
        self._espera_maxima = espera_maxima
        self._dormir = dormir or asyncio.sleep
        self.estado = Estado()
        self._parar = asyncio.Event()

    def detener(self) -> None:
        self._parar.set()

    async def arrancar(self, *, vueltas: int | None = None) -> Estado:
        """El bucle. `vueltas` lo acota para los tests; en producción no se pasa."""
        self.estado.diagnostico = self._diagnosticar()
        await self._registrar()

        dadas = 0
        while not self._parar.is_set():
            await self._una_vuelta()
            dadas += 1
            if vueltas is not None and dadas >= vueltas:
                break
        return self.estado

    async def _registrar(self) -> None:
        """Presentarse. Si falla, no importa: el bucle arranca igual.

        El registro es cortesía —le dice al panel qué versión corre y con qué
        diagnóstico—, no un requisito. Un agente que no arranca porque el
        backend estaba reiniciándose es un agente que hay que ir a levantar a
        mano.
        """
        try:
            respuesta = await self._cliente.registrar(
                version=self._version,
                diagnostico=self.estado.diagnostico.a_dict(),
                modo=self._modo,
            )
            self.estado.conectado = True
            self.estado.pausado = bool(respuesta.get("pausada"))
            log.info("agente_registrado", **{k: respuesta.get(k) for k in ("maquina", "pausada")})
        except NoAutorizado:
            self._token_rechazado()
        except (httpx.HTTPError, OSError) as error:
            log.warning("registro_fallido", error=str(error))

    async def _una_vuelta(self) -> None:
        try:
            job = await self._cliente.proximo_job()
        except SinTrabajo:
            self._anda_bien()
            await self._esperar(self._intervalo)
            return
        except Pausado:
            self._anda_bien()
            self.estado.pausado = True
            await self._esperar(self._espera_pausado)
            return
        except NoAutorizado:
            self._token_rechazado()
            await self._esperar(self._espera_pausado)
            return
        except (httpx.HTTPError, OSError) as error:
            await self._hubo_un_problema(error)
            return

        self._anda_bien()
        self.estado.pausado = False
        await self._hacer(job)

    async def _hacer(self, job: Job) -> None:
        """Ejecuta un job y lo reporta. **Siempre reporta.**

        Si el ejecutor revienta, se reporta el fallo con la excepción como
        detalle. Un job tomado que nadie reporta queda colgado hasta el barrido
        y deja al panel mostrando una corrida que no termina.
        """
        log.info("job_tomado", job=job.id, tipo=job.tipo)
        try:
            resultado = await self._ejecutar(job)
        except Exception as error:
            log.error("job_reventó", job=job.id, tipo=job.tipo, error=str(error))
            resultado = {
                "ok": False,
                "codigo": "ERROR_INESPERADO",
                "detalle": {"excepcion": type(error).__name__, "mensaje": str(error)[:500]},
                "stderr": str(error)[:2000],
            }

        try:
            await self._cliente.reportar(job.id, **resultado)
            self.estado.jobs_hechos += 1
        except (httpx.HTTPError, OSError) as error:
            # El trabajo se hizo y el reporte no llegó. No se reintenta acá: el
            # backend recupera el job por sí solo cuando pasa el tiempo de
            # colgado, y eso es más seguro que un reintento que podría
            # ejecutarlo dos veces.
            await self._hubo_un_problema(error, que="reporte_perdido")

    async def _esperar(self, segundos: float) -> None:
        """Espera, pero corta apenas alguien pide parar.

        Que se cumpla el plazo es el caso NORMAL, no un error: `TimeoutError`
        acá significa "pasaron los diez segundos y nadie pidió parar".
        """
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._parar.wait(), timeout=segundos)

    def _anda_bien(self) -> None:
        self.estado.conectado = True
        self.estado.token_rechazado = False
        self.estado.fallos_seguidos = 0
        self.estado.ultimo_error = ""

    def _token_rechazado(self) -> None:
        """401. Reintentar no lo arregla: alguien tiene que dar de alta la máquina."""
        self.estado.token_rechazado = True
        self.estado.conectado = False
        self.estado.ultimo_error = "el backend rechazó el token de esta máquina"
        log.error("token_rechazado")

    async def _hubo_un_problema(self, error: Exception, *, que: str = "sin_conexion") -> None:
        self.estado.conectado = False
        self.estado.fallos_seguidos += 1
        self.estado.ultimo_error = f"{type(error).__name__}: {error}"[:200]

        espera = min(
            self._intervalo * (2 ** (self.estado.fallos_seguidos - 1)), self._espera_maxima
        )
        log.warning(
            que, fallos=self.estado.fallos_seguidos, espera_s=espera, error=str(error)[:200]
        )
        await self._esperar(espera)


async def latir(
    cliente: Cliente,
    estado: Estado,
    *,
    intervalo: float = INTERVALO_LATIDO,
    parar: asyncio.Event | None = None,
    dormir: Callable[[float], Awaitable[None]] | None = None,
    vueltas: int | None = None,
) -> int:
    """Manda un latido cada `intervalo`, en paralelo al bucle.

    Existe para el caso pausado: ahí el agente no pregunta por trabajo, así que
    no hay consulta que valga como latido, y sin esto el panel mostraría en rojo
    a una Mac perfectamente sana que alguien pausó a propósito.

    Un latido que falla no es un problema: el que manda la señal de "algo anda
    mal" es el bucle, no esto.

    Devuelve cuántos llegaron. `vueltas` cuenta INTENTOS y no llegados: si
    contara llegados, una máquina sin red nunca alcanzaría el número y el bucle
    no terminaría jamás.
    """
    esperar = dormir or asyncio.sleep
    fin = parar or asyncio.Event()
    intentos = 0
    mandados = 0

    while not fin.is_set():
        intentos += 1
        try:
            await cliente.latido(estado.diagnostico.a_dict())
            mandados += 1
        except (httpx.HTTPError, OSError, NoAutorizado, Pausado) as error:
            log.debug("latido_fallido", error=str(error)[:120])

        if vueltas is not None and intentos >= vueltas:
            break
        await esperar(intervalo)

    return mandados
