"""Qué commit deberían correr las máquinas (D45), y si cada una lo corre.

La versión que se instala **la fija el panel**, no la rama. Hay una perilla en
la configuración, `version_agente_esperada`: con un sha, todas las máquinas
convergen a ese commit —es el rollback sin viajar a ninguna casa—; vacía, "lo
que está en `main`", que es lo que se resuelve acá.

Dos cosas que este módulo cuida:

- **Las máquinas nunca hablan con GitHub para decidir.** Preguntan al backend
  (`GET /api/agente/version-esperada`) y el backend resuelve la rama a un sha
  una vez cada `TTL` para todas. Veinte máquinas cada hora no pueden ser veinte
  llamadas a la API de GitHub.
- **No saber no es saber "lo último".** Si GitHub no contesta y no hay nada en
  caché, la esperada queda vacía y las máquinas no se mueven. Seguir con lo
  que hay es siempre mejor que saltar a algo que nadie verificó.
"""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.logging import obtener_logger

log = obtener_logger(__name__)

# Cuánto vale la resolución de la rama antes de volver a preguntar. Cinco
# minutos: un push tarda eso en llegar a las máquinas, y GitHub ve una llamada
# cada cinco minutos en vez de una por máquina por hora.
TTL_S = 300

# Un sha de git: entre 7 (abreviado) y 40 (entero) dígitos hexadecimales.
SHA = re.compile(r"^[0-9a-f]{7,40}$")

# Cuántos caracteres del sha se comparan. El agente reporta el abreviado que
# escribió el actualizador; el backend puede tener el entero de GitHub.
LARGO_COMPARACION = 7

Resolver = Callable[[str, str], Awaitable[str]]


@dataclass(frozen=True)
class Esperada:
    """El commit al que tienen que converger las máquinas."""

    sha: str
    """Vacío = no se pudo saber. Las máquinas no se actualizan a "no sé"."""
    origen: str
    """`panel` (la fijó alguien), `rama` (lo último de la rama), `desconocida`."""

    def a_dict(self) -> dict[str, str]:
        return {"sha": self.sha, "origen": self.origen}


# La caché de la rama resuelta: (sha, cuándo). Una sola, de proceso, porque el
# backend es uno (D17) y es lo único que la consulta.
_cache: dict[str, tuple[str, float]] = {}


def normalizar(sha: Any) -> str:
    """Un sha como lo acepta la configuración: minúsculas, o vacío si no lo es."""
    texto = str(sha or "").strip().lower()
    return texto if SHA.match(texto) else ""


async def _resolver_en_github(repo: str, rama: str) -> str:
    """El sha de la punta de `rama`, preguntado a la API pública de GitHub.

    `Accept: application/vnd.github.sha` devuelve el sha pelado, sin JSON que
    parsear. Sin token: el repositorio es público, y un token en el backend
    sería un secreto más que cuidar para ahorrar una llamada por cinco minutos.
    """
    async with httpx.AsyncClient(timeout=8.0) as cliente:
        respuesta = await cliente.get(
            f"https://api.github.com/repos/{repo}/commits/{rama}",
            headers={"Accept": "application/vnd.github.sha", "User-Agent": "centonara-backend"},
        )
        respuesta.raise_for_status()
        return respuesta.text.strip()


async def esperada(
    config: dict[str, Any],
    *,
    repo: str,
    rama: str,
    resolver: Resolver | None = None,
    ahora: float | None = None,
) -> Esperada:
    """La versión a la que tienen que ir las máquinas, según el panel o la rama.

    `config` es la configuración operativa (la de la base): si trae
    `version_agente_esperada`, manda. Si no, la rama, con caché de `TTL_S`.

    `resolver` se resuelve al llamar y no en la firma, a propósito: los tests
    reemplazan `_resolver_en_github` en el módulo y ningún test toca la red.
    """
    fijada = normalizar(config.get("version_agente_esperada"))
    if fijada:
        return Esperada(fijada, "panel")

    momento = ahora if ahora is not None else time.monotonic()
    clave = f"{repo}@{rama}"
    guardado = _cache.get(clave)
    if guardado is not None and momento - guardado[1] < TTL_S:
        return Esperada(guardado[0], "rama")

    try:
        sha = normalizar(await (resolver or _resolver_en_github)(repo, rama))
    except Exception as error:
        sha = ""
        log.warning("version_esperada_no_resuelta", rama=rama, error=str(error)[:200])

    if sha:
        _cache[clave] = (sha, momento)
        return Esperada(sha, "rama")
    if guardado is not None:
        #  GitHub no contestó pero hubo una respuesta antes: mejor vieja que
        #  ninguna. Las máquinas ya estaban convergiendo a ésa.
        return Esperada(guardado[0], "rama")
    return Esperada("", "desconocida")


def coincide(reportada: str | None, sha_esperado: str) -> bool | None:
    """¿La máquina corre lo esperado? `None` cuando no hay con qué comparar.

    `reportada` es lo que el agente mandó al registrarse: `"7912e13 2026-09-09"`
    (lo escribió el actualizador), o `"0.1.0"` / `"0.1.0-dev"` (nunca se
    instaló con él). Sin sha de un lado o del otro, no se afirma nada: una
    máquina "desactualizada" tiene que ser una que reportó un commit distinto,
    no una de la que no sabemos.
    """
    if not sha_esperado:
        return None
    primero = (reportada or "").split()[0].lower() if (reportada or "").split() else ""
    if not SHA.match(primero):
        return None
    largo = min(len(primero), len(sha_esperado))
    if largo < LARGO_COMPARACION:
        return None
    return primero[:largo] == sha_esperado[:largo]


def olvidar_cache() -> None:
    """Para los tests, y para nada más."""
    _cache.clear()
