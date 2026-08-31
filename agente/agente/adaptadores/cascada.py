"""El motor de contingencias: probar alternativas en orden, y anotar cuál ganó.

Existe por la corrida del 28/08: los tres `ENVIAR` fallaron con `CHAT_NO_ABRE`
y quedaron tres hipótesis abiertas que no se pudieron distinguir. La respuesta
no es reescribir la ruta que hoy existe, sino ponerle alternativas detrás: la
ruta actual es siempre el primer escalón, intacto, y las demás corren sólo
cuando la anterior devuelve "no pude".

Dos propiedades que son el punto del diseño:

- **Cada intento deja rastro.** El escalón que resolvió va al `registro`, que
  viaja en el `detalle` del reporte y queda persistido en el documento del job
  en Mongo. Después de correr en producción, una agregación sobre
  `jobs.detalle.cascadas.<cascada>.gano` dice cuál funcionó de verdad — y ése
  se promueve a primera opción reordenando la lista, sin reescribir nada.
- **Un escalón que revienta no tira la cascada.** Se anota y se sigue con el
  siguiente. La excepción no se pierde: queda logueada con su tipo.

Lo que este motor NO hace: saltear las dos verificaciones que no se negocian.
La comparación de identidad por número y el chequeo de campo vacío corren
*después* de que cualquier escalón abra el chat, en `jobs/enviar.py`, y ningún
escalón las relaja. Una cascada que insiste más en abrir chats sube el riesgo
de abrir el equivocado — esos dos pasos son justo lo que lo contiene.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, TypeVar

from agente.logging import obtener_logger

log = obtener_logger(__name__)

T = TypeVar("T")

Estrategia = tuple[str, Callable[[], Awaitable[T]]]


async def en_cascada(
    cascada: str,
    estrategias: Sequence[Estrategia],
    *,
    registro: dict[str, Any],
) -> Any:
    """Prueba las estrategias en orden. La primera que sirve gana.

    "Sirve" = devuelve algo verdadero. Un `False`/`None` es "no pude, probá la
    siguiente"; una excepción también, pero se loguea con su tipo porque no es
    lo mismo "no está" que "reventó".

    `registro` se manda en el `detalle` del reporte: es lo que después permite
    ver en producción cuál escalón resolvió.
    """
    intentadas: list[str] = []
    for nombre, estrategia in estrategias:
        intentadas.append(nombre)
        try:
            resultado = await estrategia()
        except Exception as error:
            log.info(
                "cascada_escalon_roto",
                cascada=cascada,
                escalon=nombre,
                excepcion=type(error).__name__,
                mensaje=str(error)[:200],
            )
            continue
        if resultado:
            log.info("cascada_resuelta", cascada=cascada, escalon=nombre, intentadas=intentadas)
            registro[cascada] = {"gano": nombre, "intentadas": intentadas}
            return resultado
        log.info("cascada_escalon_sin_exito", cascada=cascada, escalon=nombre)
    log.warning("cascada_agotada", cascada=cascada, intentadas=intentadas)
    registro[cascada] = {"gano": None, "intentadas": intentadas}
    return None
