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

from agente.jobs import cuota
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
# backend (60 min). Si lo pasara, el backend devolvería el job a la cola
# mientras el agente sigue en eso, y el trabajo se pagaría dos veces.
TIMEOUT_LISTAR = 25 * 60.0

# El pase único (BORRADORES): leer, redactar y tipear una tanda entera en una
# sola sesión. Eran 20 minutos con la nota "si no alcanzan, achicar la tanda";
# ese criterio se escribió cuando la tanda sólo leía y tipeaba. Desde D40/D41
# cada chat cuesta más —leer diez mensajes, clasificar en tres ramas, sacar una
# cita literal— y desde D44 el freno normal de la tanda es `max_visitas`, no
# este número: esto es la red de abajo.
#
# ⚠️ Sigue valiendo el techo de arriba: tiene que quedar por debajo de
# `cola.SEGUNDOS_PARA_DAR_POR_COLGADO` (60 min) con margen. Si esto alguna vez
# pasa de ~45, primero se sube el del backend y recién después éste.
TIMEOUT_BORRADORES = 35 * 60.0

# D65.4: cuánto de lo último que dijo el proceso se guarda con un TIMEOUT. Es
# para distinguir un Chrome colgado de cualquier otra cosa, no para releer la
# tanda entera.
COLA_DEL_TIMEOUT = 2048

# D67.2: la marca con la que el prompt de BORRADORES anota cada chat terminado,
# en una línea propia, mientras trabaja. Se lee de la salida en vivo si la
# tanda se corta por tiempo, y se borra de la respuesta final si se coló ahí.
MARCA_CHAT = "CHAT_TERMINADO"


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
    en_vivo: bool = False,
) -> Invocacion:
    """Le pasa el prompt a Claude Code y devuelve el JSON que contestó.

    `con_navegador=False` **omite `--chrome`**, y no es un detalle de
    configuración: es donde está el ahorro del proyecto. `REDACTAR` es el job
    más frecuente —uno por chat— y sacarlo del circuito del navegador es lo que
    hace viable el costo por mensaje.

    `en_vivo` (D67.2) pide la salida como `stream-json`: cada mensaje del modelo
    sale apenas lo escribe, y no sólo el sobre del final. Con un TIMEOUT, lo
    que el proceso alcanzó a decir queda en `raw` —es lo que lee BORRADORES para
    no perder los chats ya hechos—. Con una respuesta normal, el sobre del final
    es el mismo de `--output-format json` y se lee igual.
    """
    if not claude_bin:
        return Invocacion(
            False, codigo="ERROR_INESPERADO", detalle={"motivo": "CLAUDE_BIN sin configurar"}
        )

    if en_vivo:
        #  `stream-json` con `-p` exige `--verbose`.
        comando = [claude_bin, "-p", "--output-format", "stream-json", "--verbose"]
    else:
        comando = [claude_bin, "-p", "--output-format", "json"]
    if con_navegador:
        comando.insert(2, "--chrome")

    hacer = correr or _correr
    try:
        # A un hilo: `subprocess.run` bloquea, y el bucle tiene que poder seguir
        # latiendo mientras un LISTAR tarda sus minutos.
        salida = await asyncio.to_thread(hacer, comando, prompt, timeout=timeout, cwd=carpeta)
    except subprocess.TimeoutExpired as error:
        dijo = _como_texto(error.stdout)
        errores = _como_texto(error.stderr)
        log.error("claude_timeout", segundos=timeout, con_navegador=con_navegador, dijo=len(dijo))
        return Invocacion(
            False,
            codigo="TIMEOUT",
            detalle={
                "segundos": timeout,
                #  D65.4: el final de lo que alcanzó a decir. Vacío también dice
                #  algo: el proceso no escribió nada en todo ese tiempo.
                "salida": (dijo + ("\n" + errores if errores else ""))[-COLA_DEL_TIMEOUT:],
            },
            raw=dijo,
            stderr=errores,
        )
    except (OSError, ValueError) as error:
        # No se pudo lanzar el proceso: la ruta no existe, no es ejecutable.
        log.error("claude_no_arranca", error=str(error), bin=claude_bin)
        return Invocacion(
            False,
            codigo="ERROR_INESPERADO",
            detalle={"motivo": "no se pudo ejecutar", "error": str(error)[:300]},
        )

    if en_vivo:
        sobre = _sobre_final(salida.stdout)
        if sobre is None and salida.returncode == 0:
            #  Salió bien sin decir el resultado: no hay respuesta que leer, y un
            #  evento suelto del medio no puede pasar por una.
            log.error("claude_sin_sobre_final", con_navegador=con_navegador)
            return Invocacion(
                False,
                codigo="ERROR_INESPERADO",
                detalle={"motivo": "la salida en vivo terminó sin el resultado final"},
                raw=salida.stdout,
                stderr=salida.stderr,
            )
        salida = Salida(salida.returncode, sobre or salida.stdout, salida.stderr)
    return _leer(salida, con_navegador=con_navegador)


