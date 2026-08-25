"""Configuración del agente. Un único origen de verdad, leído del entorno.

Nada de `os.environ` suelto por el código: si una variable hace falta, se
declara acá y se valida al arrancar. Un valor mal escrito tiene que romper el
arranque, no aparecer a las tres semanas como un comportamiento raro.

En la Mac del vendedor la configuración va a venir de
`/opt/centonara/config.json` (04-AGENTE.md §2), que lo escribe el instalador.
Eso llega con el registro, en la fase 1. El esqueleto lee del entorno y nada
más.
"""

import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ya no hay staging: un solo entorno desplegado, que es producción (D17).
Entorno = Literal["local", "produccion"]
Modo = Literal["simulado", "prueba", "real"]


def _carpeta_agente() -> Path:
    """La carpeta `agente/`, resuelta sin depender del directorio actual.

    Importa por dos motivos, los dos del historial del MVP:

    - el `.env` del repo no está donde se corre el comando;
    - `LISTAR_CHATS` va a necesitar pasarla como `cwd=` para que Claude Code
      encuentre su contexto (04-AGENTE.md §5).

    Si algún día se empaqueta con PyInstaller, `__file__` apunta a un temporal que
    se borra al salir: ahí manda la carpeta del ejecutable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


CARPETA_AGENTE = _carpeta_agente()


class Configuracion(BaseSettings):
    """Variables de entorno del agente.

    Los valores por defecto son los de `.env.example` y sirven para local. En la
    Mac del vendedor los escribe el instalador.
    """

    model_config = SettingsConfigDict(
        # Rutas absolutas y no relativas al directorio actual: el agente se
        # arranca desde la terminal en desarrollo y desde launchd en la Mac del
        # vendedor, y ahí el directorio actual no es el nuestro.
        # El de más a la derecha pisa al anterior.
        env_file=(CARPETA_AGENTE.parent / ".env", CARPETA_AGENTE / ".env"),
        env_file_encoding="utf-8",
        # Los campos se pueden pasar por su nombre además de por el nombre de
        # la variable de entorno: lo usan los tests para construir una
        # configuración sin tocar el entorno del proceso.
        populate_by_name=True,
        # El mismo archivo trae las variables del backend, que acá no son
        # asunto nuestro.
        extra="ignore",
        frozen=True,
    )

    # Las variables del agente van con prefijo AGENTE_ y CLAUDE_BIN no, así que
    # el nombre del entorno se declara campo por campo en vez de con env_prefix.
    # Es más verboso y a cambio no hay que adivinar cómo se llama ninguna.

    # A quién puede escribirle el sistema lo gobierna
    # `configuracion.destinos_permitidos` (regla R4), no una variable de entorno.
    # El agente revalida esa lista antes de escribir, porque un job pudo quedar
    # encolado y la lista pudo cambiar en el medio.
    entorno: Entorno = "local"

    modo: Modo = Field("simulado", validation_alias="AGENTE_MODO")

    backend_url: str = Field("http://localhost:8000", validation_alias="AGENTE_BACKEND_URL")
    token: str = Field("", validation_alias="AGENTE_TOKEN")
    machine_id: str = Field("mac-1", validation_alias="AGENTE_MACHINE_ID")

    # Fijo por máquina. Sin esto, con más de un Chrome abierto headless no sabe
    # a cuál conectarse (problema #5 del MVP). Lo verifica el chequeo `device_id`.
    device_id: str = Field("", validation_alias="AGENTE_DEVICE_ID")

    # Ruta COMPLETA al ejecutable: `shutil.which("claude")` devolvía None
    # (problema #2 del MVP). Lo verifica el chequeo `claude_bin`.
    claude_bin: str = Field("", validation_alias="CLAUDE_BIN")

    # --- Chrome, para el motor de envío -------------------------------------
    #
    # El motor de envío usa un navegador DEDICADO (D24): una carpeta de datos
    # propia, con su propia sesión de WhatsApp vinculada con `--vincular`. El
    # Chrome del vendedor no se toca. Vacío = la carpeta estándar del sistema.
    navegador_dir: str = Field("", validation_alias="AGENTE_NAVEGADOR_DIR")

    # Ruta al ejecutable de Chrome. Vacío = se buscan las rutas habituales del
    # sistema, que es lo que va a pasar en casi todas las máquinas.
    chrome_bin: str = Field("", validation_alias="CHROME_BIN")
    chrome_perfil: str = Field("", validation_alias="CHROME_PERFIL")

    # ⚠️ El perfil DENTRO de `User Data`. Sin esto Chrome abre `Default`, que en
    # una máquina con varios perfiles no es el que tiene la extensión ni la
    # sesión de WhatsApp. Es el error más caro de esta sección.
    chrome_perfil_dir: str = Field("Default", validation_alias="CHROME_PERFIL_DIR")
    chrome_puerto: int = Field(9222, validation_alias="CHROME_PUERTO")

    # Logs en JSON: cómodo para archivo y para soporte, ilegible en una
    # terminal. Por defecto, JSON en todo lo que no sea local.
    log_json: bool | None = Field(None, validation_alias="LOG_JSON")

    @property
    def logs_en_json(self) -> bool:
        if self.log_json is not None:
            return self.log_json
        return self.entorno != "local"

    def resumen_para_log(self) -> dict[str, object]:
        """Lo que se puede escribir en un log, y sólo eso.

        `token` es una credencial: se reporta si está o no está, nunca su
        valor. Los logs del agente terminan en la Mac del vendedor y en un
        adjunto de soporte.
        """
        return {
            "entorno": self.entorno,
            "modo": self.modo,
            "machine_id": self.machine_id,
            "device_id": self.device_id or None,
            "backend_url": self.backend_url,
            "claude_bin": self.claude_bin or None,
            "chrome_perfil_dir": self.chrome_perfil_dir,
            "chrome_puerto": self.chrome_puerto,
            "token_definido": bool(self.token),
        }


@lru_cache
def obtener_configuracion() -> Configuracion:
    """Configuración cacheada. Se lee una vez, al arrancar."""
    return Configuracion()
