"""Colecciones e índices. Declaración e inicialización idempotente.

Dos mitades, a propósito:

- **La declaración** (`COLECCIONES`) es una estructura de datos. Se puede leer,
  comparar y testear sin una base de datos al lado.
- **La aplicación** (`inicializar`) es una función corta que la ejecuta contra
  Mongo. Correrla dos veces no rompe nada.

Los índices no son decoración. Dos de ellos son reglas de negocio disfrazadas:
`clave_idempotencia` es lo que impide que un reintento mande el mensaje dos
veces, y el índice de la cola es lo que hace que `findOneAndUpdate` no entregue
el mismo job a dos agentes.

    uv run python -m app.core.esquema      # crea todo, o confirma que ya está
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, DESCENDING, IndexModel

from app.logging import obtener_logger

log = obtener_logger(__name__)

DIA = 24 * 60 * 60

# Cuánto se guarda un job terminado. Después de eso, lo que importa vive en
# `auditoria`, que no vence. Un mes alcanza para depurar un incidente y evita
# que la colección crezca para siempre con `raw` y `stderr` de corridas viejas.
RETENCION_JOBS_DIAS = 30

# Cuánto se guarda el resumen de una conversación de un cliente (D1). Ver
# `purgar_resumenes` abajo: esto NO se implementa con un índice TTL.
RETENCION_RESUMEN_DIAS = 90


@dataclass(frozen=True)
class Indice:
    """Un índice, en forma declarativa."""

    claves: tuple[tuple[str, int], ...]
    unico: bool = False
    expira_en_segundos: int | None = None
    parcial: dict | None = None

    @property
    def nombre(self) -> str:
        """Nombre estable y legible. Si cambia, Mongo crearía uno nuevo al lado."""
        return "_".join(
            f"{campo}_{1 if orden == ASCENDING else -1}" for campo, orden in self.claves
        )

    def a_modelo(self) -> IndexModel:
        opciones: dict = {"name": self.nombre}
        if self.unico:
            opciones["unique"] = True
        if self.expira_en_segundos is not None:
            opciones["expireAfterSeconds"] = self.expira_en_segundos
        if self.parcial is not None:
            opciones["partialFilterExpression"] = self.parcial
        return IndexModel(list(self.claves), **opciones)


@dataclass(frozen=True)
class Coleccion:
    nombre: str
    indices: tuple[Indice, ...] = field(default_factory=tuple)
    porque: str = ""


COLECCIONES: tuple[Coleccion, ...] = (
    Coleccion(
        nombre="vendedores",
        porque="Una fila por máquina. Alta y baja desde el panel: la cantidad es variable.",
        indices=(
            # `maquina` es el identificador con el que se autentica el agente.
            # Único a nivel de base: dos máquinas con el mismo nombre serían dos
            # agentes peleándose la misma cola.
            Indice(claves=(("maquina", ASCENDING),), unico=True),
            # El agente se autentica con un token; se busca por su hash y no
            # recorriendo las máquinas. Es la consulta que corre cada 10
            # segundos por cada máquina, así que el índice no es opcional.
            Indice(claves=(("token_hash", ASCENDING),), unico=True),
            Indice(claves=(("activo", ASCENDING),)),
        ),
    ),
    Coleccion(
        nombre="corridas",
        porque="Una por cada vez que el dueño aprieta el botón.",
        indices=(Indice(claves=(("creada_en", DESCENDING),)),),
    ),
    Coleccion(
        nombre="mensajes",
        porque="El borrador y su recorrido hasta que sale o se descarta.",
        indices=(
            # ⚠️ Lo que impide que un reintento mande el mismo mensaje dos veces.
            # Es una regla de negocio implementada como restricción de la base:
            # un `if` en el código se puede saltear con una condición de carrera,
            # un índice único no.
            Indice(claves=(("clave_idempotencia", ASCENDING),), unico=True),
            # Anti-duplicado: "¿le escribimos a este contacto en los últimos
            # siete días?" (guardrail G5).
            Indice(claves=(("contacto_id", ASCENDING), ("creado_en", DESCENDING))),
            # La pantalla de revisión: los mensajes de una corrida, por estado.
            Indice(claves=(("corrida_id", ASCENDING), ("estado", ASCENDING))),
            # El barrido de vencimientos: qué sigue vivo y tiene más de 24 h (D3).
            Indice(claves=(("estado", ASCENDING), ("creado_en", ASCENDING))),
        ),
    ),
    Coleccion(
        nombre="jobs",
        porque="La cola. Sin Redis: Mongo alcanza para este volumen (D7).",
        indices=(
            # ⚠️ EL índice de la cola. Es la consulta que corre cada 10 segundos
            # por cada máquina, y la que `findOneAndUpdate` usa para entregar un
            # job a un solo agente. El orden de los campos importa: se filtra por
            # estado y máquina, y se ordena por disponible_desde.
            Indice(
                claves=(
                    ("estado", ASCENDING),
                    ("maquina", ASCENDING),
                    ("disponible_desde", ASCENDING),
                )
            ),
            Indice(claves=(("corrida_id", ASCENDING),)),
            # Los jobs terminados se borran solos al mes. Los que siguen vivos no
            # tienen `terminado_en`, y Mongo no toca los documentos donde el
            # campo del índice TTL no es una fecha: la cola no se vacía sola.
            Indice(
                claves=(("terminado_en", ASCENDING),),
                expira_en_segundos=RETENCION_JOBS_DIAS * DIA,
            ),
            # G4 — un solo ENVIAR VIVO por mensaje. Cierra la ventana entre el
            # encadenado automático y el botón de envío (dos jobs para el mismo
            # mensaje): en modo borrador lo tapaba `CAMPO_NO_VACIO`; en modo
            # real no había red. "Vivo" = `terminado_en` sigue en null — al
            # terminar (listo o fallido) el job sale del índice, y reenviar un
            # mensaje que falló sigue siendo posible. Regla de negocio como
            # restricción de la base: un `if` en el código se saltea con una
            # condición de carrera, un índice único no.
            Indice(
                claves=(("payload.mensaje_id", ASCENDING),),
                unico=True,
                parcial={
                    "tipo": "ENVIAR",
                    "payload.mensaje_id": {"$exists": True},
                    "terminado_en": {"$type": "null"},
                },
            ),
        ),
    ),
    Coleccion(
        nombre="auditoria",
        porque="Lo que salió, quién lo tocó y cuándo. Sólo inserción, y no vence (R5).",
        indices=(
            Indice(claves=(("cuando", DESCENDING),)),
            Indice(claves=(("mensaje_id", ASCENDING),)),
        ),
    ),
    Coleccion(
        nombre="configuracion",
        porque="Un solo documento, con _id 'unica'. Topes, palabras y destinos permitidos.",
    ),
    Coleccion(
        nombre="telefonos",
        porque=(
            "La memoria de lo que resolvió el agente (D27): el nombre con el que un contacto "
            "figura en WhatsApp y el número real que se leyó de su panel. Evita volver a abrir "
            "el chat en cada corrida del barrido."
        ),
        indices=(
            # Es la clave del upsert y la de la consulta: un contacto por
            # máquina. Único, porque dos filas para el mismo nombre serían dos
            # números distintos para la misma persona y no habría cómo elegir.
            Indice(claves=(("maquina", ASCENDING), ("nombre", ASCENDING)), unico=True),
        ),
    ),
)


async def inicializar(base) -> dict[str, list[str]]:
    """Crea colecciones e índices. Idempotente: correrla dos veces no rompe nada.

    `create_indexes` no falla si el índice ya existe con la misma definición, y
    `create_collection` sí falla si la colección ya está — por eso una se
    intenta y la otra se consulta primero.

    Devuelve qué índices tiene cada colección al terminar, que es lo que mira
    el test.
    """
    existentes = set(await base.list_collection_names())
    resultado: dict[str, list[str]] = {}

    for coleccion in COLECCIONES:
        if coleccion.nombre not in existentes:
            await base.create_collection(coleccion.nombre)
            log.info("coleccion_creada", coleccion=coleccion.nombre)

        if coleccion.indices:
            await base[coleccion.nombre].create_indexes([i.a_modelo() for i in coleccion.indices])

        indices = await base[coleccion.nombre].index_information()
        resultado[coleccion.nombre] = sorted(indices)

    log.info("esquema_listo", colecciones=len(COLECCIONES))
    return resultado


async def purgar_resumenes(base, *, dias: int = RETENCION_RESUMEN_DIAS) -> int:
    """Borra el resumen de las conversaciones más viejas que `dias` (D1).

    ⚠️ **Por qué esto no es un índice TTL.** Un TTL de Mongo borra el
    *documento* entero, no un campo. Acá hay que borrar el resumen de la
    conversación de un cliente —que es dato de un tercero— y **conservar** el
    mensaje que nosotros mandamos, que es dato propio y es la defensa ante un
    reclamo. Son retenciones distintas sobre el mismo documento, y eso el TTL
    no lo sabe hacer.

    Así que es un `$unset` programado. Lo corre APScheduler una vez por día.

    La documentación decía "TTL de 90 días sobre el resumen". Era incorrecto:
    con un TTL se habría borrado el mensaje enviado junto con el resumen.
    """
    corte = datetime.now(UTC) - timedelta(days=dias)
    resultado = await base["mensajes"].update_many(
        {"creado_en": {"$lt": corte}, "resumen_ultimo": {"$ne": None}},
        {"$unset": {"resumen_ultimo": ""}},
    )
    if resultado.modified_count:
        log.info("resumenes_purgados", cantidad=resultado.modified_count, dias=dias)
    return resultado.modified_count


async def _principal() -> None:
    from app import db
    from app.config import obtener_configuracion

    config = obtener_configuracion()
    db.conectar(config)
    try:
        for coleccion, indices in (await inicializar(db.obtener_base())).items():
            print(f"{coleccion:15} {', '.join(indices)}")
    finally:
        db.desconectar()


if __name__ == "__main__":
    asyncio.run(_principal())
