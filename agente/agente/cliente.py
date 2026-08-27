"""El cliente HTTP contra el backend. Los cuatro endpoints y nada más.

Está separado del bucle a propósito: el bucle tiene la lógica de cuándo
preguntar y qué hacer con cada respuesta, y se puede testear entero sin red
reemplazando esto por un doble.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from agente.logging import obtener_logger

log = obtener_logger(__name__)

TIMEOUT = 30.0


@dataclass(frozen=True)
class Job:
    """Un job, y las reglas vigentes al momento de entregarlo.

    `vigente` trae, para `ENVIAR`, la lista de destinos permitidos **leída
    recién**. El agente la revalida antes de escribir: entre que el mensaje se
    encoló y que llegó hasta acá pudieron pasar minutos, y alguien pudo cerrar
    la lista desde el panel (R4).
    """

    id: str
    tipo: str
    payload: dict[str, Any]
    vigente: dict[str, Any] = field(default_factory=dict)


class SinTrabajo(Exception):
    """`204`. No es un error: es la respuesta normal la mayoría de las veces."""


class Pausado(Exception):
    """`423`. Pausa global o máquina pausada. Hay que esperar, no reintentar ya."""


class NoAutorizado(Exception):
    """`401`. El token no sirve: lo revocaron o la máquina se dio de baja.

    Se distingue de un error de red porque la respuesta es distinta: reintentar
    no lo va a arreglar, y el vendedor tiene que ver algo en su barra de menú.
    """


class Cliente:
    def __init__(self, base_url: str, token: str, *, timeout: float = TIMEOUT) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    async def cerrar(self) -> None:
        await self._http.aclose()

    async def registrar(
        self, *, version: str, diagnostico: dict[str, str], modo: str = ""
    ) -> dict[str, Any]:
        respuesta = await self._http.post(
            "/api/agente/registrar",
            json={"version": version, "diagnostico": diagnostico, "modo": modo},
        )
        self._revisar(respuesta)
        return respuesta.json()

    async def proximo_job(self) -> Job:
        """Un job, o `SinTrabajo`. Nunca `None`: el llamador no puede olvidarse."""
        respuesta = await self._http.get("/api/agente/jobs/proximo")
        if respuesta.status_code == 204:
            raise SinTrabajo
        self._revisar(respuesta)
        cuerpo = respuesta.json()
        return Job(
            id=cuerpo["id"],
            tipo=cuerpo["tipo"],
            payload=cuerpo["payload"],
            #  Un backend viejo no lo manda. Ausente = lista vacía = a nadie,
            #  que es el lado seguro.
            vigente=cuerpo.get("vigente") or {},
        )

    async def reportar(
        self,
        job_id: str,
        *,
        ok: bool,
        codigo: str | None = None,
        detalle: dict[str, Any] | None = None,
        raw: str = "",
        stderr: str = "",
        costo_usd: float = 0.0,
        borrador: bool = False,
    ) -> dict[str, Any]:
        respuesta = await self._http.post(
            f"/api/agente/jobs/{job_id}/resultado",
            json={
                "ok": ok,
                "codigo": codigo,
                "detalle": detalle or {},
                # Se mandan siempre, también en éxito (R5). Cortados, porque un
                # `raw` de megabytes no ayuda a nadie y sí llena la base.
                "raw": raw[-100_000:],
                "stderr": stderr[-100_000:],
                "costo_usd": costo_usd,
                # D30: sin esto, el backend daría por enviado un borrador.
                "borrador": borrador,
            },
        )
        self._revisar(respuesta)
        return respuesta.json()

    async def latido(self, diagnostico: dict[str, str] | None = None) -> dict[str, Any]:
        respuesta = await self._http.post(
            "/api/agente/latido", json={"diagnostico": diagnostico or {}}
        )
        self._revisar(respuesta)
        return respuesta.json()

    @staticmethod
    def _revisar(respuesta: httpx.Response) -> None:
        """Traduce los códigos que tienen significado propio.

        `423` y `401` no son "un error HTTP": son dos situaciones distintas que
        el bucle atiende de maneras distintas. Dejarlos como
        `HTTPStatusError` genérico obligaría a mirar el número en el bucle, que
        es donde se olvida.
        """
        if respuesta.status_code == 423:
            raise Pausado(respuesta.text)
        if respuesta.status_code == 401:
            raise NoAutorizado(respuesta.text)
        respuesta.raise_for_status()
