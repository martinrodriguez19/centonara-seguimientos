"""Los nueve chequeos que el agente corre sobre su propia máquina.

Siete vienen del historial del MVP: son problemas que **ya ocurrieron** y que
van a volver a ocurrir en cada instalación nueva. Dos son nuevos.

La gracia no es que existan los chequeos: es que el panel pueda decir *qué*
falta. En el MVP, los siete se manifestaban como un HTTP 502 mudo y había que
adivinar cuál de los siete era.

Cada chequeo devuelve `ok`, `falla` o `n/a`. **`n/a` no es una falla**: es "esto
no aplica en esta máquina". Los chequeos de navegador dan `n/a` mientras se
desarrolla en Windows sin sesión de WhatsApp, y el de permisos de macOS da `n/a`
fuera de macOS. Un agente con `n/a` puede trabajar; uno con `falla`, no.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from agente.logging import obtener_logger

log = obtener_logger(__name__)

PERMISO_MCP = "mcp__claude-in-chrome"


class Estado(StrEnum):
    OK = "ok"
    FALLA = "falla"
    NO_APLICA = "n/a"


@dataclass(frozen=True)
class Chequeo:
    nombre: str
    estado: Estado
    detalle: str = ""
    #  De qué problema del MVP viene. Va al panel: "falta el permiso de sitio de
    #  la extensión" es accionable; "error de configuración" no.
    origen: str = ""


@dataclass(frozen=True)
class Diagnostico:
    chequeos: tuple[Chequeo, ...] = field(default_factory=tuple)

    @property
    def fallas(self) -> tuple[Chequeo, ...]:
        return tuple(c for c in self.chequeos if c.estado is Estado.FALLA)

    @property
    def puede_enviar(self) -> bool:
        """Con cualquier chequeo en falla, el agente no toma jobs de envío.

        No es lo mismo que "no toma ningún job": un agente degradado igual puede
        correr un diagnóstico y reportarlo, que es justamente lo que hace falta
        para arreglarlo desde el panel.
        """
        return not self.fallas

    def a_dict(self) -> dict[str, str]:
        """Lo que viaja al backend y termina en el panel."""
        return {c.nombre: str(c.estado) for c in self.chequeos}

    def resumen(self) -> str:
        if self.puede_enviar:
            return "todo en orden"
        return "; ".join(f"{c.nombre}: {c.detalle or 'falla'}" for c in self.fallas)


# ---------------------------------------------------------------------------
# Los chequeos, uno por uno
# ---------------------------------------------------------------------------


def _claude_bin(ruta: str) -> Chequeo:
    """Problema #2 del MVP: `shutil.which("claude")` devolvía `None`.

    Pasaba porque el PATH del proceso que lanza el agente no es el de la
    terminal donde alguien probó que funcionaba. Por eso la configuración pide
    la ruta COMPLETA y esto la verifica.
    """
    origen = "MVP #2"
    if not ruta:
        return Chequeo(
            "claude_bin",
            Estado.FALLA,
            "CLAUDE_BIN está vacío: hace falta la ruta completa al ejecutable",
            origen,
        )
    if not Path(ruta).exists() and shutil.which(ruta) is None:
        return Chequeo("claude_bin", Estado.FALLA, f"no existe: {ruta}", origen)
    return Chequeo("claude_bin", Estado.OK, ruta, origen)


def _permiso_mcp(inicio: Path) -> Chequeo:
    """Problema #3 del MVP: en modo headless, Claude Code auto-deniega todo.

    Sin `mcp__claude-in-chrome` en la lista de permitidos, el job falla con un
    502 que no dice nada.
    """
    origen = "MVP #3"
    archivo = inicio / ".claude" / "settings.json"
    if not archivo.exists():
        return Chequeo("permiso_mcp", Estado.FALLA, f"falta {archivo}", origen)

    try:
        contenido = json.loads(archivo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        return Chequeo("permiso_mcp", Estado.FALLA, f"{archivo} ilegible: {error}", origen)

    permitidos = contenido.get("permissions", {}).get("allow", [])
    if not any(PERMISO_MCP in str(p) for p in permitidos):
        return Chequeo(
            "permiso_mcp", Estado.FALLA, f"falta '{PERMISO_MCP}' en permissions.allow", origen
        )
    return Chequeo("permiso_mcp", Estado.OK, str(archivo), origen)


def _permiso_sitio() -> Chequeo:
    """Problema #4 del MVP, y el más traicionero de los siete.

    Es una capa **distinta** del permiso MCP: aunque `settings.json` esté bien,
    la extensión necesita permiso de sitio para `web.whatsapp.com`, y eso se
    concede a mano en el navegador, una vez por máquina.

    No hay forma de leerlo desde afuera del navegador, así que esto siempre da
    `n/a`: lo que lo detecta de verdad es que `LISTAR` falle con "requires
    permission". Queda declarado igual para que el panel lo liste y alguien se
    acuerde de que existe — es exactamente el que se olvida.
    """
    return Chequeo(
        "permiso_sitio",
        Estado.NO_APLICA,
        "se concede a mano en la extensión, para web.whatsapp.com. No se puede verificar desde acá",
        "MVP #4",
    )


def _device_id(valor: str) -> Chequeo:
    """Problema #5 del MVP: "hay dos navegadores conectados".

    Con más de un Chrome asociado a la cuenta, headless no sabe a cuál
    conectarse y la corrida falla. El `deviceId` de esta máquina lo desambigua.
    """
    origen = "MVP #5"
    if not valor:
        return Chequeo(
            "device_id",
            Estado.FALLA,
            "sin deviceId: con más de un Chrome conectado, no sabe a cuál ir",
            origen,
        )
    return Chequeo("device_id", Estado.OK, valor, origen)


def _claude_md(carpeta: Path) -> Chequeo:
    """Problema #7 del MVP: el modelo se negaba a ejecutar sin contexto verificable.

    La solución NO fue autorizarlo en el prompt —eso empeoró el problema, porque
    es el patrón exacto de una inyección— sino poner el contexto real en un
    `CLAUDE.md` escrito por el dueño de la máquina, fuera del pedido.
    """
    origen = "MVP #7"
    archivo = carpeta / "prompts" / "CLAUDE.md"
    if not archivo.exists():
        return Chequeo("claude_md", Estado.FALLA, f"falta {archivo}", origen)
    return Chequeo("claude_md", Estado.OK, str(archivo), origen)


def _chrome(ruta_claude: str) -> Chequeo:
    """¿Claude Code responde? Es lo más cerca que se puede estar sin abrir el navegador.

    Se corre `--version` y no algo más ambicioso: el objetivo es distinguir "el
    ejecutable está y anda" de "el ejecutable está y explota", sin abrir una
    pestaña ni gastar tokens.
    """
    if not ruta_claude:
        return Chequeo("chrome", Estado.NO_APLICA, "sin CLAUDE_BIN configurado")
    try:
        proceso = subprocess.run(
            [ruta_claude, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return Chequeo("chrome", Estado.FALLA, f"no se pudo ejecutar: {error}")

    if proceso.returncode != 0:
        return Chequeo("chrome", Estado.FALLA, (proceso.stderr or "").strip()[:200])
    return Chequeo("chrome", Estado.OK, (proceso.stdout or "").strip()[:80])


def _whatsapp_sesion() -> Chequeo:
    """Si WhatsApp Web pide QR, no se puede leer ni enviar nada.

    Verificarlo requiere abrir el navegador, que es trabajo de la fase 3. Hasta
    entonces, `n/a`.

    ⚠️ Cuando exista, importa más de lo que parece: con la opción de perfil
    dedicado de Playwright, ésta es una **segunda** sesión vinculada a la línea
    del vendedor, y él no la ve en ningún lado. Si se cae, nadie se entera salvo
    por este chequeo.
    """
    return Chequeo("whatsapp_sesion", Estado.NO_APLICA, "necesita el navegador: llega en la fase 3")


def _selectores() -> Chequeo:
    """¿Los selectores de WhatsApp Web siguen respondiendo?

    Corre antes de cada corrida, no una vez por día: si el DOM cambió, todos los
    envíos van a fallar igual y conviene saberlo antes de encolar el primero.

    Llega con el motor de envío, en la fase 4.
    """
    return Chequeo("selectores", Estado.NO_APLICA, "necesita el motor de envío: llega en la fase 4")


def _permisos_macos() -> Chequeo:
    """Automatización, en Ajustes del Sistema > Privacidad y seguridad.

    No está en el historial del MVP porque el MVP era Windows. Es la lista que
    nadie tiene todavía y que se completa en F5.1, la primera vez que el agente
    corra en una Mac.
    """
    if platform.system() != "Darwin":
        return Chequeo("permisos_macos", Estado.NO_APLICA, f"no es macOS ({platform.system()})")
    return Chequeo(
        "permisos_macos",
        Estado.NO_APLICA,
        "por implementar en F5.1, con la primera Mac",
    )


# ---------------------------------------------------------------------------
# Ejecutar todo
# ---------------------------------------------------------------------------


def ejecutar(
    *,
    claude_bin: str,
    device_id: str,
    carpeta_agente: Path,
    inicio: Path | None = None,
    con_navegador: bool = True,
) -> Diagnostico:
    """Corre los nueve chequeos.

    `con_navegador=False` saltea el que lanza un proceso: lo usan los tests y
    sirve para un arranque rápido, porque `claude --version` tarda.
    """
    hogar = inicio or Path(os.path.expanduser("~"))

    chequeos = [
        _claude_bin(claude_bin),
        _permiso_mcp(hogar),
        _permiso_sitio(),
        _device_id(device_id),
        _chrome(claude_bin) if con_navegador else Chequeo("chrome", Estado.NO_APLICA, "salteado"),
        _whatsapp_sesion(),
        _claude_md(carpeta_agente),
        _permisos_macos(),
        _selectores(),
    ]

    diagnostico = Diagnostico(tuple(chequeos))
    if diagnostico.fallas:
        log.warning("diagnostico_degradado", resumen=diagnostico.resumen())
    else:
        log.info("diagnostico_ok", chequeos=len(chequeos))
    return diagnostico
