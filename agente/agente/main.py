"""Punto de entrada del agente.

    uv run python -m agente.main --simulado

Esqueleto del Sprint 0 (T0.5): lee la configuración, la valida y loguea un
latido cada 10 segundos. **Nada más.** No hay long-poll (Sprint 1), no hay
autodiagnóstico (Sprint 1), no hay navegador y no hay envío (Sprint 4, R7).

Es la forma en que trabaja todo el equipo hasta el Sprint 4 (06 §3 y §5), así
que corre igual en Linux, macOS y Windows: sin rutas de Windows, sin
`os.system`, sin nada que dependa del sistema operativo.
"""

import argparse
import signal
import sys
import threading
from collections.abc import Sequence
from types import FrameType

from pydantic import ValidationError

from agente import __version__
from agente.config import CARPETA_AGENTE, Configuracion, Modo, obtener_configuracion
from agente.logging import configurar_logs, obtener_logger

log = obtener_logger(__name__)

# T0.5: "modo --simulado que loguea cada 10 segundos".
INTERVALO_SIMULADO_SEGUNDOS = 10.0

SALIDA_OK = 0
SALIDA_CONFIGURACION = 2


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agente",
        description="Agente local del Sistema de Seguimiento Comercial v2.",
    )
    # No existe una opción --real ni --prueba, a propósito: para que el agente
    # haga algo distinto de simular hay que cambiar la configuración de la
    # máquina, que es un acto deliberado y queda escrito.
    parser.add_argument(
        "--simulado",
        action="store_true",
        help="Fuerza el modo simulado, sin tocar el navegador. Gana sobre AGENTE_MODO.",
    )
    parser.add_argument("--version", action="version", version=f"agente {__version__}")
    return parser


def resolver_modo(config: Configuracion, forzar_simulado: bool) -> Modo:
    """El modo con el que se va a correr.

    La opción de línea de comandos gana sobre el entorno, y la única que hay
    lleva hacia el lado seguro.
    """
    return "simulado" if forzar_simulado else config.modo


def ejecutar_simulado(
    config: Configuracion,
    *,
    intervalo_segundos: float = INTERVALO_SIMULADO_SEGUNDOS,
    parar: threading.Event | None = None,
    ciclos: int | None = None,
) -> int:
    """Late cada `intervalo_segundos` hasta que le pidan parar.

    No abre una conexión, no lee un archivo, no lanza un proceso. Sirve para
    tener el agente corriendo mientras se desarrollan backend y frontend, y
    para verificar que el proceso arranca y se apaga bien en los tres sistemas
    operativos.

    Devuelve la cantidad de latidos, que es lo que miran los tests.
    """
    parar = parar if parar is not None else threading.Event()

    log.info(
        "simulado_arrancado",
        intervalo_s=intervalo_segundos,
        carpeta=str(CARPETA_AGENTE),
        plataforma=f"{sys.platform} python{sys.version_info.major}.{sys.version_info.minor}",
        **config.resumen_para_log(),
    )

    latidos = 0
    try:
        while not parar.is_set():
            latidos += 1
            log.info("simulado_latido", latido=latidos, sin_trabajo_real=True)
            if ciclos is not None and latidos >= ciclos:
                break
            # `Event.wait` y no `time.sleep`: el apagado corta en el momento en
            # vez de esperar a que termine el intervalo.
            parar.wait(intervalo_segundos)
    except KeyboardInterrupt:
        # Ctrl+C en una terminal, cuando llega como excepción y no por el
        # manejador de señales. Salir es la respuesta correcta, pero queda
        # registrado: en el agente no se traga nada en silencio.
        log.info("simulado_interrumpido", latidos=latidos)

    log.info("simulado_detenido", latidos=latidos)
    return latidos


def atender_apagado(parar: threading.Event) -> None:
    """Ctrl+C y apagado ordenado, en los tres sistemas operativos.

    En Windows existe SIGBREAK (Ctrl+Pausa) y no existe casi nada de lo demas,
    asi que se registra lo que haya en vez de dar por sentado un catalogo.
    """

    def _parar(numero: int, marco: FrameType | None) -> None:
        log.info("senal_recibida", senal=signal.Signals(numero).name)
        parar.set()

    for nombre in ("SIGINT", "SIGTERM", "SIGBREAK"):
        senal = getattr(signal, nombre, None)
        if senal is None:
            continue
        # Si el sistema no la acepta, es un dato: se registra y se sigue.
        try:
            signal.signal(senal, _parar)
        except (OSError, ValueError) as error:
            log.warning("senal_no_registrada", senal=nombre, motivo=str(error))


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)

    try:
        config = obtener_configuracion()
    except ValidationError as error:
        # Todavía no hay logs configurados: esto va crudo a stderr.
        print(f"Configuración inválida, el agente no arranca:\n{error}", file=sys.stderr)
        return SALIDA_CONFIGURACION

    configurar_logs(config)
    modo = resolver_modo(config, args.simulado)

    # ---- R7 -----------------------------------------------------------------
    # `prueba` y `real` necesitan el motor de Playwright, que no existe en el
    # repositorio hasta el Sprint 4. El agente no arranca a medias ni "hace lo
    # que puede": corta acá (R3).
    # BORRAR ESTE BLOQUE EN EL SPRINT 4, junto con el job `sin-envio` del CI.
    if modo != "simulado":
        log.error(
            "modo_no_disponible",
            modo=modo,
            regla="R7",
            detalle=(
                "El código de envío no existe hasta el Sprint 4. "
                "Corré con --simulado o poné AGENTE_MODO=simulado."
            ),
        )
        return SALIDA_CONFIGURACION
    # -------------------------------------------------------------------------

    parar = threading.Event()
    atender_apagado(parar)
    ejecutar_simulado(config, parar=parar)
    return SALIDA_OK


if __name__ == "__main__":
    raise SystemExit(main())
