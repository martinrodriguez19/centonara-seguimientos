"""El token de Claude que llega del panel (D73).

D68 dejó el token de `claude setup-token` como opción del instalador: llegaba
sólo a la máquina donde alguien lo pegaba. Ahora el dueño lo carga una vez en
el panel y viaja en la respuesta del latido a cada máquina que usa otro.

Lo que hace esto:

- dice qué token usar (`vigente`): el que llegó en este proceso, o el del `.env`;
- reporta cuál usa sin decirlo (`hash_corto`, el mismo cálculo del backend);
- y cuando llega uno nuevo lo escribe en el `.env` —donde ya vive desde D68, y
  el instalador lo conserva al reinstalar— para que sobreviva a un reinicio.

**El valor nunca se imprime ni se loguea.** El log dice sólo el hash corto.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
from pathlib import Path

from agente.config import CARPETA_AGENTE, obtener_configuracion
from agente.logging import obtener_logger

log = obtener_logger(__name__)

VARIABLE = "CLAUDE_CODE_OAUTH_TOKEN"

#  El que llegó por latido en este proceso. `Configuracion` está congelada y
#  cacheada: sin esto, el token nuevo recién se usaría al reiniciar el agente.
_recibido: str | None = None


def vigente() -> str:
    """El token que hay que pasarle a `claude`, o vacío si no hay."""
    if _recibido is not None:
        return _recibido
    return obtener_configuracion().claude_oauth_token.strip()


def hash_corto(token: str) -> str:
    """Igual que `app.core.conexiones.hash_corto`: los dos lados tienen que coincidir."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()[:16]


def reportado() -> str:
    """Lo que viaja en el latido: el hash del token en uso, o "" si no hay."""
    token = vigente()
    return hash_corto(token) if token else ""


def _parece_token(token: str) -> bool:
    limpio = token.strip()
    largo_ok = 40 <= len(limpio) <= 400
    return limpio.startswith("sk-ant-") and largo_ok and not re.search(r"\s", limpio)


def archivo_env() -> Path:
    """El `.env` que lee `Configuracion`: el de la carpeta `agente/` si existe
    (es el que gana), si no el de la raíz del repositorio, que es el que
    escribe el instalador."""
    propio = CARPETA_AGENTE / ".env"
    return propio if propio.exists() else CARPETA_AGENTE.parent / ".env"


def _escribir(archivo: Path, token: str) -> None:
    lineas = archivo.read_text(encoding="utf-8").splitlines() if archivo.exists() else []
    nueva = f"{VARIABLE}={token}"
    reemplazada = False
    for i, linea in enumerate(lineas):
        if linea.startswith(f"{VARIABLE}="):
            lineas[i] = nueva
            reemplazada = True
    if not reemplazada:
        lineas.append(nueva)
    temporal = archivo.with_name(archivo.name + ".nuevo")
    temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    #  El `.env` tiene credenciales: sólo el usuario. En Windows el instalador ya
    #  le dejó la ACL; `replace` conserva la del destino.
    with contextlib.suppress(OSError):
        os.chmod(temporal, 0o600)
    os.replace(temporal, archivo)


def aplicar(token: str, *, archivo: Path | None = None) -> bool:
    """Usa este token desde ya, y lo deja en el `.env`. `True` si lo tomó.

    Un token que no parece de `setup-token` no se toma: el backend ya lo
    valida al cargarlo, y esto es para no romper una máquina por un dato raro.
    Si no se puede escribir el `.env`, se usa igual en este proceso.
    """
    global _recibido
    limpio = token.strip()
    if not _parece_token(limpio):
        log.warning("token_claude_rechazado")
        return False
    if limpio == vigente():
        return True
    _recibido = limpio
    destino = archivo or archivo_env()
    try:
        _escribir(destino, limpio)
    except OSError as error:
        log.warning("token_claude_no_guardado", error=str(error)[:200], hash=hash_corto(limpio))
    else:
        log.info("token_claude_recibido", hash=hash_corto(limpio))
    return True


def olvidar() -> None:
    """Para los tests."""
    global _recibido
    _recibido = None
