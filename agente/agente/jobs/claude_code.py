"""Cómo se invoca a Claude Code, y cómo se le lee la respuesta.

Está separado de `listar` y `redactar` porque la invocación es la parte que ya
está validada contra la realidad —cuatro de los siete problemas del MVP viven
acá— y los dos jobs sólo se diferencian en el prompt y en si abren el navegador.

Los cuatro detalles de la llamada, cada uno con su cicatriz (`docs/04-AGENTE.md`
§4 y §5):

- **El prompt va por stdin, nunca como argumento.** En Windows `claude.CMD`
  pasa por `cmd.exe`, que corta el comando en el primer salto de línea y deja
  llegar un prompt mutilado. En macOS no pasa, y se hace igual: es lo correcto y
  el código es compartido.
- **`encoding="utf-8"` explícito.** Si no, Windows decodifica con `cp1252` y
  rompe los acentos. macOS ya es UTF-8, y se fija igual, por lo mismo.
- **`cwd` en la carpeta del agente**, para que Claude Code encuentre el
  `CLAUDE.md` que da el contexto de la máquina (problema #7).
- **La ruta completa al ejecutable**, que la trae la configuración. `which` no
  alcanza: el PATH de launchd no es el de la terminal donde alguien probó que
  funcionaba (problema #2).

Y uno que no es de la llamada sino de la respuesta: **una salida que no parsea
es un fallo con el `raw` completo, no una excepción.** El prompt es lo que más
se va a tocar, y sin el crudo no hay forma de saber qué contestó el modelo.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agente.logging import obtener_logger

log = obtener_logger(__name__)

# Diez minutos, como el MVP. Una lectura de veinte chats con el navegador de por
# medio tarda minutos, no segundos.
TIMEOUT = 600.0

# `LISTAR` necesita más, y el barrido del historial (D27) mucho más: scrollear
# hasta el fondo de un WhatsApp con años de chats y después abrir cada uno para
# ver de qué se hablaba no entra en diez minutos. Se midió en la primera Mac:
# tres timeouts seguidos a los 600 s, con el modelo todavía trabajando.
#
# ⚠️ Este número tiene un techo: `cola.SEGUNDOS_PARA_DAR_POR_COLGADO` en el
# backend (40 min). Si lo pasara, el backend devolvería el job a la cola
# mientras el agente sigue en eso, y el trabajo se pagaría dos veces.
TIMEOUT_LISTAR = 25 * 60.0


@dataclass(frozen=True)
class Salida:
    """Lo que devolvió el proceso, sin interpretar."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class Invocacion:
    """El resultado de pedirle algo a Claude Code.

    `datos` es el JSON que devolvió el modelo, ya desenvuelto. Es `None` siempre
    que `ok` sea `False`, y el motivo está en `codigo`.
    """

    ok: bool
    datos: dict[str, Any] | None = None
    codigo: str | None = None
    detalle: dict[str, Any] = field(default_factory=dict)
    # Se reportan siempre, también en éxito (R5).
    raw: str = ""
    stderr: str = ""
    costo_usd: float = 0.0


def rellenar(plantilla: Path, variables: dict[str, str]) -> str:
    """Sustituye `{{VARIABLE}}` en un prompt que vive en disco.

    **El prompt nunca viaja por la red.** El backend manda variables acotadas y
    validadas contra un esquema (`app/modelos/jobs.py`), y acá se rellena un
    archivo que está en la máquina del vendedor. Un backend comprometido no
    puede hacer que el agente ejecute texto arbitrario.

    Sustituye en una sola pasada sobre la plantilla: un valor que contenga
    `{{OTRA_COSA}}` no se vuelve a expandir.
    """
    texto = plantilla.read_text(encoding="utf-8")
    for nombre, valor in variables.items():
        texto = texto.replace("{{" + nombre + "}}", valor)
    return texto


def _correr(comando: list[str], prompt: str, *, timeout: float, cwd: Path) -> Salida:
    """La llamada de verdad. Se inyecta en los tests para no lanzar procesos."""
    proceso = subprocess.run(
        comando,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(cwd),
        check=False,
    )
    return Salida(proceso.returncode, proceso.stdout or "", proceso.stderr or "")


Correr = Callable[..., Salida]


