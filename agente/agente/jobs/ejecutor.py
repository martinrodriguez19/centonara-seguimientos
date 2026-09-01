"""A qué función va cada job.

Hasta acá el bucle se construía sin ejecutor y usaba el de por defecto, que
responde "este agente no sabe ejecutar X". Servía mientras los ejecutores no
existían; ahora existen tres de los cuatro y hay que enchufarlos.

**Lo que este módulo no hace es decidir política.** Traduce un `Job` a una
llamada y una llamada a un reporte. Qué se reintenta lo decide `cola.Codigo` en
el backend; qué se hace con un borrador lo decide el triage; a quién se le puede
escribir lo decide `destinos_permitidos`.

`ENVIAR` es el caso incómodo y está tratado aparte, por dos motivos:

- **Contra qué se ejecuta lo decide la máquina; qué se hace, el panel (D32).**
  Con `--simulado` (desarrollo) se corre contra la página en memoria, sin
  navegador. Operativo, va contra WhatsApp Web — y si el mensaje queda como
  borrador o se envía lo dice el `modo` del payload, que puso el botón del
  panel. La máquina no tiene una perilla propia: la tuvo, y fue la causa del
  incidente del 26/08.
- **Los selectores no están verificados contra WhatsApp Web real.** Mientras
  `selectores.VERIFICADO` sea `None`, un envío real se rechaza. No es una fase
  pendiente: es la precondición concreta que falta, y el guard desaparece solo
  el día que alguien la cumpla.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from agente.adaptadores import selectores
from agente.adaptadores.simulada import PaginaSimulada
from agente.cliente import Job
from agente.diagnostico import Diagnostico
from agente.jobs import borradores as borradores_job
from agente.jobs import enviar as enviar_job
from agente.jobs import listar as listar_job
from agente.jobs import redactar as redactar_job
from agente.jobs import resolver as resolver_job
from agente.logging import obtener_logger

log = obtener_logger(__name__)


def construir(
    *,
    claude_bin: str,
    device_id: str,
    carpeta: Path,
    modo: str,
    diagnosticar: Callable[[], Diagnostico],
    abrir_pagina: Callable[[], Awaitable[Any]] | None = None,
    asegurar_navegador: Callable[[], Awaitable[Any]] | None = None,
) -> Callable[[Job], Awaitable[dict[str, Any]]]:
    """Devuelve el ejecutor que espera `Bucle`, ya atado a esta máquina.

    `abrir_pagina` es de dónde sale el navegador para `ENVIAR` y `RESOLVER`. En
    `simulado` no hace falta y no se usa. Se inyecta porque cómo conseguir la
    página es una decisión aparte (D24: el navegador dedicado, ver
    `adaptadores/conexion.py`) y el despachador no tiene por qué saberla.

    `asegurar_navegador` es lo que se corre antes de un `LISTAR`: la extensión
    vive en el Chrome del vendedor, y si él lo cerró no hay extensión para
    nadie. Se inyecta por el mismo motivo, y porque en los tests nadie quiere
    que se abra un navegador de verdad.
    """

    async def ejecutar(job: Job) -> dict[str, Any]:
        carga = job.payload or {}

        if job.tipo == "LISTAR":
            # ⚠️ Antes de pagarle a un modelo. Con el Chrome del vendedor
            # cerrado, el prompt gasta la llamada para volver con
            # `browser_no_disponible` — y la cola lo reintenta tres veces.
            if asegurar_navegador is not None:
                listo = await asegurar_navegador()
                if not listo.utilizable:
                    log.error("chrome_del_vendedor_no_disponible", detalle=listo.detalle)
                    return {
                        "ok": False,
                        "codigo": "ERROR_INESPERADO",
                        "detalle": {
                            "motivo": (
                                "no se pudo abrir el Chrome de esta máquina, que es donde "
                                f"vive la extensión: {listo.detalle}"
                            )
                        },
                    }

            resultado = await listar_job.listar(
                n_chats=carga.get("n_chats", 20),
                run_id=str(carga.get("run_id", "")),
                antiguedad_min_dias=carga.get("antiguedad_min_dias", 0),
                antiguedad_max_dias=carga.get("antiguedad_max_dias", 3650),
                estrategia=str(carga.get("estrategia", "recientes")),
                barrido_hasta_dias=carga.get("barrido_hasta_dias", 3650),
                ya_vistos=list(carga.get("ya_vistos", [])),
                device_id=device_id,
                claude_bin=claude_bin,
                carpeta=carpeta,
            )
            return resultado.a_reporte()

        if job.tipo == "BORRADORES":
            # El pase único: leer el chat y dejar el borrador ahí mismo, con la
            # extensión, sin enviar nada. Igual que LISTAR, corre en el Chrome
            # del vendedor — y con el mismo guard: sin navegador no se le paga
            # a un modelo para que descubra que no hay navegador.
            if asegurar_navegador is not None:
                listo = await asegurar_navegador()
                if not listo.utilizable:
                    log.error("chrome_del_vendedor_no_disponible", detalle=listo.detalle)
                    return {
                        "ok": False,
                        "codigo": "ERROR_INESPERADO",
                        "detalle": {
                            "motivo": (
                                "no se pudo abrir el Chrome de esta máquina, que es donde "
                                f"vive la extensión: {listo.detalle}"
                            )
                        },
                    }

            resultado = await borradores_job.dejar_borradores(
                n_chats=carga.get("n_chats", 6),
                run_id=str(carga.get("run_id", "")),
                antiguedad_min_dias=carga.get("antiguedad_min_dias", 0),
                antiguedad_max_dias=carga.get("antiguedad_max_dias", 3650),
                estrategia=str(carga.get("estrategia", "recientes")),
                barrido_hasta_dias=carga.get("barrido_hasta_dias", 3650),
                ya_vistos=list(carga.get("ya_vistos", [])),
                no_escribir=list(carga.get("no_escribir", [])),
                solo_numeros=list(carga.get("solo_numeros", [])),
                contexto_empresa=str(carga.get("contexto_empresa", "")),
                largo_maximo=carga.get("largo_maximo", 600),
                device_id=device_id,
                claude_bin=claude_bin,
                carpeta=carpeta,
            )
            return resultado.a_reporte()

        if job.tipo == "RESOLVER":
            # Sólo lectura sobre el navegador dedicado. No pasa por el guard de
            # selectores verificados: no escribe nada, y si el DOM cambió lo
            # reporta con SELECTOR_ROTO, que es información y no un riesgo.
            if modo == "simulado":
                pagina: Any = PaginaSimulada()
            elif abrir_pagina is None:
                return {
                    "ok": False,
                    "codigo": "ERROR_INESPERADO",
                    "detalle": {"motivo": "no se configuró cómo conectarse al navegador"},
                }
            else:
                pagina = await abrir_pagina()
            resultado = await resolver_job.resolver(
                pagina, contactos=list(carga.get("contactos", []))
            )
            return resultado.a_reporte()

        if job.tipo == "REDACTAR":
            resultado = await redactar_job.redactar(
                contacto_nombre=str(carga.get("contacto_nombre", "")),
                resumen=str(carga.get("resumen", "")),
                quien_hablo_ultimo=str(carga.get("quien_hablo_ultimo", "contacto")),
                antiguedad_dias=carga.get("antiguedad_dias", 0),
                largo_maximo=carga.get("largo_maximo", 600),
                contexto_empresa=str(carga.get("contexto_empresa", "")),
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
            return await _enviar(job, carga, modo=modo, abrir_pagina=abrir_pagina)

        return {
            "ok": False,
            "codigo": "ERROR_INESPERADO",
            "detalle": {"motivo": f"tipo de job desconocido: {job.tipo}"},
        }

    return ejecutar


async def _enviar(
    job: Job,
    carga: dict[str, Any],
    *,
    modo: str,
    abrir_pagina: Callable[[], Awaitable[Any]] | None,
) -> dict[str, Any]:
    """Escribe un mensaje, o explica por qué no.

    Lo único que decide acá es **contra qué página** corre el motor. El resto
    —la verificación de identidad, los topes, si se aprieta enviar— es de
    `jobs/enviar.py`, que ya lo tiene probado.
    """
    # ⚠️ R4, segunda verificación. La lista viene de `job.vigente`, leída por el
    # backend **al entregar el job** y no al encolarlo: entre una cosa y la otra
    # pueden pasar minutos, y alguien pudo cerrarla desde el panel.
    #
    # Ausente significa lista vacía, que significa a nadie. Un backend que no la
    # manda no habilita nada.
    permitidos = job.vigente.get("destinos_permitidos") or []

    # Qué se hace con el mensaje —borrador o envío— lo decide el panel y viaja
    # en el payload (D32). La máquina no tiene voz: la perilla por máquina fue
    # la causa del 26/08. Ausente = "prueba", el lado que no envía (R2).
    modo_pedido = str(carga.get("modo", "prueba"))

    if modo == "simulado":
        # Desarrollo (`--simulado`): no toca ningún navegador, corre contra la
        # página en memoria.
        pagina: Any = PaginaSimulada()
    else:
        if selectores.VERIFICADO is None and modo_pedido == "real":
            # ⚠️ El guard no es una fase pendiente: es la precondición que falta.
            # Los selectores nunca se probaron contra WhatsApp Web, así que un
            # envío real es la primera vez que confiaríamos en algo no
            # verificado. Desaparece solo cuando alguien complete la fecha.
            log.error("selectores_sin_verificar", modo=modo)
            return {
                "ok": False,
                "codigo": "SELECTOR_ROTO",
                "detalle": {
                    "motivo": (
                        "los selectores de WhatsApp Web nunca se verificaron contra una "
                        "sesión real. Correr `--sonda` y verificarlos antes de enviar"
                    )
                },
            }

        if abrir_pagina is None:
            log.error("sin_forma_de_abrir_el_navegador", modo=modo)
            return {
                "ok": False,
                "codigo": "ERROR_INESPERADO",
                "detalle": {"motivo": "no se configuró cómo conectarse al navegador"},
            }
        pagina = await abrir_pagina()

    resultado = await enviar_job.enviar(
        pagina,
        contacto_id=str(carga.get("contacto_id", "")),
        contacto_nombre=str(carga.get("contacto_nombre", "")),
        texto=str(carga.get("texto", "")),
        modo=modo_pedido,
        destinos_permitidos=permitidos,
    )
    return resultado.a_reporte()
