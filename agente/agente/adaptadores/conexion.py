"""De dónde sale la página de Playwright. **F4.2 — decidida el 24/8/2026.**

`whatsapp_web.py` recibe una `Page` y no le importa de dónde vino. La decisión de
cómo conseguirla estaba abierta, y se resolvió sola: **una de las dos opciones no
es posible.**

---

## ⚠️ La opción A está descartada: Chrome no la permite

El plan era enganchar Playwright por CDP al Chrome que el vendedor ya tiene
abierto, reusando su sesión de WhatsApp. Eso **no funciona desde Chrome 136**:
Google ignora `--remote-debugging-port` cuando se usa el **perfil por defecto**,
como medida de seguridad para que un malware no pueda leer cookies por CDP.

Medido en Chrome 151, el 24 de agosto de 2026:

    perfil por defecto     + --remote-debugging-port=9222  ->  el puerto NO escucha
    --user-data-dir aparte + --remote-debugging-port=9223  ->  el puerto ESCUCHA

No es un problema de configuración ni de permisos: Chrome arranca, acepta el
flag sin quejarse, y simplemente no abre el puerto. Que falle en silencio es lo
que lo hace difícil de diagnosticar.

Y es una decisión de Chrome, no del sistema operativo: **pasa igual en macOS**.
Este era el único punto de F4.2 que necesitaba una Mac para decidirse, y ya no.

## Entonces queda la opción B — perfil dedicado

Un Chrome aparte, con su propio perfil, vinculado a WhatsApp una vez.

Cualquier camino con CDP necesita `--user-data-dir` distinto del por defecto, y
un perfil distinto **no tiene la sesión de WhatsApp del vendedor**: hay que
vincularlo. Así que "CDP con otro perfil" y "perfil dedicado de Playwright" son
la misma cosa con distinto nombre. `conectar_cdp` se conserva porque sirve para
engancharse a un Chrome ya vinculado, no para reusar el del vendedor.

⚠️ **Lo que eso cuesta, y hay que decirlo:** es un **segundo dispositivo
vinculado** a la línea del vendedor. Ocupa uno de los cuatro que WhatsApp
permite, y es una sesión más que se puede caer sin que nadie la vea hasta que
una corrida falla. No hay forma de evitarlo: la alternativa la cerró Chrome.

## Lo que sigue faltando medir, y sí necesita la Mac

Ya no *cuál* de las dos, sino cómo se comporta la que quedó:

1. Si el vendedor **reinicia la máquina**, ¿sigue vinculada sin que nadie toque nada?
2. ¿Sobrevive **media jornada** de uso normal?
3. Si la sesión se cae, ¿cuánto tarda alguien en enterarse?

La tercera es la que más importa, porque es la que no tiene dueño.
"""

from __future__ import annotations

from pathlib import Path

from agente.logging import obtener_logger

log = obtener_logger(__name__)

# El puerto por el que Chrome expone su protocolo de depuración. Es el que hay
# que pasarle con `--remote-debugging-port` al arrancarlo.
PUERTO_CDP = 9222


class NoHayNavegador(Exception):
    """No se pudo llegar a un navegador utilizable.

    Se distingue de un error de selector: acá no es que WhatsApp cambió, es que
    no hay dónde mirar. El agente lo reporta y no escribe nada.
    """


async def conectar_cdp(playwright, *, puerto: int = PUERTO_CDP):
    """**Opción A.** Se engancha al Chrome que el vendedor ya tiene abierto.

    Devuelve la primera pestaña utilizable del contexto existente. No abre una
    nueva si ya hay uma: reusar la que está evita dejarle pestañas al vendedor.
    """
    try:
        navegador = await playwright.chromium.connect_over_cdp(f"http://localhost:{puerto}")
    except Exception as error:
        raise NoHayNavegador(
            f"no hay un Chrome escuchando en el puerto {puerto}. "
            "Tiene que estar arrancado con --remote-debugging-port"
        ) from error

    if not navegador.contexts:
        raise NoHayNavegador("el Chrome respondió pero no tiene ningún contexto abierto")

    contexto = navegador.contexts[0]
    paginas = [p for p in contexto.pages if not p.is_closed()]
    pagina = paginas[0] if paginas else await contexto.new_page()

    log.info("conectado_por_cdp", puerto=puerto, pestanias=len(paginas))
    return pagina


async def conectar_perfil(playwright, *, carpeta: Path, headless: bool = False):
    """**Opción B.** Un Chrome aparte, con perfil propio.

    ⚠️ La primera vez pide escanear el QR, y eso **vincula un dispositivo más** a
    la línea del vendedor: uno de los cuatro que WhatsApp permite.

    `headless=False` a propósito. WhatsApp Web detecta y trata distinto a los
    navegadores sin interfaz, y una sesión que se cae en headless se cae sin que
    nadie la vea.
    """
    # Una sola vez al arrancar, y bloquea microsegundos: mandarlo a un hilo
    # sería más ruido que beneficio.
    carpeta.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    try:
        contexto = await playwright.chromium.launch_persistent_context(
            str(carpeta), headless=headless
        )
    except Exception as error:
        raise NoHayNavegador(f"no se pudo abrir el perfil en {carpeta}") from error

    pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()
    log.info("conectado_con_perfil_propio", carpeta=str(carpeta), headless=headless)
    return pagina
