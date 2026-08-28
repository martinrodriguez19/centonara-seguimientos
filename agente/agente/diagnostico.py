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


def encontrar_claude() -> str | None:
    """La ruta COMPLETA al ejecutable de Claude Code, buscándolo en el sistema.

    Hace falta antes de que exista el `.env`: `--datos` se corre para armarlo, y
    leer `CLAUDE_BIN` de la configuración en ese momento devuelve siempre vacío
    —el archivo todavía no está— aunque Claude Code esté perfectamente instalado.

    Y devuelve el ejecutable **real**, no el shim. `npm install -g` deja un
    `claude` que es un script o un enlace; bajo `launchd` el PATH no es el de la
    terminal y ese shim puede no resolver. Es el problema #2 del MVP, y es el
    mismo criterio que usa el instalador.
    """
    ruta = shutil.which("claude")
    if ruta is None:
        return None

    real = Path(ruta).resolve()

    # En Windows `claude.cmd` no es un enlace: hay que ir a buscar el .exe que
    # npm dejó en node_modules, al lado del shim.
    if real.suffix.lower() in (".cmd", ".ps1", ""):
        candidato = real.parent / "node_modules/@anthropic-ai/claude-code/bin/claude.exe"
        if candidato.exists():
            return str(candidato)

    return str(real)


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
        "se concede a mano en la extensión, para web.whatsapp.com. Lo verifica `--sonda`",
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


def _navegador_envio(carpeta: Path) -> Chequeo:
    """¿El navegador dedicado del motor de envío se vinculó alguna vez?

    Reemplaza al viejo chequeo del puerto de Chrome: desde D24 el motor no se
    engancha a ningún puerto, abre su propio navegador con carpeta propia.

    Sólo mira que la carpeta exista y tenga algo adentro. Si la sesión sigue
    viva se sabe recién al abrirla —igual que `whatsapp_sesion`— y que no
    exista todavía no es una falla: es que falta correr `--vincular`, y el
    primer envío lo va a decir.
    """
    origen = "D24: el motor de envío usa un navegador propio"
    if carpeta.is_dir() and any(carpeta.iterdir()):
        return Chequeo("navegador_envio", Estado.OK, f"vinculado: {carpeta}", origen)
    return Chequeo(
        "navegador_envio",
        Estado.NO_APLICA,
        "sin vincular todavía: correr --vincular antes del primer envío",
        origen,
    )


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

    Acá siempre da `n/a`: verificarlo requiere abrir el navegador dedicado, y
    este módulo es síncrono y barato a propósito. Quien lo verifica de verdad
    es la **vigía** (`vigia_sesion.py`): al arrancar y cada unas horas abre la
    página, pregunta por la sesión, y reemplaza este chequeo con `con_chequeo` —
    el latido lleva ese resultado al panel.

    ⚠️ Importa más de lo que parece: con el perfil dedicado (D24), ésta es una
    **segunda** sesión vinculada a la línea del vendedor, y él no la ve en
    ningún lado. Si se cae, nadie se entera salvo por este chequeo.
    """
    return Chequeo(
        "whatsapp_sesion", Estado.NO_APLICA, "lo revisa la vigía al arrancar y cada unas horas"
    )


def _selectores() -> Chequeo:
    """¿Los selectores de WhatsApp Web siguen respondiendo?

    Corre antes de cada corrida, no una vez por día: si el DOM cambió, todos los
    envíos van a fallar igual y conviene saberlo antes de encolar el primero.

    Acá sólo se reporta **si alguna vez se verificaron contra WhatsApp Web real**.
    Comprobarlo de verdad necesita el navegador abierto y la página cargada, y
    eso lo hace `verificar_selectores()` desde el motor.

    Mientras la fecha sea `None`, un `ENVIAR` en modo real se rechaza. Por eso
    esto es una FALLA y no un `n/a`: es lo único que separa al sistema de poder
    escribir, y tiene que verse en el panel.
    """
    from agente.adaptadores import selectores

    origen = "F4.3"
    if selectores.VERIFICADO is None:
        return Chequeo(
            "selectores",
            Estado.FALLA,
            "nunca se verificaron contra WhatsApp Web: el envío real está bloqueado",
            origen,
        )
    return Chequeo("selectores", Estado.OK, f"verificados el {selectores.VERIFICADO}", origen)


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


def con_chequeo(diagnostico: Diagnostico, chequeo: Chequeo) -> Diagnostico:
    """Un diagnóstico con un chequeo reemplazado por su versión más fresca.

    Lo usa la vigía de la sesión dedicada: el diagnóstico completo es caro de
    correr y casi todo no cambia; lo único que ella averiguó de nuevo es un
    chequeo. Si el nombre no estaba —un diagnóstico vacío de arranque—, se
    agrega en vez de perderse.
    """
    if any(c.nombre == chequeo.nombre for c in diagnostico.chequeos):
        chequeos = tuple(chequeo if c.nombre == chequeo.nombre else c for c in diagnostico.chequeos)
    else:
        chequeos = (*diagnostico.chequeos, chequeo)
    return Diagnostico(chequeos)


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
    navegador_dir: str = "",
) -> Diagnostico:
    """Corre los diez chequeos.

    `con_navegador=False` saltea el que lanza un proceso —`claude --version`—:
    lo usan los tests, y sirve para un arranque rápido porque tarda.
    """
    from agente.adaptadores import conexion

    hogar = inicio or Path(os.path.expanduser("~"))

    chequeos = [
        _claude_bin(claude_bin),
        _permiso_mcp(hogar),
        _permiso_sitio(),
        _device_id(device_id),
        _chrome(claude_bin) if con_navegador else Chequeo("chrome", Estado.NO_APLICA, "salteado"),
        _navegador_envio(conexion.carpeta_dedicada(navegador_dir)),
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
