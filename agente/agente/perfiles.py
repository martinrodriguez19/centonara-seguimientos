"""Qué perfil de Chrome usar, y cuál es el `deviceId` de esta máquina.

Existe para sacarle dos tareas a una persona que está instalando una Mac y no
tiene por qué pelearse con `grep` ni comparar rutas a ojo:

1. **Qué perfil de Chrome** tiene la extensión de Claude **y** la sesión de
   WhatsApp. Tienen que ser el mismo, y en la máquina donde se desarrolló esto
   estaban separados. Comparar dos listas de rutas largas para darse cuenta es
   pedirle a alguien que haga de intérprete.
2. **El `deviceId`**, que estaba documentado como un `grep` de dos líneas con
   espacios escapados sobre una ruta con comodines. Funciona, y nadie lo escribe
   bien la primera vez.

La salida de este módulo es lo que va al `.env`, ya resuelto.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# El identificador de la extensión Claude in Chrome en la tienda. Es estable.
EXTENSION = "fcoeoabgfenejglbffodgkkbkcdhcgfn"

# La extensión guarda su propio identificador de dispositivo bajo esta clave.
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def carpeta_chrome() -> Path:
    """La carpeta `User Data`, donde viven todos los perfiles."""
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Google/Chrome"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"
    return Path.home() / ".config/google-chrome"


@dataclass(frozen=True)
class Perfil:
    """Un perfil de Chrome, y qué tiene adentro."""

    nombre: str
    tiene_extension: bool
    tiene_whatsapp: bool
    device_id: str | None = None

    @property
    def sirve(self) -> bool:
        """Las dos cosas, en el mismo perfil. Es lo único que sirve."""
        return self.tiene_extension and self.tiene_whatsapp


def _device_id_de(carpeta: Path) -> str | None:
    """El `bridgeDeviceId` que la extensión guardó en este perfil."""
    almacen = carpeta / "Local Extension Settings" / EXTENSION
    if not almacen.is_dir():
        return None
    for archivo in sorted(almacen.glob("*.log")) + sorted(almacen.glob("*.ldb")):
        try:
            datos = archivo.read_bytes()
        except OSError:
            continue
        marca = datos.find(b"bridgeDeviceId")
        if marca == -1:
            continue
        # El valor va justo después de la clave. Se acota la ventana para no
        # agarrar un UUID de otra cosa que esté más adelante en el archivo.
        if encontrado := _UUID.search(datos[marca : marca + 120].decode("latin-1")):
            return encontrado.group(0)
    return None


def _tiene_whatsapp(carpeta: Path) -> bool:
    """¿Este perfil abrió WhatsApp Web alguna vez?

    Se mira el IndexedDB **y su tamaño**: la carpeta puede quedar vacía cuando
    la sesión venció, y eso no es lo mismo que haberla usado.
    """
    for indexeddb in (carpeta / "IndexedDB").glob("*whatsapp*"):
        if any(indexeddb.rglob("*")):
            return True
    return False


def listar() -> list[Perfil]:
    """Todos los perfiles de Chrome de esta máquina, con lo que tienen."""
    base = carpeta_chrome()
    if not base.is_dir():
        return []

    perfiles = []
    for carpeta in sorted(base.iterdir()):
        if not carpeta.is_dir():
            continue
        if carpeta.name != "Default" and not carpeta.name.startswith("Profile"):
            continue
        perfiles.append(
            Perfil(
                nombre=carpeta.name,
                tiene_extension=(carpeta / "Extensions" / EXTENSION).is_dir(),
                tiene_whatsapp=_tiene_whatsapp(carpeta),
                device_id=_device_id_de(carpeta),
            )
        )
    return perfiles


@dataclass(frozen=True)
class Recomendacion:
    """Qué usar, o qué falta para poder usar algo."""

    perfil: Perfil | None
    problema: str = ""
    #  Qué hacer, en una línea, cuando hay problema.
    solucion: str = ""

    @property
    def listo(self) -> bool:
        return self.perfil is not None and self.perfil.sirve


def recomendar(perfiles: list[Perfil] | None = None) -> Recomendacion:
    """El perfil que hay que usar, o por qué todavía no hay ninguno."""
    perfiles = listar() if perfiles is None else perfiles

    if not perfiles:
        return Recomendacion(
            None,
            "no se encontró ningún perfil de Chrome en esta máquina",
            f"¿Está Chrome instalado? Se buscó en {carpeta_chrome()}",
        )

    #  El caso bueno: uno con las dos cosas. Si hay varios, el que además tiene
    #  deviceId, que es el que se usó de verdad.
    sirven = [p for p in perfiles if p.sirve]
    if sirven:
        elegido = next((p for p in sirven if p.device_id), sirven[0])
        return Recomendacion(elegido)

    con_extension = [p.nombre for p in perfiles if p.tiene_extension]
    con_whatsapp = [p.nombre for p in perfiles if p.tiene_whatsapp]

    if con_extension and con_whatsapp:
        return Recomendacion(
            None,
            (
                f"la extensión está en {', '.join(con_extension)} y la sesión de "
                f"WhatsApp en {', '.join(con_whatsapp)}: son perfiles distintos"
            ),
            (
                f"Abrí Chrome en {con_whatsapp[0]} e instalá ahí la extensión, "
                f"o iniciá WhatsApp Web en {con_extension[0]}. Tienen que estar juntas."
            ),
        )
    if con_extension:
        return Recomendacion(
            None,
            f"la extensión está en {', '.join(con_extension)}, pero ningún perfil tiene WhatsApp",
            f"Abrí Chrome en {con_extension[0]}, entrá a web.whatsapp.com y escaneá el QR.",
        )
    if con_whatsapp:
        return Recomendacion(
            None,
            f"WhatsApp está en {', '.join(con_whatsapp)}, pero falta la extensión",
            f"Abrí Chrome en {con_whatsapp[0]} e instalá la extensión Claude in Chrome.",
        )
    return Recomendacion(
        None,
        "ningún perfil tiene la extensión ni la sesión de WhatsApp",
        "Instalá la extensión Claude in Chrome y entrá a web.whatsapp.com "
        "con la línea del vendedor.",
    )