def _como_texto(crudo: str | bytes | None) -> str:
    """Lo que trae un `TimeoutExpired`: bytes en macOS y Linux, texto en Windows."""
    if crudo is None:
        return ""
    if isinstance(crudo, bytes):
        return crudo.decode("utf-8", errors="replace")
    return crudo


def _sobre_final(stdout: str) -> str | None:
    """De una salida `stream-json`, la línea del sobre final (`"type": "result"`).

    `None` si no está: el proceso murió antes de terminar, o salió por un
    camino que no escribe el sobre. Con código distinto de cero `_leer` mira la
    salida entera, que es donde puede estar el aviso de cuota.
    """
    for linea in reversed(stdout.splitlines()):
        linea = linea.strip()
        if not linea.startswith("{"):
            continue
        try:
            evento = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(evento, dict) and evento.get("type") == "result":
            return linea
    return None


def textos_del_modelo(stdout: str) -> list[str]:
    """Los textos que escribió el modelo, en orden, de una salida `stream-json`.

    Saltea lo que no parsea: con un TIMEOUT la última línea suele estar cortada.
    """
    textos: list[str] = []
    for linea in stdout.splitlines():
        linea = linea.strip()
        if not linea.startswith("{"):
            continue
        try:
            evento = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if not isinstance(evento, dict) or evento.get("type") != "assistant":
            continue
        contenido = (evento.get("message") or {}).get("content")
        for bloque in contenido if isinstance(contenido, list) else []:
            if isinstance(bloque, dict) and bloque.get("type") == "text":
                textos.append(str(bloque.get("text") or ""))
    return textos


def _leer(salida: Salida, *, con_navegador: bool) -> Invocacion:
    crudo = salida.stdout.strip()

    if salida.returncode != 0:
        # Lo que claude tenía para decir suele salir por stdout —con
        # `--output-format json` el error viaja en el sobre— y stderr queda
        # vacío. Sin mostrarlo, "código distinto de cero" es un callejón sin
        # salida: pasó, instalando la primera Mac.
        dijo = (salida.stderr.strip() or crudo)[-300:] or "sin salida"
        # D60: sin cuota no es un error a reintentar —no se arregla en treinta
        # segundos— sino una pausa hasta que vuelva.
        if cuota.agotada(crudo) or cuota.agotada(salida.stderr):
            return _sin_cuota(crudo + "\n" + salida.stderr, salida)
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

    # D60: con código 0 el aviso de cuota también puede venir adentro de un
    # sobre marcado como error. Sólo se mira ahí: una respuesta sana puede
    # hablar de "límites" por cualquier otra razón.
    if _sobre_con_error(crudo) and cuota.agotada(interior):
        return _sin_cuota(interior, salida)

    try:
        datos = json.loads(_sin_backticks(_sin_marcas(interior)))
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


def _sin_cuota(texto: str, salida: Salida) -> Invocacion:
    """El job, reportado como cuota agotada, con la hora a la que vuelve si se sabe."""
    vuelve = cuota.reinicio(texto)
    detalle: dict[str, Any] = {"motivo": "Claude Code se quedó sin cuota en esta máquina"}
    if vuelve is not None:
        detalle["reinicia_en"] = vuelve.isoformat()
    log.warning("claude_sin_cuota", reinicia_en=detalle.get("reinicia_en"))
    return Invocacion(
        False, codigo="LIMITE_USO", detalle=detalle, raw=salida.stdout, stderr=salida.stderr
    )


def _sobre_con_error(crudo: str) -> bool:
    try:
        sobre = json.loads(crudo)
    except json.JSONDecodeError:
        return False
    return isinstance(sobre, dict) and bool(sobre.get("is_error"))


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


def _sin_marcas(texto: str) -> str:
    """Saca las líneas `CHAT_TERMINADO` que el modelo haya dejado en la respuesta final.

    El prompt las pide entre chat y chat; si la del último chat cae en el mismo
    mensaje que el JSON, no puede romper el reporte de una tanda que salió bien.
    """
    if MARCA_CHAT not in texto:
        return texto
    return "\n".join(
        linea for linea in texto.splitlines() if not linea.lstrip().startswith(MARCA_CHAT)
    )


def _sin_backticks(texto: str) -> str:
    """Saca el cercado de markdown, que el modelo agrega aunque se le pida que no."""
    limpio = texto.strip()
    if not limpio.startswith("```"):
        return limpio
    limpio = limpio.split("\n", 1)[1] if "\n" in limpio else ""
    if limpio.rstrip().endswith("```"):
        limpio = limpio.rstrip()[:-3]
    return limpio.strip()
