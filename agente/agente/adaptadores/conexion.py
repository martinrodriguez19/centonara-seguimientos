"""De dónde sale la página de Playwright. **F4.2, y sigue sin decidirse.**

`whatsapp_web.py` recibe una `Page` y no le importa de dónde vino. Esa costura
está a propósito: la decisión de cómo conectarse al navegador es la única parte
del envío que depende del sistema operativo, y hay que tomarla **con evidencia**
—no con un argumento— midiendo en una Mac de verdad.

Están las dos opciones implementadas para poder medirlas. Ninguna es la elegida.

---

## Opción A — CDP sobre el Chrome del vendedor

Playwright se engancha al Chrome que el vendedor ya tiene abierto, con la sesión
de WhatsApp que ya usa.

- **A favor:** una sola sesión de WhatsApp. No ocupa un dispositivo vinculado, no
  hay una segunda sesión que se caiga sin que nadie la vea, y es el mismo Chrome
  donde vive la extensión que usa `LISTAR`.
- **En contra:** Chrome tiene que estar arrancado con `--remote-debugging-port`.
  Si el vendedor lo abre desde el Dock, no lo está. Eso hay que resolverlo en el
  arranque, y es distinto en cada sistema.
- **Y algo que hay que mirar de cerca:** Playwright comparte el navegador con una
  persona que lo está usando. Si el vendedor cambia de pestaña o escribe en el
  mismo chat mientras el agente opera, hay que saber qué pasa.

## Opción B — Perfil dedicado de Playwright

Un Chrome aparte, con su propio perfil, que se vincula a WhatsApp una vez.

- **A favor:** nadie lo toca. El vendedor trabaja en su navegador y el agente en
  el suyo.
- **En contra, y no es menor:** ⚠️ **es un segundo dispositivo vinculado a esa
  línea.** Ocupa uno de los cuatro que WhatsApp permite, y es una sesión más que
  se puede caer sin que nadie la vea hasta que una corrida falla.

## Qué hay que medir, y en una Mac

1. Si el vendedor **cierra el navegador**, ¿se pierde la sesión?
2. Si **reinicia la máquina**, ¿sigue andando sin que nadie toque nada?
3. Si está **escribiendo en el mismo chat** cuando el agente entra, ¿qué pasa?
4. ¿Sobrevive **media jornada** de uso normal?

El criterio no es cuál es más elegante: es cuál sigue funcionando después de eso.
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
