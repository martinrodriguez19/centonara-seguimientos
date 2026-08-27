"""La configuración operativa: topes, ventana, palabras, destinos permitidos.

Vive en la base y no en variables de entorno, por dos motivos:

- El cliente tiene que poder cambiar un tope o agregar una palabra del rubro sin
  pedirnos nada y sin un despliegue.
- Cambiarla queda registrado en `auditoria`, con quién y cuándo. Una variable de
  entorno cambia sin dejar rastro.

Un solo documento, con `_id: "unica"`. No es elegante y es correcto: no hay dos
configuraciones posibles, y un documento único hace imposible el bug de leer la
equivocada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.logging import obtener_logger

log = obtener_logger(__name__)

ID = "unica"

# Los valores con los que arranca una base vacía. Conservadores a propósito:
# es más fácil aflojar un tope cuando hay datos que explicar por qué salieron
# doscientos mensajes el primer día.
POR_DEFECTO: dict[str, Any] = {
    "_id": ID,
    "pausa_global": False,
    # ⚠️ A quién puede escribirle el sistema (R4). Vacía = a nadie.
    #
    # Arranca vacía y no en ["*"] a propósito: el estado seguro tiene que ser el
    # que se obtiene sin hacer nada. Abrirla es un acto deliberado.
    "destinos_permitidos": [],
    "n_chats_por_defecto": 20,
    # La ventana de antigüedad de los chats que vale la pena seguir: el caso de
    # uso del sistema son los clientes que quedaron fríos, no el que escribió
    # hoy. En días desde el último mensaje; fuera de la ventana no se redacta.
    # ⚠️ Sólo aplica al modo "recientes": el barrido es su propia estrategia.
    "antiguedad_min_dias": 0,
    "antiguedad_max_dias": 90,
    # Cómo elige chats una corrida de generación (D27):
    #   recientes — los de arriba de la lista, dentro de la ventana de arriba.
    #   barrido   — desde el fondo del historial hacia hoy, N por corrida, con
    #               cursor por máquina y sin repetir contactados. Es el modo
    #               para recuperar a los clientes viejos que quedaron sin
    #               recontactar.
    "modo_lectura": "recientes",
    # Lo que el dueño quiere que el redactor sepa de su empresa: qué vende, qué
    # ofrece, promociones, tono. Viaja al REDACTAR como dato acotado y el prompt
    # lo enmarca como referencia — no como instrucciones. Vacío = no se usa.
    "contexto_empresa": "",
    "tope_diario_maquina": 20,
    "tope_por_corrida": 25,
    "largo_maximo": 600,
    "dias_anti_duplicado": 7,
    "ventana": {"inicio": "09:00", "fin": "19:00", "dias": [1, 2, 3, 4, 5]},
    "pausa_entre_envios_s": [45, 180],
    "palabras_conflicto": [
        "reclamo",
        "problema",
        "cancelar",
        "factura",
        "no me interesa",
        "abogado",
        "devolución",
        "garantía",
        "defectuoso",
        "estafa",
        "denuncia",
    ],
}

# Campos que existieron y se eliminaron. `obtener()` los limpia del documento
# vivo la primera vez que los ve: `actualizar()` valida contra `POR_DEFECTO`,
# así que un campo huérfano no se puede sacar desde el panel.
#   - palabras_comerciales: D29 — todos los chats se consideran comerciales.
RETIRADOS = ("palabras_comerciales",)

TODOS = "*"


async def obtener(base) -> dict[str, Any]:
    """La configuración. La crea con los valores por defecto si no existe.

    Idempotente: `$setOnInsert` sólo escribe cuando el documento no estaba, así
    que llamarla no pisa lo que el cliente haya cambiado desde el panel.
    """
    documento = await base["configuracion"].find_one_and_update(
        {"_id": ID},
        {"$setOnInsert": POR_DEFECTO},
        upsert=True,
        return_document=True,
    )
    huerfanos = [campo for campo in RETIRADOS if campo in documento]
    if huerfanos:
        await base["configuracion"].update_one(
            {"_id": ID}, {"$unset": {campo: "" for campo in huerfanos}}
        )
        for campo in huerfanos:
            del documento[campo]
        log.info("configuracion_campos_retirados", campos=huerfanos)
    return documento


async def actualizar(base, cambios: dict[str, Any]) -> dict[str, Any]:
    """Cambia campos de la configuración.

    No valida acá qué se puede cambiar: eso es del endpoint, que sabe quién lo
    está pidiendo. Esto sólo escribe y deja la marca de cuándo.
    """
    prohibidos = set(cambios) - (set(POR_DEFECTO) - {"_id"})
    if prohibidos:
        raise ValueError(f"campos que no existen en la configuración: {sorted(prohibidos)}")

    # ⚠️ Asegurar los valores por defecto ANTES de escribir.
    #
    # Sin esto, el `upsert` de abajo crea un documento con SÓLO el campo que se
    # cambió, y todo lo demás queda ausente. Es un bug silencioso y feo: la
    # primera persona que toca un tope desde el panel en una base nueva se lleva
    # puestas las palabras del triage, y el triage deja de retener nada sin que
    # aparezca ningún error en ningún lado.
    await obtener(base)

    await base["configuracion"].update_one(
        {"_id": ID},
        {"$set": {**cambios, "actualizado_en": datetime.now(UTC)}},
    )
    log.info("configuracion_actualizada", campos=sorted(cambios))
    return await obtener(base)


async def restablecer(base) -> dict[str, Any]:
    """Vuelve la configuración a los valores de fábrica (D28).

    Es parte de entregar el sistema: lo que importa acá es que
    `destinos_permitidos` vuelva a estar **vacío** —que significa a nadie—, para
    que el cliente no herede los números de prueba de quien lo configuró.

    Reemplaza el documento entero en vez de hacer `$set` campo por campo: un
    campo que alguien agregó a mano y ya no existe en `POR_DEFECTO` tiene que
    desaparecer, no sobrevivir al borrado.
    """
    await base["configuracion"].replace_one({"_id": ID}, dict(POR_DEFECTO), upsert=True)
    log.warning("configuracion_restablecida")
    return await obtener(base)


def destino_permitido(configuracion: dict[str, Any], contacto_id: str) -> bool:
    """¿El sistema puede escribirle a este número? (regla R4)

    Se verifica en el backend al encolar y **otra vez en el agente antes de
    escribir**. La duplicación no es porque el agente desconfíe del backend: es
    porque un job puede quedar encolado y ejecutarse minutos después, y en el
    medio la lista pudo cambiar. La segunda verificación es contra el paso del
    tiempo.

    Lista vacía significa **a nadie**, no "a todos". Es la diferencia entre un
    sistema que arranca seguro y uno que arranca abierto porque nadie lo
    configuró todavía.
    """
    permitidos = configuracion.get("destinos_permitidos") or []
    if TODOS in permitidos:
        return True
    return contacto_id in permitidos


async def esta_pausado(base) -> bool:
    """El kill switch. Mientras esté puesto, no se entrega ningún job."""
    configuracion = await obtener(base)
    return bool(configuracion.get("pausa_global"))


async def pausar(base, *, pausado: bool, quien: str) -> None:
    """Aprieta o suelta el kill switch, y lo deja anotado.

    El dueño va a usar este botón con las manos temblando algún día. Que quede
    registrado quién lo apretó no es para auditar a nadie: es para poder
    reconstruir qué pasó esa tarde.
    """
    await base["configuracion"].update_one(
        {"_id": ID},
        {"$set": {"pausa_global": pausado, "actualizado_en": datetime.now(UTC)}},
        upsert=True,
    )
    log.warning("kill_switch", pausado=pausado, quien=quien)
