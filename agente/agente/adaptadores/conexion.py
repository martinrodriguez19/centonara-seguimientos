"""De dónde sale la página de Playwright. **F4.2 — decidida el 24/8/2026.**

`whatsapp_web.py` recibe una `Page` y no le importa de dónde vino. La decisión de
cómo conseguirla era: CDP sobre el Chrome del vendedor, o un perfil dedicado.

**Gana CDP sobre el Chrome del vendedor**, y con eso el sistema usa una sola
sesión de WhatsApp y un solo dispositivo vinculado.

---

## Lo que Chrome bloquea, y lo que no

Desde Chrome 136, `--remote-debugging-port` **se ignora cuando el perfil es el
por defecto implícito** — o sea, cuando no se pasa `--user-data-dir`. Es una
medida de seguridad para que un malware no lea cookies por CDP, y **falla en
silencio**: Chrome arranca, acepta el flag, y no abre el puerto.

Pero **basta con pasar la ruta explícita**, incluso la del mismo perfil real.
Medido en Chrome 151 el 24 de agosto de 2026:

    --remote-debugging-port                              ->  el puerto NO escucha
    --remote-debugging-port --user-data-dir=<ruta real>  ->  el puerto ESCUCHA

Con eso Playwright se engancha al Chrome del vendedor, con su perfil, su sesión
de WhatsApp y su extensión. No hace falta un segundo dispositivo vinculado.

## Cómo hay que arrancar Chrome

Los tres flags, y ninguno es opcional:

    --remote-debugging-port=9222
    --user-data-dir="<carpeta User Data del vendedor>"
    --profile-directory="<el perfil que usa>"

El tercero importa más de lo que parece: sin él Chrome abre el perfil `Default`,
que en una máquina con varios perfiles **no es el que tiene nada**.

## ⚠️ Un solo perfil tiene que tener las dos cosas

`LISTAR` usa la extensión Claude in Chrome. `ENVIAR` usa esta conexión. Las dos
tienen que dar contra **el mismo perfil**, y ese perfil tiene que tener:

1. La extensión instalada
2. La sesión de WhatsApp Web iniciada

En la máquina donde se probó esto **estaban en perfiles distintos** —la
extensión en uno, la sesión en otro— y ninguna de las dos partes habría
funcionado. Es lo primero que hay que verificar al instalar, y está en el SOP.

## ⚠️ La sesión de WhatsApp Web expira

No es una hipótesis: la sesión que usó `LISTAR` el 21 de agosto ya no existía el
24. La página de vinculación tiene un `auto-logout` visible.

Cuando se cae, **el sistema entero se detiene**: `LISTAR` no puede leer y
`ENVIAR` no puede escribir. Falla cerrado, que es lo correcto, pero nadie se
entera hasta que una corrida falla. Ese es el riesgo operativo que queda abierto,
y es lo que hay que medir en la Mac: cuánto dura, y cómo se entera alguien.

`conectar_perfil` se conserva para el caso en que haya que aislar el navegador
del vendedor, pero **no es la opción elegida**: ese camino sí vincula un
dispositivo más.
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
