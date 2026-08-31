"""`RESOLVER`: leer el número real de los chats que vinieron sin teléfono.

Existe porque los contactos reales están agendados por nombre: el `LISTAR` ve
"Corralón San Justo" en la lista y el número no está a la vista. Sin esto, esos
chats — que son casi todos — se descartaban.

Es **determinístico y de sólo lectura**: código con los mismos selectores del
motor de envío, en el navegador dedicado, sin modelo y sin costo por token.
Por cada nombre: abrir el chat, confirmar que no es un grupo, y leer el número
del panel de contacto. Lo que no se puede leer con certeza vuelve como `null`
con su motivo — deducir un número acá es escribirle a otra persona después.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agente.adaptadores.pagina import ErrorDeSelector, PaginaNoCargo
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# La misma cota que el backend (`PayloadResolver`). Última barrera local.
MAX_CONTACTOS = 50


@dataclass(frozen=True)
class Resultado:
    ok: bool
    codigo: str | None = None
    detalle: dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    stderr: str = ""
    costo_usd: float = 0.0

    def a_reporte(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "codigo": self.codigo,
            "detalle": self.detalle,
            "raw": self.raw,
            "stderr": self.stderr,
            "costo_usd": self.costo_usd,
        }


async def resolver(pagina, *, contactos: list[str]) -> Resultado:
    """Abre cada chat por nombre y lee su número. Nunca escribe nada."""
    nombres = [str(n).strip() for n in contactos[:MAX_CONTACTOS] if str(n).strip()]
    if not nombres:
        return Resultado(False, "ERROR_INESPERADO", {"motivo": "sin contactos que resolver"})

    try:
        await pagina.abrir_whatsapp()
        if not await pagina.sesion_iniciada():
            return Resultado(False, "SESION_CAIDA", {"motivo": "WhatsApp Web está pidiendo el QR"})
    except PaginaNoCargo as error:
        #  Transitorio: la página no terminó de cargar. Reintenta como TIMEOUT
        #  en vez de frenar la corrida entera con SELECTOR_ROTO.
        return Resultado(False, "TIMEOUT", {"motivo": str(error), "contactos": []})
    except ErrorDeSelector as error:
        #  `contactos` vacío y presente: el backend lee siempre la misma forma.
        return Resultado(False, "SELECTOR_ROTO", {"motivo": str(error), "contactos": []})

    leidos: list[dict[str, Any]] = []
    for nombre in nombres:
        try:
            leidos.append(await _uno(pagina, nombre))
        except ErrorDeSelector as error:
            # El DOM cambió a mitad de camino. Lo ya leído se reporta igual:
            # es trabajo hecho, y el código le dice al backend que frene.
            log.error("resolver_selector_roto", nombre=nombre[:60], motivo=str(error))
            return Resultado(
                False,
                "SELECTOR_ROTO",
                {
                    "motivo": str(error),
                    "contactos": leidos,
                    "resueltos_antes_de_fallar": len(leidos),
                },
            )
        except Exception as error:
            # Un tropiezo con UN contacto —la página que se redibujó en el
            # momento justo, un timeout suelto— no tira el lote entero: ese
            # contacto queda sin número, con el motivo anotado, y se sigue.
            # Antes de esto, un solo "not attached to the DOM" mataba el job
            # tres veces seguidas y la corrida quedaba sin borradores.
            log.warning("resolver_contacto_fallo", nombre=nombre[:60], error=str(error)[:200])
            leidos.append({"nombre": nombre, "telefono": None, "motivo": "error_al_abrir"})

    resueltos = sum(1 for c in leidos if c["telefono"])
    log.info("resolver_ok", pedidos=len(nombres), resueltos=resueltos)
    return Resultado(
        True,
        detalle={
            "contactos": leidos,
            "pedidos": len(nombres),
            "resueltos": resueltos,
            "sin_numero": len(leidos) - resueltos,
        },
    )


async def _uno(pagina, nombre: str) -> dict[str, Any]:
    """Un contacto: su número, o el motivo por el que no.

    ⚠️ Abre con `buscar_verificado` y no con `buscar_contacto`, y no es una
    optimización: acá la fila verificada (A3) es LA REGLA, no un escalón
    opcional. `RESOLVER` no tiene la comparación de identidad que protege a
    `ENVIAR` — el número que se lea acá queda guardado como el del contacto, y
    puede hacer pasar la verificación de un envío posterior contra el chat de
    otra persona. Si ninguna fila contiene el nombre buscado, la respuesta
    correcta es `None`, no el número del primer chat de la lista.
    """
    if not await pagina.buscar_verificado(nombre):
        log.info(
            "resolver_chat_no_abre",
            nombre=nombre[:60],
            motivo=getattr(pagina, "motivo_no_abrio", None),
        )
        return {"nombre": nombre, "telefono": None, "motivo": "chat_no_abre"}

    if await pagina.es_grupo():
        # Un grupo nunca recibe un seguimiento comercial; su "número" tampoco.
        return {"nombre": nombre, "telefono": None, "motivo": "es_grupo"}

    numero = await pagina.resolver_numero()
    if numero is None:
        # El panel no mostró un número legible. `null` es la respuesta honesta.
        return {"nombre": nombre, "telefono": None, "motivo": "numero_no_legible"}

    return {"nombre": nombre, "telefono": numero, "motivo": None}
