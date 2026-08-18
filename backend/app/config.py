"""Configuración del backend. Un único origen de verdad, leído del entorno.

Nada de `os.environ` suelto por el código: si una variable hace falta, se declara
acá y se valida al arrancar. Un valor mal escrito tiene que romper el arranque,
no aparecer a las tres semanas como un comportamiento raro.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Entorno = Literal["local", "staging", "produccion"]


class Configuracion(BaseSettings):
    """Variables de entorno del backend (06 §4).

    Los valores por defecto son los de `.env.example` y sirven para local. En
    staging y en producción los inyecta Render.
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

    # ENTORNO=produccion es la única variable que habilita el envío real (05 §6).
    # En el Sprint 0 no hay código de envío que habilitar (R7); la declaramos
    # ahora porque /health la reporta y porque el despliegue ya la necesita.
    entorno: Entorno = "local"

    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "seguimiento"

    # Cuánto espera el driver antes de decidir que Mongo no está. Corto a
    # propósito: /health tiene que contestar rápido que algo anda mal, no
    # quedarse colgado los 30 s que trae Motor por defecto.
    mongo_timeout_ms: int = 2000

    # Auth (Sprint 1) y correo (magic links). Se declaran ahora para que el
    # despliegue de T0.7 tenga la lista completa de variables, pero todavía no
    # las usa nadie: por eso no son obligatorias.
    jwt_secret: str = ""
    auth_email_from: str = "no-reply@centonara-ia.com"
    smtp_url: str = "smtp://localhost:1025"
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
