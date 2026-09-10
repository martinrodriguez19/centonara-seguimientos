"""Agente local: lo que corre en la PC del vendedor (07).

Hasta la fase 3 este paquete **no puede mandar un mensaje**: no hay código de
envío y no hay dependencia que lo permita. La forma normal de trabajar mientras
tanto es `python -m agente.main --simulado` (04-AGENTE.md §11).
"""

from pathlib import Path

from agente.version import leer as _leer_version

# El commit instalado, según `agente/VERSION` (lo escribe el actualizador). En
# una máquina de desarrollo no hay archivo y esto vale `0.1.0-dev`.
__version__ = _leer_version(Path(__file__).resolve().parent.parent)
