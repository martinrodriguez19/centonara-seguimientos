"""A qué función va cada job.

Hasta acá el bucle se construía sin ejecutor y usaba el de por defecto, que
responde "este agente no sabe ejecutar X". Servía mientras los ejecutores no
existían; ahora existen tres de los cuatro y hay que enchufarlos.

**Lo que este módulo no hace es decidir política.** Traduce un `Job` a una
llamada y una llamada a un reporte. Qué se reintenta lo decide `cola.Codigo` en
el backend; qué se hace con un borrador lo decide el triage; a quién se le puede
escribir lo decide `destinos_permitidos`.

`ENVIAR` es el caso incómodo y está tratado aparte: el adaptador real de
WhatsApp Web —`adaptadores/whatsapp_web.py`— todavía no existe, así que sólo se
puede ejecutar contra la página simulada. Un `ENVIAR` real se **rechaza
explícitamente** en vez de fallar raro más adelante: es la regla R2, y el modo
por defecto de todo el sistema es el que no manda nada.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from agente.cliente import Job
from agente.diagnostico import Diagnostico
from agente.jobs import listar as listar_job
from agente.jobs import redactar as redactar_job
from agente.logging import obtener_logger

log = obtener_logger(__name__)


def construir(
    *,
    claude_bin: str,
    device_id: str,
    carpeta: Path,
    modo: str,
    diagnosticar: Callable[[], Diagnostico],
) -> Callable[[Job], Awaitable[dict[str, Any]]]:
    """Devuelve el ejecutor que espera `Bucle`, ya atado a esta máquina."""

    async def ejecutar(job: Job) -> dict[str, Any]:
        carga = job.payload or {}

        if job.tipo == "LISTAR":
            resultado = await listar_job.listar(
                n_chats=carga.get("n_chats", 20),
                run_id=str(carga.get("run_id", "")),
                device_id=device_id,
                claude_bin=claude_bin,
                carpeta=carpeta,
            )
            return resultado.a_reporte()

        if job.tipo == "REDACTAR":
            resultado = await redactar_job.redactar(
                contacto_nombre=str(carga.get("contacto_nombre", "")),
                resumen=str(carga.get("resumen", "")),
                quien_hablo_ultimo=str(carga.get("quien_hablo_ultimo", "contacto")),
                antiguedad_dias=carga.get("antiguedad_dias", 0),
                largo_maximo=carga.get("largo_maximo", 600),
                claude_bin=claude_bin,
                carpeta=carpeta,
            )
            return resultado.a_reporte()

        if job.tipo == "DIAGNOSTICO":
            revision = diagnosticar()
            return {
                "ok": revision.puede_enviar,
                "codigo": None if revision.puede_enviar else "ERROR_INESPERADO",
                "detalle": revision.a_dict(),
            }

        if job.tipo == "ENVIAR":
            return _todavia_no_hay_navegador(modo)

        return {
            "ok": False,
            "codigo": "ERROR_INESPERADO",
            "detalle": {"motivo": f"tipo de job desconocido: {job.tipo}"},
        }

    return ejecutar


def _todavia_no_hay_navegador(modo: str) -> dict[str, Any]:
    """`ENVIAR` sin adaptador real.

    El motor (`jobs/enviar.py`) está escrito y probado contra la página
    simulada; lo que falta es la implementación de `Pagina` sobre Playwright.
    Mientras tanto esto reporta un fallo claro, con el modo incluido, en vez de
    dejar que el job reviente con un `ImportError` a mitad de una corrida.
    """
    log.error("enviar_sin_adaptador", modo=modo)
    return {
        "ok": False,
        "codigo": "ERROR_INESPERADO",
        "detalle": {
            "motivo": "falta adaptadores/whatsapp_web.py: el envío real llega en la fase 4",
            "modo": modo,
        },
    }
