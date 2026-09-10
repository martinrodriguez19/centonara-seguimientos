"""Qué versión del agente es ésta, leída de `agente/VERSION`.

Antes `__version__` era `"0.1.0"` escrito a mano, y nunca se tocó: el 09/09
tres máquinas con código distinto reportaron exactamente lo mismo, y la
pregunta "¿cuál está atrasada?" hubo que contestarla leyendo logs. La versión
tiene que decir **qué commit** corre, y eso no lo puede saber el código sobre
sí mismo: lo escribe quien lo instala.

`VERSION` es una línea: el sha corto del commit, y opcionalmente la fecha:

    7912e13 2026-09-09

Lo escribe `instalador/actualizar.sh` (o `.ps1`) al terminar de aplicar un
commit, y **no está en el repositorio**: en una máquina de desarrollo no existe
y la versión es `0.1.0-dev`, que es la verdad — nadie la instaló.
"""

from __future__ import annotations

import re
from pathlib import Path

ARCHIVO = "VERSION"
SIN_INSTALAR = "0.1.0-dev"

# Lo que puede haber en la línea: un sha (hex), y después lo que sea, corto.
# El backend acepta hasta 64 caracteres; acá se recorta antes para que un
# archivo raro nunca haga fallar el registro de la máquina.
LARGO_MAXIMO = 64
_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def leer(carpeta: Path) -> str:
    """La versión instalada en `carpeta`, o `SIN_INSTALAR` si no hay archivo.

    Nunca levanta: un `VERSION` ilegible vale lo mismo que uno ausente. Lo que
    importa es que el agente arranque y se registre; qué versión dice es un
    dato para el panel, no una condición.
    """
    try:
        texto = (carpeta / ARCHIVO).read_text(encoding="utf-8")
    except OSError:
        return SIN_INSTALAR
    primera = texto.strip().splitlines()[0].strip() if texto.strip() else ""
    if not primera:
        return SIN_INSTALAR
    return " ".join(primera.split())[:LARGO_MAXIMO]


def sha(version: str) -> str | None:
    """El sha de una versión como la reporta `leer`, o `None` si no trae uno."""
    primero = version.split()[0] if version.split() else ""
    return primero if _SHA.match(primero) else None