async def invocar(
    prompt: str,
    *,
    claude_bin: str,
    carpeta: Path,
    con_navegador: bool,
    # ASYNC109 sugiere `asyncio.timeout` en vez de un parametro. Aca seria peor:
    # `to_thread` no se puede cancelar, asi que el await se cortaria y el proceso
    # `claude` quedaria corriendo suelto. El `timeout` de `subprocess.run` si lo
    # mata, que es lo que hace falta.
    timeout: float = TIMEOUT,  # noqa: ASYNC109
    correr: Correr | None = None,
) -> Invocacion:
    """Le pasa el prompt a Claude Code y devuelve el JSON que contestó.

    `con_navegador=False` **omite `--chrome`**, y no es un detalle de
    configuración: es donde está el ahorro del proyecto. `REDACTAR` es el job
    más frecuente —uno por chat— y sacarlo del circuito del navegador es lo que
    hace viable el costo por mensaje.
    """
    if not claude_bin:
        return Invocacion(
            False, codigo="ERROR_INESPERADO", detalle={"motivo": "CLAUDE_BIN sin configurar"}
        )

    comando = [claude_bin, "-p", "--output-format", "json"]
    if con_navegador:
        comando.insert(2, "--chrome")

    hacer = correr or _correr
    try:
        # A un hilo: `subprocess.run` bloquea, y el bucle tiene que poder seguir
        # latiendo mientras un LISTAR tarda sus minutos.
        salida = await asyncio.to_thread(hacer, comando, prompt, timeout=timeout, cwd=carpeta)
    except subprocess.TimeoutExpired:
        log.error("claude_timeout", segundos=timeout, con_navegador=con_navegador)
        return Invocacion(False, codigo="TIMEOUT", detalle={"segundos": timeout})
    except (OSError, ValueError) as error:
        # No se pudo lanzar el proceso: la ruta no existe, no es ejecutable.
        log.error("claude_no_arranca", error=str(error), bin=claude_bin)
        return Invocacion(
            False,
            codigo="ERROR_INESPERADO",
            detalle={"motivo": "no se pudo ejecutar", "error": str(error)[:300]},
        )

    return _leer(salida, con_navegador=con_navegador)


def _leer(salida: Salida, *, con_navegador: bool) -> Invocacion:
    crudo = salida.stdout.strip()

    if salida.returncode != 0:
        # Lo que claude tenía para decir suele salir por stdout —con
        # `--output-format json` el error viaja en el sobre— y stderr queda
        # vacío. Sin mostrarlo, "código distinto de cero" es un callejón sin
        # salida: pasó, instalando la primera Mac.
        dijo = (salida.stderr.strip() or crudo)[-300:] or "sin salida"
        # El fallo con nombre propio: el token OAuth de Claude Code vence cada
        # tanto, y un 401 crudo no le dice a nadie qué hacer. Pasó en la
        # primera Mac, con todo lo demás en verde.
        if "OAuth access token has expired" in crudo or '"api_error_status":401' in crudo:
            motivo = (
                "la sesión de Claude Code venció: correr `claude`, iniciar "
                "sesión de nuevo, salir con /exit y volver a intentar"
            )
        else:
            motivo = f"claude devolvió {salida.returncode} y dijo: {dijo}"
        log.error(
            "claude_salio_mal",
            returncode=salida.returncode,
            stderr=salida.stderr[-500:],
            stdout=crudo[-500:],
        )
        return Invocacion(
            False,
            codigo="ERROR_INESPERADO",
            detalle={
                "motivo": motivo,
                "returncode": salida.returncode,
            },
            raw=crudo,
            stderr=salida.stderr,
        )

    interior, costo = _desenvolver(crudo)

    try:
        datos = json.loads(_sin_backticks(interior))
    except json.JSONDecodeError as error:
        # El caso más probable cuando alguien toca el prompt. El crudo entero se
        # reporta: sin eso, "no devolvió JSON" es un callejón sin salida.
        log.error("claude_no_devolvio_json", con_navegador=con_navegador, error=str(error))
        return Invocacion(
            False,
            codigo="ERROR_INESPERADO",
            detalle={"motivo": "el modelo no devolvió JSON", "error": str(error)},
            raw=crudo,
            stderr=salida.stderr,
            costo_usd=costo,
        )

    if not isinstance(datos, dict):
        return Invocacion(
            False,
            codigo="ERROR_INESPERADO",
            detalle={"motivo": f"se esperaba un objeto y vino {type(datos).__name__}"},
            raw=crudo,
            stderr=salida.stderr,
            costo_usd=costo,
        )

    return Invocacion(True, datos=datos, raw=crudo, stderr=salida.stderr, costo_usd=costo)


def _desenvolver(crudo: str) -> tuple[str, float]:
    """`--output-format json` envuelve la respuesta; adentro va la nuestra.

    Del sobre sale también `total_cost_usd`, que es de dónde salen las métricas
    de costo por mensaje. Si el sobre no parsea se sigue con el crudo: puede ser
    que el modelo haya contestado nuestro JSON directamente.
    """
    try:
        sobre = json.loads(crudo)
    except json.JSONDecodeError:
        return crudo, 0.0

    if not isinstance(sobre, dict):
        return crudo, 0.0

    interior = sobre.get("result", crudo)
    costo = sobre.get("total_cost_usd", 0.0)
    try:
        costo = max(0.0, float(costo))
    except (TypeError, ValueError):
        costo = 0.0
    return interior if isinstance(interior, str) else crudo, costo


def _sin_backticks(texto: str) -> str:
    """Saca el cercado de markdown, que el modelo agrega aunque se le pida que no."""
    limpio = texto.strip()
    if not limpio.startswith("```"):
        return limpio
    limpio = limpio.split("\n", 1)[1] if "\n" in limpio else ""
    if limpio.rstrip().endswith("```"):
        limpio = limpio.rstrip()[:-3]
    return limpio.strip()
