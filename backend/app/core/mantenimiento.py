"""Vaciar el sistema para entregárselo a un cliente (D28).

Un sistema que se probó durante días queda con corridas, borradores, mensajes
enviados a números de prueba y una memoria de teléfonos que son de otra
persona. Entregarlo así obliga al cliente a mirar datos que no son suyos, y
—peor— deja los destinos de prueba cargados en la lista que decide a quién se
le puede escribir.

**Qué NO se borra, y no es un olvido:**

- **La auditoría.** El rol de Mongo del backend no tiene `remove` sobre esa
  colección: la inmutabilidad del registro no depende de que el código se porte
  bien. Lo que sí queda es un evento `DATOS_BORRADOS` con los conteos, que es
  la marca de dónde empieza la historia del cliente.
- **Las máquinas**, salvo que se pida. Darlas de baja revoca sus tokens y
  obliga a reinstalar cada Mac; casi nunca es lo que se quiere al entregar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core import auditoria, configuracion
from app.logging import obtener_logger

log = obtener_logger(__name__)

# Todo lo que produce el uso del sistema. La configuración va aparte porque es
# lo que alguien cargó a mano, y las máquinas aparte porque borrarlas obliga a
# reinstalar.
COLECCIONES = ("corridas", "jobs", "mensajes", "telefonos")


async def empezar_de_cero(
    base,
    *,
    quien: str,
    restablecer_configuracion: bool = True,
    borrar_maquinas: bool = False,
    ahora: datetime | None = None,
) -> dict[str, Any]:
    """Deja el sistema como recién instalado. Devuelve qué borró.

    El orden importa: primero se cuenta y se borra, y **al final** se registra
    en la auditoría. Al revés, el evento quedaría antes que el borrado en la
    línea de tiempo y no se entendería qué pasó primero.
    """
    momento = ahora or datetime.now(UTC)
    borrados: dict[str, int] = {}

    for coleccion in COLECCIONES:
        resultado = await base[coleccion].delete_many({})
        borrados[coleccion] = resultado.deleted_count

    if borrar_maquinas:
        resultado = await base["vendedores"].delete_many({})
        borrados["vendedores"] = resultado.deleted_count
    else:
        # Las máquinas quedan, pero sin rastro de lo que hicieron: el cursor
        # del barrido (D27) y el último diagnóstico son del uso anterior.
        await base["vendedores"].update_many(
            {}, {"$unset": {"barrido": "", "diagnostico": "", "ultimo_latido": ""}}
        )
        borrados["vendedores"] = 0

    if restablecer_configuracion:
        # ⚠️ Lo más importante de todo esto: vuelve `destinos_permitidos` a
        # vacío, que significa **a nadie**. Entregar el sistema con los números
        # de prueba de otra persona cargados es entregarlo apuntando a ellos.
        await configuracion.restablecer(base)

    await auditoria.registrar(
        base,
        que=auditoria.Que.DATOS_BORRADOS,
        quien=quien,
        detalle={
            "borrados": borrados,
            "configuracion_restablecida": restablecer_configuracion,
            "maquinas_borradas": borrar_maquinas,
        },
        ahora=momento,
    )
    log.warning("datos_borrados", quien=quien, **borrados)

    return {
        "borrados": borrados,
        "configuracion_restablecida": restablecer_configuracion,
        "maquinas_borradas": borrar_maquinas,
    }
