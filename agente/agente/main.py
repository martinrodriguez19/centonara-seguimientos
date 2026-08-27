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
    # No existe una opción --real ni --prueba, a propósito: qué pasa con cada
    # mensaje —borrador o envío— lo decide el panel y viaja en el payload de
    # cada job (D32). El agente instalado está siempre operativo.
    parser.add_argument(
        "--simulado",
        action="store_true",
        help=(
            "Modo de desarrollo: corre contra una página en memoria, sin tocar "
            "ningún navegador. Es la única forma de que el agente no sea "
            "operativo — no hay variable de entorno que lo haga (D32)."
        ),
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
    parser.add_argument(
        "--datos",
        action="store_true",
        help=(
            "Averigua lo que se puede saber de esta máquina —qué perfil de Chrome "
            "usar y cuál es su deviceId— e imprime las líneas del .env listas para "
            "pegar. Es el primer comando que hay que correr al instalar."
        ),
    )
    parser.add_argument(
        "--vincular",
        action="store_true",
        help=(
            "Abre el navegador dedicado del motor de envío (D24) para escanear el "
            "QR de WhatsApp con el teléfono del vendedor. Una vez por máquina, y "
            "de nuevo cuando esa sesión expire."
        ),
    )
    parser.add_argument(
        "--verificar-selectores",
        action="store_true",
        dest="verificar_selectores",
        help=(
            "Comprueba los selectores contra WhatsApp Web real, en el navegador "
            "dedicado. Con --chat abre ese chat y verifica también los del chat "
            "abierto. No envía nada."
        ),
    )
    parser.add_argument(
        "--chat",
        default="",
        help=(
            "Con --verificar-selectores: el número de PRUEBA cuyo chat se abre "
            "para verificar encabezado, campo y botón. Elegirlo a propósito."
        ),
    )
    parser.add_argument("--version", action="version", version=f"agente {__version__}")
    return parser


def resolver_modo(forzar_simulado: bool) -> Modo:
    """Operativo, salvo que la línea de comandos pida simular (D32).

    No hay variable de entorno que decida esto: la perilla `AGENTE_MODO` fue la
    causa del incidente del 26/08 —Macs que quedaron en simulado tras instalar—
    y se eliminó. Un `.env` viejo que todavía la tenga se ignora.
    """
    return "simulado" if forzar_simulado else "operativo"


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

    if args.datos:
        return correr_datos(config)

    if args.diagnostico:
        return correr_diagnostico(config)

    if args.sonda:
        return correr_sonda(config)

    if args.vincular:
        from agente import verificacion

        return SALIDA_OK if asyncio.run(verificacion.vincular(config)) else SALIDA_DIAGNOSTICO

    if args.verificar_selectores:
        from agente import verificacion

        paso = asyncio.run(verificacion.verificar_selectores(config, chat=args.chat))
        return SALIDA_OK if paso else SALIDA_DIAGNOSTICO

    modo = resolver_modo(args.simulado)

    # Lo que impide que un mensaje llegue a alguien que no corresponde nunca
    # fue el modo de la máquina (D32), y sigue en pie:
    #
    #   - `destinos_permitidos`, verificado en el backend al encolar y otra vez
    #     en el agente antes de escribir (R4)
    #   - la comparación de identidad contra el chat abierto (R1)
    #   - qué se hace con cada mensaje —borrador o envío— lo decide el panel y
    #     viaja en el payload; enviar de verdad tiene su fricción propia ahí
    #   - y, mientras los selectores no se hayan verificado contra WhatsApp
    #     Web, un envío real se rechaza en el despachador

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


def correr_datos(config: Configuracion) -> int:
    """`--datos`: lo que hay que poner en el `.env`, ya resuelto.

    Existe para que instalar una máquina no requiera correr un `grep` con
    espacios escapados ni comparar dos listas de rutas a ojo. Lo que la máquina
    puede saber sola, lo dice; lo que no —el token y el identificador, que salen
    del panel— lo deja marcado.
    """
    from agente import perfiles

    todos = perfiles.listar()
    recomendacion = perfiles.recomendar(todos)

    print("PERFILES DE CHROME EN ESTA MÁQUINA")
    print(f"  {perfiles.carpeta_chrome()}")
    print()
    if not todos:
        print("  (ninguno)")
    for perfil in todos:
        marcas = []
        if perfil.tiene_extension:
            marcas.append("extensión")
        if perfil.tiene_whatsapp:
            marcas.append("WhatsApp")
        estado = " + ".join(marcas) if marcas else "nada"
        senial = (
            "  <-- este"
            if recomendacion.perfil and perfil.nombre == recomendacion.perfil.nombre
            else ""
        )
        print(f"  {perfil.nombre:14} {estado}{senial}")
    print()

    if not recomendacion.listo:
        print("NO SE PUEDE SEGUIR TODAVÍA")
        print(f"  {recomendacion.problema}")
        print()
        print(f"  Qué hacer: {recomendacion.solucion}")
        print()
        print("  Después volvé a correr esto.")
        return SALIDA_DIAGNOSTICO

    perfil = recomendacion.perfil
    assert perfil is not None

    # ⚠️ Se BUSCA en el sistema, no se lee de la configuración. Este comando se
    # corre para armar el `.env`, así que en ese momento el archivo todavía no
    # existe y `config.claude_bin` está vacío aunque Claude Code esté instalado.
    claude = config.claude_bin or diagnostico.encontrar_claude()

    if not claude:
        print("FALTA CLAUDE CODE")
        print("  No se encontró el ejecutable `claude` en esta máquina.")
        print()
        print("  Qué hacer:")
        print("    npm install -g @anthropic-ai/claude-code")
        print()
        print("  Después volvé a correr esto. El resto de los datos ya están")
        print("  resueltos y se imprimen igual, así que podés ir adelantando.")
        print()

    print("PONÉ ESTO EN EL .env")
    print(f"  {CARPETA_AGENTE.parent / '.env'}")
    print()
    print("AGENTE_BACKEND_URL=https://backend-produccion-7yqr.onrender.com")
    if claude:
        print(f"CLAUDE_BIN={claude}")
    else:
        #  Sin valor, y sin nada pegable al lado: una línea con texto suelto
        #  terminaría siendo el valor de la variable.
        print("CLAUDE_BIN=")
        print("   ^ vacío: falta instalar Claude Code (ver arriba)")
    print(f"CHROME_PERFIL_DIR={perfil.nombre}")
    print(f"CHROME_PUERTO={config.chrome_puerto}")

    if perfil.device_id:
        print(f"AGENTE_DEVICE_ID={perfil.device_id}")
    else:
        print("AGENTE_DEVICE_ID=")
        print("   ^ vacío: la extensión está instalada pero nunca se usó en este perfil.")
        print("     Abrí Chrome, usá la extensión una vez, y volvé a correr esto.")

    print("AGENTE_MACHINE_ID=")
    print("   ^ el identificador que pusiste en el panel al dar de alta la máquina")
    print("AGENTE_TOKEN=")
    print("   ^ el que mostró el panel en ese momento. Se muestra UNA sola vez.")
    print()
    print("Las líneas que empiezan con ^ son explicaciones: NO se pegan.")
    print("Y los comentarios de un valor vacío van en la línea de arriba, nunca")
    print("al lado: dotenv toma el '# ...' como si fuera el valor.")
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


def _asegurar_navegador(config: Configuracion):
    """Devuelve cómo asegurarse de que el Chrome del vendedor esté abierto.

    `LISTAR` lee los chats a través de la extensión Claude in Chrome, que vive
    en el navegador de todos los días del vendedor. Si él lo cerró con Cmd+Q,
    la extensión no existe: sin esto, la corrida le paga a un modelo para que
    lo descubra y vuelva con `browser_no_disponible`, tres veces.

    Es otra cosa que el navegador dedicado del motor de envío (D24): ese lo
    abre Playwright con su propia carpeta y no tiene extensión.
    """

    async def asegurar():
        from agente.adaptadores import navegador

        return await navegador.asegurar_abierto(
            chrome_bin=config.chrome_bin,
            perfil_dir=config.chrome_perfil_dir,
        )

    return asegurar


def _abrir_pagina(config: Configuracion):
    """Devuelve cómo conseguir la página de WhatsApp, para el motor de envío.

    Se arma acá y no en el despachador porque es lo único que sabe de esta
    máquina: dónde está Chrome y dónde vive la carpeta del navegador dedicado.

    El motor abre **su propio navegador** (D24): el Chrome del sistema, con una
    carpeta de datos propia y su propia sesión de WhatsApp, vinculada con
    `--vincular`. El Chrome del vendedor no se toca, y no hay ningún puerto.

    Playwright y el navegador se arrancan una vez y quedan vivos mientras viva
    el agente: abrir y cerrar por cada mensaje costaría más que el mensaje. Si
    alguien cierra la ventana, el próximo envío la vuelve a abrir.
    """
    from playwright.async_api import async_playwright

    from agente.adaptadores import conexion
    from agente.adaptadores.whatsapp_web import PaginaWhatsApp

    estado: dict[str, object] = {}

    async def abrir():
        if "playwright" not in estado:
            estado["playwright"] = await async_playwright().start()

        pagina = estado.get("pagina")
        if pagina is None or pagina.is_closed():
            pagina = await conexion.conectar_perfil(
                estado["playwright"],
                carpeta=conexion.carpeta_dedicada(config.navegador_dir),
                chrome_bin=config.chrome_bin,
            )
            estado["pagina"] = pagina
        return PaginaWhatsApp(pagina)

    return abrir


async def _trabajar(config: Configuracion, parar: threading.Event, *, modo: str) -> None:
    """El bucle y el latido, en paralelo, hasta que alguien pida parar."""
    cliente = Cliente(config.backend_url, config.token)

    def diagnosticar():
        return diagnostico.ejecutar(
            claude_bin=config.claude_bin,
            device_id=config.device_id,
            carpeta_agente=CARPETA_AGENTE,
            navegador_dir=config.navegador_dir,
        )

    trabajo = Bucle(
        cliente,
        version=__version__,
        modo=modo,
        diagnosticar=diagnosticar,
        ejecutor=ejecutor.construir(
            claude_bin=config.claude_bin,
            device_id=config.device_id,
            carpeta=CARPETA_AGENTE,
            # El modo RESUELTO, no el de la configuración: `--simulado` tiene que
            # ganarle al entorno, que es para lo único que existe esa opción.
            modo=modo,
            diagnosticar=diagnosticar,
            abrir_pagina=None if modo == "simulado" else _abrir_pagina(config),
            # El Chrome del vendedor, donde vive la extensión que usa `LISTAR`.
            # En simulado no se toca ningún navegador.
            asegurar_navegador=None if modo == "simulado" else _asegurar_navegador(config),
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
