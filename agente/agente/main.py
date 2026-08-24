"""Punto de entrada del agente.

    uv run python -m agente.main --simulado

Esqueleto: lee la configuración, la valida y loguea un latido cada 10 segundos.
**Nada más.** No hay bucle de consulta ni diagnóstico (fase 1), y no hay
navegador ni envío (fase 3).

Es la forma en que trabaja el equipo mientras no haya una Mac disponible
(04-AGENTE.md §11), así que corre igual en macOS, Linux y Windows: sin rutas de
un sistema en particular, sin `os.system`, sin nada que dependa del SO.
"""

import argparse
import asyncio
import os
import signal
import sys
import threading
from collections.abc import Sequence
from types import FrameType

from pydantic import ValidationError

from agente import __version__, diagnostico, sonda
from agente.bucle import Bucle, latir
from agente.cliente import Cliente
from agente.config import CARPETA_AGENTE, Configuracion, Modo, obtener_configuracion
from agente.jobs import ejecutor
from agente.logging import configurar_logs, obtener_logger

log = obtener_logger(__name__)

# Mismo intervalo con el que el agente va a consultar al backend en la fase 1.
INTERVALO_SIMULADO_SEGUNDOS = 10.0

SALIDA_OK = 0
SALIDA_CONFIGURACION = 2
SALIDA_DIAGNOSTICO = 3


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
    parser.add_argument(
        "--diagnostico",
        action="store_true",
        help="Corre los nueve chequeos, los imprime y sale. No consulta al backend.",
    )
    parser.add_argument(
        "--sonda",
        action="store_true",
        help=(
            "Abre WhatsApp Web una vez para contestar los dos chequeos que el "
            "diagnóstico no puede: el permiso de sitio y la sesión. Cuesta dinero "
            "y tarda minutos, por eso no va en --diagnostico. No lee ningún chat."
        ),
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


def soltar_sslkeylogfile() -> str | None:
    """Saca `SSLKEYLOGFILE` del entorno del proceso, y devuelve lo que sacó.

    Un antivirus con escudo web —Avast, y los que hacen lo mismo— deja esa
    variable apuntando a su driver de filtrado, para quedarse con las claves de
    sesión de todo el TLS de la máquina. Cuando OpenSSL crea un contexto abre
    ese archivo con `fopen`, y eso cruza la frontera entre el runtime de C de
    OpenSSL y el del módulo que lo llama. En Windows eso necesita `applink`, que
    el `_ssl.pyd` de esta distribución de Python no trae, y el proceso **se
    muere** con un mensaje que no menciona ni al antivirus ni al TLS:

        OPENSSL_Uplink(...,08): no OPENSSL_Applink

    Sin eso el agente no llega ni a presentarse al backend, y el vendedor ve una
    máquina que no arranca sin ninguna pista de por qué.

    Se saca sólo del entorno de este proceso: no se toca la configuración del
    antivirus ni la de la máquina. Y de paso es lo correcto por otro motivo —
    las claves de sesión del agente no tienen por qué quedar registradas en
    ningún lado.
    """
    valor = os.environ.pop("SSLKEYLOGFILE", None)
    if valor:
        log.warning(
            "sslkeylogfile_descartado",
            detalle="lo dejó un antivirus con escudo web; con eso puesto, OpenSSL mata el proceso",
            valor=valor,
        )
    return valor


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    soltar_sslkeylogfile()

    try:
        config = obtener_configuracion()
    except ValidationError as error:
        # Todavía no hay logs configurados: esto va crudo a stderr.
        print(f"Configuración inválida, el agente no arranca:\n{error}", file=sys.stderr)
        return SALIDA_CONFIGURACION

    configurar_logs(config)

    if args.diagnostico:
        return correr_diagnostico(config)

    if args.sonda:
        return correr_sonda(config)

    modo = resolver_modo(config, args.simulado)

    # El bloque que cortaba acá cuando el modo no era `simulado` se fue: el motor
    # de envío ya existe (`adaptadores/whatsapp_web.py`), así que negarse a
    # arrancar sería negarse a hacer el trabajo.
    #
    # Lo que impide que un mensaje llegue a alguien que no corresponde no era
    # nunca este bloque, y sigue en pie:
    #
    #   - `destinos_permitidos`, verificado en el backend al encolar y otra vez
    #     en el agente antes de escribir (R4)
    #   - la comparación de identidad contra el chat abierto (R1)
    #   - y, mientras los selectores no se hayan verificado contra WhatsApp Web,
    #     un `ENVIAR` en modo `real` se rechaza en el despachador
    #
    # Además `AGENTE_MODO` viene en `simulado` por defecto en todos lados: para
    # que algo salga hay que decirlo, y eso queda escrito en la máquina.

    parar = threading.Event()
    atender_apagado(parar)

    # Sin backend configurado no hay a quién preguntarle: se queda latiendo en
    # seco, que es como trabaja el equipo mientras se desarrollan las otras
    # partes. Con backend, arranca el bucle de verdad.
    if not config.token:
        log.info("sin_token", detalle="sin AGENTE_TOKEN no hay a quién consultar: modo latido")
        ejecutar_simulado(config, parar=parar)
        return SALIDA_OK

    asyncio.run(_trabajar(config, parar, modo=modo))
    return SALIDA_OK


def correr_sonda(config: Configuracion) -> int:
    """`--sonda`: lo que el diagnóstico no puede contestar sin abrir el navegador.

    Se corre a mano, una vez por máquina, cuando se la instala. Es lo que cierra
    `permiso_sitio` y `whatsapp_sesion`, que en el diagnóstico salen siempre
    `n/a` porque no se pueden verificar leyendo archivos.
    """
    print("Abriendo WhatsApp Web una vez. Tarda unos minutos y no lee ningún chat.\n")
    resultado = asyncio.run(
        sonda.probar(
            device_id=config.device_id,
            claude_bin=config.claude_bin,
            carpeta=CARPETA_AGENTE,
        )
    )
    print(resultado.como_texto())
    print(f"\nCostó USD {resultado.costo_usd:.4f}.")
    return SALIDA_OK if resultado.ok else SALIDA_DIAGNOSTICO


def correr_diagnostico(config: Configuracion) -> int:
    """`--diagnostico`: corre los chequeos, los imprime y sale.

    Es lo primero que se corre en una máquina nueva, y lo primero que se pide
    cuando alguien dice "no anda". Imprime a stdout y no sólo al log para que
    se pueda pegar en un mensaje.
    """
    resultado = diagnostico.ejecutar(
        claude_bin=config.claude_bin,
        device_id=config.device_id,
        carpeta_agente=CARPETA_AGENTE,
    )
    for chequeo in resultado.chequeos:
        marca = {"ok": "OK ", "falla": "MAL", "n/a": " - "}[str(chequeo.estado)]
        print(f"[{marca}] {chequeo.nombre:16} {chequeo.detalle}")

    if resultado.puede_enviar:
        print()
        print("Todo en orden.")
        return SALIDA_OK
    print()
    print(f"Degradado: {resultado.resumen()}")
    return SALIDA_DIAGNOSTICO


async def _trabajar(config: Configuracion, parar: threading.Event, *, modo: str) -> None:
    """El bucle y el latido, en paralelo, hasta que alguien pida parar."""
    cliente = Cliente(config.backend_url, config.token)

    def diagnosticar():
        return diagnostico.ejecutar(
            claude_bin=config.claude_bin,
            device_id=config.device_id,
            carpeta_agente=CARPETA_AGENTE,
        )

    trabajo = Bucle(
        cliente,
        version=__version__,
        diagnosticar=diagnosticar,
        ejecutor=ejecutor.construir(
            claude_bin=config.claude_bin,
            device_id=config.device_id,
            carpeta=CARPETA_AGENTE,
            # El modo RESUELTO, no el de la configuración: `--simulado` tiene que
            # ganarle al entorno, que es para lo único que existe esa opción.
            modo=modo,
            diagnosticar=diagnosticar,
        ),
    )
    fin = asyncio.Event()

    def vigilar_apagado() -> None:
        """Puente entre la señal (que llega a un hilo) y el bucle (que es async)."""
        parar.wait()
        trabajo.detener()
        fin.set()

    threading.Thread(target=vigilar_apagado, daemon=True).start()

    try:
        await asyncio.gather(trabajo.arrancar(), latir(cliente, trabajo.estado, parar=fin))
    finally:
        await cliente.cerrar()
        log.info("agente_detenido", jobs=trabajo.estado.jobs_hechos)


if __name__ == "__main__":
    raise SystemExit(main())
