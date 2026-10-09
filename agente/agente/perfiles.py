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

import contextlib
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


def _numero(archivo: Path) -> int:
    """El número de un archivo de LevelDB (`000012.ldb` → 12): más alto, más nuevo."""
    return int(archivo.stem) if archivo.stem.isdigit() else -1


def _device_id_de(carpeta: Path) -> str | None:
    """El `bridgeDeviceId` que la extensión guardó **último** en este perfil.

    LevelDB no reescribe: agrega. Un id viejo sobrevive en los `.ldb` hasta que
    se compacta, y si la extensión se reinstaló conviven los dos (D66). Por eso
    se recorren los archivos del más viejo al más nuevo —el número los ordena,
    sea `.ldb` o `.log`— y dentro de cada uno todas las apariciones, y gana la
    última.
    """
    almacen = carpeta / "Local Extension Settings" / EXTENSION
    if not almacen.is_dir():
        return None
    archivos = sorted(
        [*almacen.glob("*.ldb"), *almacen.glob("*.log")], key=lambda a: (_numero(a), a.name)
    )
    ultimo = None
    for archivo in archivos:
        try:
            datos = archivo.read_bytes()
        except OSError:
            continue
        marca = datos.find(b"bridgeDeviceId")
        while marca != -1:
            # El valor va justo después de la clave. Se acota la ventana para no
            # agarrar un UUID de otra cosa que esté más adelante en el archivo.
            if encontrado := _UUID.search(datos[marca : marca + 120].decode("latin-1")):
                ultimo = encontrado.group(0)
            marca = datos.find(b"bridgeDeviceId", marca + 1)
    return ultimo


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


# ---------------------------------------------------------------------------
# El deviceId en caliente (D47)
# ---------------------------------------------------------------------------
#
# Antes el deviceId era un requisito de instalación: si la extensión no se
# había usado todavía, el `.env` quedaba sin él y había que volver a correr el
# instalador después de abrirla a mano. El 09/09 dos Macs fallaron cada tanda
# por eso, con el dato ya escrito en el disco por la extensión.
#
# Ahora se resuelve cuando hace falta —al arrancar, y otra vez cuando llega un
# job—. Lo que se encuentra en el perfil se memoriza fuera del repositorio,
# porque el `.env` lo reescribe el instalador.
#
# D66 dio vuelta el orden. D47 ponía el `.env` y lo memorizado antes que el
# disco, y una extensión reinstalada o un Chrome que cambió de perfil dejaba a
# la máquina buscando para siempre un id que ya no existe: mac-sofia falló así
# todas las corridas de octubre. Ahora manda el disco —sólo puede tener el id de
# este Chrome, aunque la cuenta de Claude sea compartida— y el `.env` y lo
# memorizado quedan para cuando el disco no dice nada.

ARCHIVO_DEVICE_ID = "device_id"


def _memoria(casa: Path | None) -> Path:
    from agente.reinicio import carpeta_estado

    return carpeta_estado(casa) / ARCHIVO_DEVICE_ID


def _del_disco(perfil_dir: str) -> str | None:
    """El id que la extensión tiene escrito, en el perfil que se va a usar."""
    todos = listar()
    propio = next((p for p in todos if p.nombre == perfil_dir), None)
    #  El configurado, si es un perfil que sirve: es el que se abre.
    if propio is not None and propio.sirve and propio.device_id:
        return propio.device_id
    #  Si no, el que recomienda `recomendar`, que es lo que hace el instalador:
    #  el .env puede decir Default y la extensión vivir en Profile 3.
    recomendado = recomendar(todos)
    if recomendado.perfil is not None and recomendado.perfil.device_id:
        return recomendado.perfil.device_id
    #  Y si nada sirve entero, lo que tenga el configurado, aunque sea a medias.
    return propio.device_id if propio is not None else None


def resolver_device_id(
    configurado: str, *, perfil_dir: str, casa: Path | None = None, fijo: bool = False
) -> str:
    """El deviceId de esta máquina, o vacío si todavía no existe en ningún lado.

    `fijo` (`AGENTE_DEVICE_ID_FIJO`) devuelve al orden de D47: el `.env` primero.
    """
    configurado = configurado.strip()
    if fijo and configurado:
        return configurado

    memoria = _memoria(casa)
    try:
        memorizado = memoria.read_text(encoding="utf-8").strip()
    except OSError:
        memorizado = ""
    if not _UUID.fullmatch(memorizado):
        memorizado = ""

    encontrado = _del_disco(perfil_dir)
    if encontrado is None:
        return configurado or memorizado

    if encontrado != memorizado:
        #  Una vez por cambio, no en cada job: lo memorizado ya es el nuevo.
        anterior = memorizado or configurado
        if anterior and anterior != encontrado:
            _avisar_cambio(anterior, encontrado)
        #  Memorizar es cortesía: si no se puede escribir, igual se usa lo hallado.
        with contextlib.suppress(OSError):
            memoria.write_text(encontrado + "\n", encoding="utf-8")
    return encontrado


def _avisar_cambio(anterior: str, nuevo: str) -> None:
    """Queda en el log: es la explicación de "ayer no andaba y hoy sí"."""
    from agente.logging import obtener_logger

    obtener_logger(__name__).warning("device_id_cambiado", anterior=anterior, nuevo=nuevo)
