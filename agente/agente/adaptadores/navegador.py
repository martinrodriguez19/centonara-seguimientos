"""Que Chrome esté abierto y accesible, sin que el vendedor haga nada.

El vendedor prende la Mac y no toca nada más. El agente arranca solo con el
LaunchAgent, y cuando llega trabajo tiene que encontrar un Chrome **abierto y con
el puerto de depuración habilitado**. Si no lo encuentra, lo abre él.

---

## Los tres flags, y por qué ninguno sobra

    --remote-debugging-port=9222
    --user-data-dir="<carpeta User Data>"
    --profile-directory="<el perfil que usa el vendedor>"

**`--user-data-dir` no es opcional aunque apunte al perfil de siempre.** Desde
Chrome 136, el puerto de depuración se ignora cuando el perfil es el por defecto
*implícito*. Con la ruta explícita —la misma ruta— funciona. Y falla en
silencio: Chrome arranca, acepta el flag, y no abre el puerto.

**`--profile-directory` tampoco.** Sin él Chrome abre `Default`, que en una
máquina con varios perfiles no es el que tiene la extensión ni la sesión de
WhatsApp.

## El caso incómodo: Chrome ya abierto, pero sin el puerto

Pasa cuando el vendedor abrió Chrome desde el Dock. Lanzar otra instancia **no
sirve**: Chrome le pide a la que ya existe que abra una ventana, y el puerto
sigue cerrado.

La salida fácil sería cerrarle el navegador. **No se hace**: es la máquina de
alguien que está trabajando, y cerrarle las pestañas para mandar un mensaje
comercial es exactamente el tipo de cosa que hace que una herramienta se
desinstale.

Se reporta con un código propio y la corrida se frena. La solución de fondo es
que Chrome arranque con los flags **al iniciar sesión**, y de eso se encarga el
instalador: así el que abre el vendedor desde el Dock se engancha al que ya
está, con el puerto puesto.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from agente.logging import obtener_logger

log = obtener_logger(__name__)

PUERTO_POR_DEFECTO = 9222

# Cuánto se espera a que Chrome levante el puerto después de lanzarlo. Un Chrome
# frío con muchas pestañas restauradas tarda.
ESPERA_ARRANQUE_S = 20.0


def rutas_probables() -> tuple[Path, ...]:
    """Dónde suele estar el ejecutable, por sistema."""
    if sys.platform == "darwin":
        return (
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
    if sys.platform == "win32":
        base = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        base86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        return tuple(
            Path(p) / "Google/Chrome/Application/chrome.exe" for p in (base, base86, local) if p
        )
    return (Path("/usr/bin/google-chrome"), Path("/usr/bin/chromium"))


def perfil_por_defecto() -> Path:
    """La carpeta `User Data` del sistema."""
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Google/Chrome"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"
    return Path.home() / ".config/google-chrome"


def encontrar_chrome() -> Path | None:
    for ruta in rutas_probables():
        if ruta.exists():
            return ruta
    return None


class Estado(StrEnum):
    YA_ESTABA = "ya_estaba"
    """El puerto ya escuchaba. Es el caso normal si Chrome arranca al iniciar sesión."""

    ABIERTO = "abierto"
    """Lo abrimos nosotros."""

    SIN_PUERTO = "sin_puerto"
    """Chrome está abierto pero sin el puerto. No se le cierra al vendedor."""

    NO_SE_PUDO = "no_se_pudo"
    """No hay ejecutable, o no levantó."""


@dataclass(frozen=True)
class Resultado:
    estado: Estado
    detalle: str = ""

    @property
    def utilizable(self) -> bool:
        return self.estado in (Estado.YA_ESTABA, Estado.ABIERTO)


async def puerto_escucha(
    puerto: int,
    *,
    # No es un `await` largo que convenga cancelar desde afuera: es un
    # intento de conexion que o entra o no. `asyncio.timeout` alrededor
    # dejaria el socket a medio abrir.
    timeout: float = 1.5,  # noqa: ASYNC109
) -> bool:
    """¿Hay algo escuchando en `localhost:puerto`?"""
    try:
        lector, escritor = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", puerto), timeout=timeout
        )
    except (OSError, TimeoutError):
        return False
    escritor.close()
    #  Un cierre sucio no cambia la respuesta: ya sabemos que habia algo.
    with contextlib.suppress(OSError):
        await escritor.wait_closed()
    del lector
    return True


def puerto_escucha_sync(puerto: int, *, timeout: float = 1.0) -> bool:
    """Lo mismo, sin bucle de eventos.

    El diagnóstico es sincrónico —lo corre `--diagnostico` y también el bucle
    antes de registrarse— y meterle un `asyncio.run` adentro sería peor que
    duplicar cuatro líneas de socket.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def _chrome_corriendo() -> bool:
    """¿Hay algún proceso de Chrome? Sin depender de librerías extra."""
    try:
        if sys.platform == "win32":
            salida = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return "chrome.exe" in salida.stdout
        salida = subprocess.run(
            ["pgrep", "-x", "Google Chrome" if sys.platform == "darwin" else "chrome"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return salida.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _lanzar(comando: list[str]) -> None:
    """Chrome, suelto del agente.

    `start_new_session` para que no muera cuando el agente se reinicie: el
    navegador es del vendedor, no nuestro. Y la salida al vacío, porque un
    Chrome que llena el log del agente con sus advertencias lo hace ilegible.
    """
    subprocess.Popen(
        comando,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


async def asegurar_chrome(
    *,
    chrome_bin: str = "",
    perfil: str = "",
    perfil_dir: str = "Default",
    puerto: int = PUERTO_POR_DEFECTO,
    espera_s: float = ESPERA_ARRANQUE_S,
    lanzar=_lanzar,
) -> Resultado:
    """Deja Chrome abierto y con el puerto, o explica por qué no pudo."""
    if await puerto_escucha(puerto):
        return Resultado(Estado.YA_ESTABA, f"el puerto {puerto} ya escuchaba")

    if _chrome_corriendo():
        # ⚠️ No se le cierra el navegador a nadie. Ver la cabecera del módulo.
        log.error("chrome_abierto_sin_puerto", puerto=puerto)
        return Resultado(
            Estado.SIN_PUERTO,
            (
                f"Chrome está abierto pero sin el puerto {puerto}. Lanzar otra "
                "instancia no lo habilita. Hay que cerrarlo y volver a abrirlo con "
                "los flags, o dejar que arranque así al iniciar sesión."
            ),
        )

    ejecutable = Path(chrome_bin) if chrome_bin else encontrar_chrome()
    if ejecutable is None or not ejecutable.exists():
        return Resultado(
            Estado.NO_SE_PUDO,
            f"no se encontró el ejecutable de Chrome{f': {chrome_bin}' if chrome_bin else ''}",
        )

    carpeta = Path(perfil) if perfil else perfil_por_defecto()
    comando = [
        str(ejecutable),
        f"--remote-debugging-port={puerto}",
        f"--user-data-dir={carpeta}",
        f"--profile-directory={perfil_dir}",
    ]

    log.info("abriendo_chrome", perfil=str(carpeta), perfil_dir=perfil_dir, puerto=puerto)
    try:
        lanzar(comando)
    except (OSError, subprocess.SubprocessError) as error:
        return Resultado(Estado.NO_SE_PUDO, f"no se pudo lanzar Chrome: {error}")

    # Se espera al puerto y no al proceso: que Chrome esté vivo no significa que
    # haya abierto el puerto — que es exactamente el modo de falla de la 136.
    limite = asyncio.get_running_loop().time() + espera_s
    while asyncio.get_running_loop().time() < limite:
        if await puerto_escucha(puerto):
            return Resultado(Estado.ABIERTO, f"Chrome abierto, puerto {puerto}")
        await asyncio.sleep(0.5)

    return Resultado(
        Estado.NO_SE_PUDO,
        (
            f"Chrome se lanzó pero el puerto {puerto} no abrió en {espera_s:.0f}s. "
            "Suele ser que ya había una instancia corriendo, o que falta "
            "--user-data-dir con la ruta explícita."
        ),
    )
