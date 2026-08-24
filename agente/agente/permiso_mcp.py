"""Habilita `mcp__claude-in-chrome` en `~/.claude/settings.json`, sin pisar nada.

Es el permiso que necesita el modo headless: sin él, `claude -p` **se
auto-deniega** las acciones de navegador y el job falla con un 502 que no dice
nada. Es el problema #3 del MVP.

Se hace acá y no con un `echo` en el SOP por un motivo concreto: ese archivo
suele tener otras cosas. En la máquina donde se desarrolló esto tenía además
`agentPushNotifEnabled`, y el comando que estaba documentado —un `echo` con
redirección— lo habría borrado. El vendedor que ya usaba Claude Code para otra
cosa se habría quedado sin su configuración, y nadie lo habría notado hasta que
algo dejara de andar.

Lo que este módulo NO puede hacer, y no es un descuido: **el permiso de sitio de
la extensión** —el que habilita `web.whatsapp.com`— vive adentro del
almacenamiento de la extensión y se concede desde su interfaz. Es una puerta de
consentimiento: la idea es que una persona la abra a propósito. Escribirla desde
afuera sería saltear un control, además de romperse en la próxima versión.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PERMISO = "mcp__claude-in-chrome"


@dataclass(frozen=True)
class Resultado:
    cambiado: bool
    detalle: str
    archivo: Path | None = None


def asegurar(inicio: Path | None = None) -> Resultado:
    """Deja el permiso puesto, conservando todo lo demás del archivo.

    Idempotente: si ya está, no toca nada y lo dice.
    """
    hogar = inicio or Path.home()
    archivo = hogar / ".claude" / "settings.json"

    contenido: dict = {}
    if archivo.exists():
        try:
            contenido = json.loads(archivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            # ⚠️ No se sobrescribe un archivo que no se pudo leer. Puede tener
            # configuración de alguien y estar sólo mal formado; pisarlo sería
            # cambiar un problema chico por uno peor.
            return Resultado(
                False,
                f"{archivo} existe pero no se pudo leer ({error}). Revisalo a mano.",
                archivo,
            )
        if not isinstance(contenido, dict):
            return Resultado(
                False, f"{archivo} no contiene un objeto JSON. Revisalo a mano.", archivo
            )

    permisos = contenido.setdefault("permissions", {})
    if not isinstance(permisos, dict):
        return Resultado(False, f"{archivo}: 'permissions' no es un objeto. Revisalo.", archivo)

    permitidos = permisos.setdefault("allow", [])
    if not isinstance(permitidos, list):
        return Resultado(False, f"{archivo}: 'permissions.allow' no es una lista.", archivo)

    if PERMISO in permitidos:
        return Resultado(False, f"ya estaba en {archivo}", archivo)

    permitidos.append(PERMISO)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(contenido, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return Resultado(True, f"agregado a {archivo}", archivo)
