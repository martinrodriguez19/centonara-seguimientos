"""La vigía de la sesión dedicada: que su vencimiento se vea ANTES de fallar.

El motor de envío escribe desde un navegador propio con una **segunda** sesión
de WhatsApp vinculada a la línea del vendedor (D24). Esa sesión expira sola, el
vendedor no la ve en ningún lado, y hasta ahora nadie se enteraba de que había
vencido hasta que una corrida fallaba con `SESION_CAIDA` — está reconocido en
`conexion.py` como lo que había que medir.

Esto la mira de verdad: cada tanto abre la página dedicada, corre el mismo
`sesion_iniciada()` del motor, y deja el resultado en el chequeo
`whatsapp_sesion` del diagnóstico que ya viaja en cada latido. El panel lo
muestra y alerta "re-vincular" con tiempo, no después de una corrida cancelada.

**No abre navegador por latido**: el latido manda el resultado cacheado de la
última revisión. El navegador se abre una vez cada `INTERVALO_VIGIA` — y es el
mismo navegador persistente del motor, así que "abrir" es casi siempre mirar
una página que ya está.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from agente import diagnostico
from agente.adaptadores.pagina import PaginaNoCargo
from agente.bucle import Estado as EstadoBucle
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# Cada cuánto se revisa la sesión de verdad. Horas y no minutos: la sesión
# expira en días, y cada revisión toca el navegador del motor.
INTERVALO_VIGIA = 6 * 3600.0

NOMBRE = "whatsapp_sesion"


async def revisar_sesion(abrir_pagina: Callable[[], Awaitable[Any]]) -> diagnostico.Chequeo:
    """Una revisión: abre la página dedicada y pregunta por la sesión.

    Sólo dos respuestas son seguras y por eso son las únicas que afirman algo:
    la lista de chats a la vista (`ok`) y el QR a la vista (`falla`). Todo lo
    demás —la página que no cargó, el navegador que no abrió— es `n/a` con el
    motivo: afirmar "sesión caída" por un tropiezo transitorio dispararía la
    alerta de re-vincular sin necesidad.
    """
    try:
        pagina = await abrir_pagina()
        await pagina.abrir_whatsapp()
        iniciada = await pagina.sesion_iniciada()
    except PaginaNoCargo as error:
        return diagnostico.Chequeo(
            NOMBRE, diagnostico.Estado.NO_APLICA, f"la página no cargó: {error}"[:200], "D24"
        )
    except Exception as error:
        return diagnostico.Chequeo(
            NOMBRE,
            diagnostico.Estado.NO_APLICA,
            f"no se pudo abrir el navegador dedicado: {error}"[:200],
            "D24",
        )

    if iniciada:
        return diagnostico.Chequeo(NOMBRE, diagnostico.Estado.OK, "sesión dedicada activa", "D24")
    return diagnostico.Chequeo(
        NOMBRE,
        diagnostico.Estado.FALLA,
        "WhatsApp Web pide el QR: correr --vincular en esta máquina",
        "D24",
    )


async def vigilar(
    abrir_pagina: Callable[[], Awaitable[Any]],
    estado: EstadoBucle,
    *,
    intervalo: float = INTERVALO_VIGIA,
    parar: asyncio.Event | None = None,
    dormir: Callable[[float], Awaitable[None]] | None = None,
    vueltas: int | None = None,
) -> int:
    """Revisa al arrancar y después cada `intervalo`, en paralelo al bucle.

    Escribe el resultado en `estado.diagnostico`, que es lo que el latido manda
    cada 30 segundos — la revisión es cara y esporádica, el reporte es gratis y
    constante.

    Convive con los envíos sin coordinarse, a propósito: sólo navega si la
    lista de chats no está a la vista (mismo criterio que el motor) y no toca
    ningún chat. `vueltas` acota para los tests, como en `latir`.
    """
    fin = parar or asyncio.Event()
    hechas = 0

    while not fin.is_set():
        chequeo = await revisar_sesion(abrir_pagina)
        estado.diagnostico = diagnostico.con_chequeo(estado.diagnostico, chequeo)
        hechas += 1
        log.info("sesion_dedicada_revisada", estado=str(chequeo.estado), detalle=chequeo.detalle)

        if vueltas is not None and hechas >= vueltas:
            break
        #  Corta apenas alguien pide parar, sin esperar a que venza el
        #  intervalo — con 6 h de intervalo, un `sleep` plano retendría el
        #  apagado. `dormir` inyectado gana, para los tests.
        if dormir is not None:
            await dormir(intervalo)
        else:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(fin.wait(), timeout=intervalo)

    return hechas
