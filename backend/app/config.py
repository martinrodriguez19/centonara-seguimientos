"""Configuración del backend. Un único origen de verdad, leído del entorno.

Nada de `os.environ` suelto por el código: si una variable hace falta, se declara
acá y se valida al arrancar. Un valor mal escrito tiene que romper el arranque,
no aparecer a las tres semanas como un comportamiento raro.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Ya no hay staging: un solo entorno desplegado, que es producción (D17).
Entorno = Literal["local", "produccion"]


class Configuracion(BaseSettings):
    """Variables de entorno del backend.

    Los valores por defecto son los de `.env.example` y sirven para local. En
    producción los inyecta Render.
    """

    model_config = SettingsConfigDict(
        # El .env vive en la raíz del repo y lo comparten backend y agente, pero
        # el backend se corre desde backend/. Se buscan los dos: el de más a la
        # derecha pisa al anterior.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        # El mismo archivo trae AGENTE_*, que acá no son asunto nuestro.
        extra="ignore",
        frozen=True,
    )

    # A quién puede escribirle el sistema NO lo gobierna esta variable: lo
    # gobierna `configuracion.destinos_permitidos` en la base (regla R4). Esto
    # sólo distingue una corrida local de la desplegada, y lo reporta /health.
    entorno: Entorno = "local"

    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "seguimiento"

    # Cuánto espera el driver antes de decidir que Mongo no está. Corto a
    # propósito: /health tiene que contestar rápido que algo anda mal, no
    # quedarse colgado los 30 s que trae Motor por defecto.
    mongo_timeout_ms: int = 2000

    # Login del panel: una contraseña y una cookie firmada (D22). Sin Auth.js,
    # sin magic links, sin correo saliente. Se declaran ahora para que el
    # despliegue tenga la lista completa, pero todavía no las usa nadie.
    panel_password: str = ""
    sesion_secret: str = ""
    sentry_dsn: str = ""

    # Logs en JSON: cómodo para Render, ilegible para una terminal.
    # Por defecto, JSON en todo lo que no sea local.
    log_json: bool | None = None

    @property
    def logs_en_json(self) -> bool:
        if self.log_json is not None:
            return self.log_json
        return self.entorno != "local"


@lru_cache
def obtener_configuracion() -> Configuracion:
    """Configuración cacheada. Se lee una vez, al arrancar."""
    return Configuracion()
