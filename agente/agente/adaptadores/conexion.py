"""De dónde sale la página de Playwright. **F4.2 revisada: D24, 25/8/2026.**

`whatsapp_web.py` recibe una `Page` y no le importa de dónde vino. La decisión
de cómo conseguirla era: CDP sobre el Chrome del vendedor, o un perfil dedicado.

**Gana el perfil dedicado** (`conectar_perfil`). El motor de envío abre su
propio navegador —el Chrome real del sistema, con una carpeta de datos propia—
sólo cuando tiene que escribir, y lo cierra al terminar. El Chrome del vendedor
no se toca.

---

## Por qué no CDP, que era la decisión anterior

F4.2 se había decidido al revés, apoyada en una medición en Chrome 151: pasar
`--user-data-dir` explícito —aunque apuntara al directorio real— hacía que el
puerto de depuración abriera. **Chrome 152 cerró esa puerta**, verificado en la
primera Mac instalada (24/8/2026):

    --remote-debugging-port --user-data-dir=<ruta del perfil real>
    ->  "DevTools remote debugging requires a non-default data directory"

Es Google blindando las cookies del perfil real contra CDP, y va a seguir en
esa dirección. La historia completa, con las opciones, en D24.

## Lo que implica el perfil dedicado

- **Su propia sesión de WhatsApp**, vinculada una vez con `--vincular` (usa
  uno de los cuatro dispositivos que WhatsApp permite). `LISTAR` no cambia:
  sigue por la extensión, en el Chrome del vendedor, con la sesión de él.
- **Sin puerto, sin launchctl, sin "cerrá Chrome del todo"**: es otro proceso
  con otra carpeta, no pelea con la instancia del Dock.
- **Con ventana** (`headless=False`): WhatsApp Web trata distinto a los
  navegadores sin interfaz, y además lo que el sistema hace en la máquina del
  vendedor se tiene que ver.

## ⚠️ Las sesiones de WhatsApp Web expiran

No es una hipótesis: la sesión que usó `LISTAR` el 21 de agosto ya no existía
el 24. Vale para la del vendedor y para la dedicada. Cuando la dedicada se cae,
`ENVIAR` falla cerrado con `sesion_no_iniciada` y se re-vincula con
`--vincular`. Cuánto duran y cómo se entera alguien antes de que falle una
corrida sigue siendo lo que hay que medir.

`conectar_cdp` se conserva por si alguna vez hay un Chrome con puerto contra el
que valga la pena engancharse, pero **no es la opción elegida** y nada del
camino normal lo usa.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from agente.logging import obtener_logger

log = obtener_logger(__name__)

# El puerto por el que Chrome expone su protocolo de depuración. Sólo lo usa
# `conectar_cdp`, que quedó fuera del camino normal (D24).
PUERTO_CDP = 9222


def carpeta_dedicada(configurada: str = "") -> Path:
    """La carpeta de datos del navegador del motor de envío.

    Separada del `User Data` de Chrome a propósito: es lo que hace que el
    puerto no haga falta y que nada de acá roce el perfil del vendedor.
    """
    if configurada:
        return Path(configurada)
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Centonara/Chrome"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Centonara/Chrome"
    return Path.home() / ".config/centonara/chrome"


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


async def conectar_perfil(
    playwright, *, carpeta: Path, chrome_bin: str = "", headless: bool = False
):
    """**La opción elegida (D24).** Un Chrome aparte, con carpeta propia.

    ⚠️ La primera vez pide escanear el QR (`--vincular`), y eso **vincula un
    dispositivo más** a la línea del vendedor: uno de los cuatro que WhatsApp
    permite.

    `headless=False` a propósito. WhatsApp Web detecta y trata distinto a los
    navegadores sin interfaz, y una sesión que se cae en headless se cae sin que
    nadie la vea.

    Usa el **Chrome real del sistema** si está (y en la Mac de un vendedor
    está): WhatsApp ve el navegador de siempre, y no hay que bajar el Chromium
    de Playwright en cada máquina. Sin Chrome instalado cae al de Playwright,
    que es el caso de desarrollo.
    """
    from agente.adaptadores import navegador

    # Una sola vez al arrancar, y bloquea microsegundos: mandarlo a un hilo
    # sería más ruido que beneficio.
    carpeta.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240

    ejecutable = Path(chrome_bin) if chrome_bin else navegador.encontrar_chrome()
    extras = {"executable_path": str(ejecutable)} if ejecutable and ejecutable.exists() else {}
    try:
        contexto = await playwright.chromium.launch_persistent_context(
            str(carpeta), headless=headless, **extras
        )
    except Exception as error:
        # ⚠️ Con `CHROME_BIN` puesto, lo más probable no es que el perfil esté
        # roto: es que esa ruta no sea un navegador. `CLAUDE_BIN` y `CHROME_BIN`
        # se parecen, están a tres líneas en el `.env`, y `--datos` imprime la
        # primera — pegarla en la segunda deja a Playwright lanzando Claude Code
        # con cuarenta banderas de Chrome, y el error que sale de ahí no nombra
        # ni al `.env` ni a la variable. Pasó en la primera instalación Windows.
        if chrome_bin:
            raise NoHayNavegador(
                # Comillas a mano y no `!r`: en Windows el repr duplica las
                # barras de la ruta —C:\\Users\\...— y eso es ilegible justo
                # para quien tiene que ir a corregir esa línea del .env.
                f"CHROME_BIN apunta a '{chrome_bin}' y con eso no se pudo abrir un "
                "navegador. Si esa ruta no es un Chrome, corregila o dejala vacía "
                "en el .env —vacía busca el Chrome del sistema—. Ojo que CLAUDE_BIN "
                "y CHROME_BIN son dos variables distintas."
            ) from error
        raise NoHayNavegador(f"no se pudo abrir el perfil en {carpeta}") from error

    pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()
    log.info(
        "conectado_con_perfil_propio",
        carpeta=str(carpeta),
        chrome=str(ejecutable) if extras else "chromium de playwright",
        headless=headless,
    )
    return pagina
