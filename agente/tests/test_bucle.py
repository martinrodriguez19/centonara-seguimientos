"""Tests del bucle del agente.

El criterio de salida de F1.8 es concreto: **se corta la red cinco minutos, se
reconecta, y el agente sigue funcionando sin reiniciar**. Está abajo, y no tarda
cinco minutos porque la espera se inyecta.

Todo corre contra un cliente falso. Lo que se prueba acá es la lógica de cuándo
preguntar y qué hacer con cada respuesta — no HTTP.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from agente.bucle import Bucle, Estado, latir
from agente.cliente import Job, NoAutorizado, Pausado, SinTrabajo
from agente.diagnostico import Chequeo, Diagnostico
from agente.diagnostico import Estado as EstadoChequeo


class ClienteFalso:
    """Un backend de mentira, guionado: se le dice qué contestar a cada consulta."""

    def __init__(self, respuestas: list, registro: dict | None = None) -> None:
        self._respuestas = list(respuestas)
        self._registro = registro or {"maquina": "mac-prueba", "pausada": False}
        self.reportes: list[dict] = []
        self.latidos = 0
        self.consultas = 0
        self.registros = 0

    async def registrar(self, *, version: str, diagnostico: dict) -> dict:
        self.registros += 1
        if isinstance(self._registro, Exception):
            raise self._registro
        return self._registro

    async def proximo_job(self) -> Job:
        self.consultas += 1
        siguiente = self._respuestas.pop(0) if self._respuestas else SinTrabajo()
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    async def reportar(self, job_id: str, **datos) -> dict:
        self.reportes.append({"job_id": job_id, **datos})
        return {"estado": "listo"}

    async def latido(self, diagnostico=None) -> dict:
        self.latidos += 1
        return {"ok": True}


def sin_dormir():
    """Reemplaza la espera y anota cuánto se habría esperado."""
    esperas: list[float] = []

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)

    return dormir, esperas


def diagnostico_sano() -> Diagnostico:
    return Diagnostico((Chequeo("claude_bin", EstadoChequeo.OK),))


def diagnostico_roto() -> Diagnostico:
    return Diagnostico((Chequeo("claude_bin", EstadoChequeo.FALLA, "no existe"),))


def armar(cliente, **extra) -> Bucle:
    bucle = Bucle(
        cliente,
        version="0.2.0",
        diagnosticar=extra.pop("diagnosticar", diagnostico_sano),
        intervalo=10.0,
        espera_pausado=60.0,
        **extra,
    )
    # Las esperas del bucle usan `asyncio.wait_for` sobre el evento de parada, no
    # `dormir`. Para los tests se acorta a cero: lo que se prueba es la lógica,
    # no el reloj.
    bucle._intervalo = 0.0
    bucle._espera_pausado = 0.0
    bucle._espera_maxima = 0.0
    return bucle


# ---------------------------------------------------------------------------
# Lo básico
# ---------------------------------------------------------------------------


async def test_se_registra_al_arrancar() -> None:
    cliente = ClienteFalso([])
    bucle = armar(cliente)
    await bucle.arrancar(vueltas=1)

    assert cliente.registros == 1
    assert bucle.estado.conectado


async def test_sin_trabajo_sigue_preguntando() -> None:
    cliente = ClienteFalso([SinTrabajo(), SinTrabajo(), SinTrabajo()])
    bucle = armar(cliente)
    await bucle.arrancar(vueltas=3)

    assert cliente.consultas == 3
    assert bucle.estado.jobs_hechos == 0


async def test_ejecuta_y_reporta_un_job() -> None:
    job = Job(id="j1", tipo="DIAGNOSTICO", payload={})

    async def ejecutor(_: Job) -> dict:
        return {"ok": True, "raw": "listo"}

    cliente = ClienteFalso([job])
    bucle = armar(cliente, ejecutor=ejecutor)
    await bucle.arrancar(vueltas=1)

    assert cliente.reportes == [{"job_id": "j1", "ok": True, "raw": "listo"}]
    assert bucle.estado.jobs_hechos == 1


# ---------------------------------------------------------------------------
# El criterio de salida de F1.8
# ---------------------------------------------------------------------------


async def test_se_corta_la_red_y_el_agente_sigue_vivo_sin_reiniciar() -> None:
    """⚠️ El criterio de salida, escrito como test.

    Treinta consultas fallidas seguidas —una caída larga— y después la red
    vuelve. El agente tiene que seguir siendo el mismo proceso, tomar el job y
    reportarlo.
    """
    caida = [httpx.ConnectError("sin red")] * 30
    job = Job(id="j1", tipo="DIAGNOSTICO", payload={})
    cliente = ClienteFalso([*caida, job])

    bucle = armar(cliente)
    await bucle.arrancar(vueltas=31)

    assert bucle.estado.jobs_hechos == 1
    assert bucle.estado.conectado, "se reconectó y lo sabe"
    assert bucle.estado.fallos_seguidos == 0, "el contador se reinicia al volver"


async def test_el_agente_nunca_se_rinde() -> None:
    """Cien fallos seguidos y sigue preguntando.

    Un agente que se muere después de N intentos hay que ir a levantarlo a la
    computadora de otra persona.
    """
    cliente = ClienteFalso([httpx.ConnectError("sin red")] * 100)
    bucle = armar(cliente)
    await bucle.arrancar(vueltas=100)

    assert cliente.consultas == 100
    assert bucle.estado.fallos_seguidos == 100


async def test_la_espera_crece_pero_tiene_techo() -> None:
    """Una caída de red no puede generar cientos de peticiones por minuto."""
    bucle = Bucle(
        ClienteFalso([httpx.ConnectError("sin red")] * 10),
        version="0.2.0",
        diagnosticar=diagnostico_sano,
        intervalo=10.0,
        espera_maxima=120.0,
    )
    esperas: list[float] = []

    async def espiar(segundos: float) -> None:
        esperas.append(segundos)

    bucle._esperar = espiar  # type: ignore[method-assign]
    await bucle.arrancar(vueltas=10)

    assert esperas[0] == 10.0
    assert esperas[1] == 20.0
    assert esperas[2] == 40.0
    assert max(esperas) == 120.0, "no crece para siempre"


# ---------------------------------------------------------------------------
# Pausa y token
# ---------------------------------------------------------------------------


async def test_la_pausa_no_cuenta_como_error() -> None:
    """Un 423 es el sistema funcionando, no una falla de red."""
    cliente = ClienteFalso([Pausado("pausa global")])
    bucle = armar(cliente)
    await bucle.arrancar(vueltas=1)

    assert bucle.estado.pausado
    assert bucle.estado.conectado
    assert bucle.estado.fallos_seguidos == 0


async def test_al_soltar_la_pausa_vuelve_a_trabajar() -> None:
    job = Job(id="j1", tipo="DIAGNOSTICO", payload={})
    cliente = ClienteFalso([Pausado("pausa"), Pausado("pausa"), job])
    bucle = armar(cliente)
    await bucle.arrancar(vueltas=3)

    assert not bucle.estado.pausado
    assert bucle.estado.jobs_hechos == 1


async def test_un_token_rechazado_se_distingue_de_una_caida_de_red() -> None:
    """Reintentar no lo arregla: alguien tiene que dar de alta la máquina."""
    cliente = ClienteFalso([NoAutorizado("token inválido")])
    bucle = armar(cliente)
    await bucle.arrancar(vueltas=1)

    assert bucle.estado.token_rechazado
    assert not bucle.estado.conectado
    assert "token" in bucle.estado.ultimo_error


async def test_el_registro_que_falla_no_impide_arrancar() -> None:
    """El backend reiniciándose no puede dejar un agente muerto."""
    cliente = ClienteFalso([SinTrabajo()], registro=httpx.ConnectError("sin red"))
    bucle = armar(cliente)
    await bucle.arrancar(vueltas=1)

    assert cliente.consultas == 1, "arrancó igual"


# ---------------------------------------------------------------------------
# Siempre se reporta
# ---------------------------------------------------------------------------


async def test_un_ejecutor_que_revienta_igual_reporta() -> None:
    """Un job tomado que nadie reporta queda colgado y el panel no dice por qué."""

    async def explota(_: Job) -> dict:
        raise RuntimeError("Chrome se cerró")

    cliente = ClienteFalso([Job(id="j1", tipo="ENVIAR", payload={})])
    bucle = armar(cliente, ejecutor=explota)
    await bucle.arrancar(vueltas=1)

    assert len(cliente.reportes) == 1
    reporte = cliente.reportes[0]
    assert reporte["ok"] is False
    assert reporte["codigo"] == "ERROR_INESPERADO"
    assert "Chrome se cerró" in reporte["stderr"]


async def test_un_tipo_de_job_que_el_agente_no_conoce_se_reporta_como_fallo() -> None:
    """Falla explícito, no en silencio."""
    cliente = ClienteFalso([Job(id="j1", tipo="ENVIAR", payload={})])
    bucle = armar(cliente)
    await bucle.arrancar(vueltas=1)

    assert cliente.reportes[0]["ok"] is False
    assert "ENVIAR" in cliente.reportes[0]["detalle"]["motivo"]


async def test_si_el_reporte_no_llega_no_se_reintenta_el_job() -> None:
    """El backend recupera el job solo. Reintentar acá podría enviarlo dos veces."""

    class ReporteRoto(ClienteFalso):
        async def reportar(self, job_id: str, **datos) -> dict:
            raise httpx.ConnectError("se cortó al reportar")

    cliente = ReporteRoto([Job(id="j1", tipo="DIAGNOSTICO", payload={})])
    bucle = armar(cliente)
    await bucle.arrancar(vueltas=1)

    assert bucle.estado.jobs_hechos == 0
    assert not bucle.estado.conectado


# ---------------------------------------------------------------------------
# El estado que lee el ícono de la barra de menú
# ---------------------------------------------------------------------------


async def test_verde_cuando_todo_anda() -> None:
    bucle = armar(ClienteFalso([]))
    await bucle.arrancar(vueltas=1)
    assert bucle.estado.color == "verde"


async def test_amarillo_con_un_chequeo_en_falla() -> None:
    """Degradado: conectado, pero no puede tomar envíos."""
    bucle = armar(ClienteFalso([]), diagnosticar=diagnostico_roto)
    await bucle.arrancar(vueltas=1)

    assert bucle.estado.color == "amarillo"
    assert not bucle.estado.diagnostico.puede_enviar


async def test_rojo_sin_conexion() -> None:
    bucle = armar(ClienteFalso([httpx.ConnectError("sin red")]))
    await bucle.arrancar(vueltas=1)
    assert bucle.estado.color == "rojo"


async def test_pausado_se_ve_distinto_de_roto() -> None:
    """Para el vendedor no es lo mismo "lo pausé yo" que "algo anda mal"."""
    bucle = armar(ClienteFalso([Pausado("pausa")]))
    await bucle.arrancar(vueltas=1)
    assert bucle.estado.color == "pausado"


async def test_el_token_rechazado_se_ve_rojo_aunque_haya_red() -> None:
    bucle = armar(ClienteFalso([NoAutorizado("token")]))
    await bucle.arrancar(vueltas=1)
    assert bucle.estado.color == "rojo"


# ---------------------------------------------------------------------------
# Parada ordenada
# ---------------------------------------------------------------------------


async def test_detener_corta_el_bucle() -> None:
    cliente = ClienteFalso([SinTrabajo()] * 100)
    bucle = armar(cliente)
    bucle.detener()
    await bucle.arrancar(vueltas=100)

    assert cliente.consultas == 0, "no llegó a preguntar ni una vez"


# ---------------------------------------------------------------------------
# El latido
# ---------------------------------------------------------------------------


async def test_el_latido_manda_el_diagnostico() -> None:
    cliente = ClienteFalso([])
    dormir, _ = sin_dormir()
    mandados = await latir(
        cliente, Estado(diagnostico=diagnostico_sano()), dormir=dormir, vueltas=3
    )

    assert mandados == 3
    assert cliente.latidos == 3


async def test_un_latido_que_falla_no_rompe_nada_y_el_bucle_termina() -> None:
    """El que avisa que algo anda mal es el bucle, no el latido.

    Regresión: `vueltas` cuenta intentos y no latidos llegados. Contando
    llegados, una máquina sin red no alcanzaba nunca el número y esto se colgaba
    para siempre — que es exactamente lo que hizo la primera versión.
    """

    class LatidoRoto(ClienteFalso):
        async def latido(self, diagnostico=None) -> dict:
            raise httpx.ConnectError("sin red")

    dormir, _ = sin_dormir()
    mandados = await latir(LatidoRoto([]), Estado(), dormir=dormir, vueltas=5)

    assert mandados == 0, "no llegó ninguno"


async def test_el_latido_existe_para_cuando_esta_pausado() -> None:
    """Pausado no pregunta por trabajo, así que no hay consulta que valga de latido.

    Sin esto, el panel mostraría en rojo una Mac sana que alguien pausó a
    propósito.
    """
    cliente = ClienteFalso([])
    dormir, _ = sin_dormir()
    await latir(cliente, Estado(pausado=True), dormir=dormir, vueltas=2)

    assert cliente.latidos == 2


@pytest.mark.parametrize("vueltas", [0, 1, 5])
async def test_el_latido_respeta_la_cantidad_pedida(vueltas: int) -> None:
    cliente = ClienteFalso([])
    dormir, _ = sin_dormir()
    parar = asyncio.Event()
    if vueltas == 0:
        parar.set()

    mandados = await latir(cliente, Estado(), dormir=dormir, parar=parar, vueltas=vueltas or None)
    assert mandados == vueltas
