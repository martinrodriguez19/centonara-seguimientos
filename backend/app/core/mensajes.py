"""Los mensajes: crearlos, moverlos de estado, buscarlos.

Es el repositorio de la colección `mensajes`. La regla de qué transición existe
vive en `estados.py`; acá vive cómo se persiste.

**Toda transición pasa por `mover`.** No hay ningún otro lugar que escriba el
campo `estado`, y eso es a propósito: la máquina de estados sólo sirve si no se
puede sortear.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core import auditoria
from app.core.estados import Estado, Motivo, es_terminal, tomar_para_enviar, transicionar
from app.logging import obtener_logger

log = obtener_logger(__name__)

# Un borrador vence a las 24 h de generado (D3). Un mensaje que sale con
# contexto de anteayer es peor que uno que no sale.
HORAS_PARA_VENCER = 24


class MensajeDuplicado(Exception):
    """Ya existe un mensaje con esa clave de idempotencia.

    No es un error del sistema: es el sistema haciendo su trabajo. Pasa cuando
    un reintento vuelve a generar el mismo mensaje para el mismo contacto en la
    misma corrida.
    """


def clave_idempotencia(*, corrida_id: ObjectId, contacto_id: str, texto: str) -> str:
    """Identifica un mensaje por lo que lo hace único: a quién, en qué corrida, con qué texto.

    El texto entra en la clave a propósito. Si el dueño edita un borrador, es
    otro mensaje —y tiene que poder guardarse—; si un reintento regenera el
    mismo, la clave coincide y el índice único lo frena.
    """
    crudo = f"{corrida_id}|{contacto_id}|{texto}"
    return sha256(crudo.encode("utf-8")).hexdigest()


async def crear_borrador(
    base,
    *,
    corrida_id: ObjectId,
    maquina: str,
    contacto_id: str,
    contacto_nombre: str,
    texto: str,
    resumen_ultimo: str = "",
    quien_hablo_ultimo: str = "contacto",
    antiguedad_dias: int = 0,
    ahora: datetime | None = None,
) -> ObjectId:
    """Guarda un borrador recién redactado.

    Nace en `BORRADOR`: todavía no pasó por las reglas. Quien lo mueve a
    `EN_ESPERA` o `RETENIDO` es el paso de validación, no esto.
    """
    momento = ahora or datetime.now(UTC)
    clave = clave_idempotencia(corrida_id=corrida_id, contacto_id=contacto_id, texto=texto)

    documento = {
        "corrida_id": corrida_id,
        "maquina": maquina,
        "contacto_id": contacto_id,
        "contacto_nombre": contacto_nombre,
        "resumen_ultimo": resumen_ultimo,
        "quien_hablo_ultimo": quien_hablo_ultimo,
        "antiguedad_dias": antiguedad_dias,
        "texto": texto,
        "estado": str(Estado.BORRADOR),
        "motivo": None,
        "senales": [],
        "clave_idempotencia": clave,
        "sale_a_las": None,
        "intentos": 0,
        "editado_por": None,
        "creado_en": momento,
    }

    try:
        resultado = await base["mensajes"].insert_one(documento)
    except DuplicateKeyError as error:
        raise MensajeDuplicado(f"ya existe ese mensaje para {contacto_id}") from error

    return resultado.inserted_id


async def mover(
    base,
    mensaje_id: ObjectId,
    hasta: Estado,
    *,
    motivo: Motivo | None = None,
    quien: str = auditoria.SISTEMA,
    senales: list[str] | None = None,
    ahora: datetime | None = None,
) -> Estado:
    """Cambia el estado de un mensaje, validando la transición.

    **El único lugar del sistema que escribe `estado`.** Si aparece un
    `update_one({"estado": ...})` en otro archivo, es un hallazgo.

    La escritura es condicional al estado de origen: si entre que leímos y
    escribimos alguien más lo movió, no pisamos su cambio — devolvemos error en
    vez de dejar dos caminos pisándose.
    """
    momento = ahora or datetime.now(UTC)
    mensaje = await base["mensajes"].find_one({"_id": mensaje_id})
    if mensaje is None:
        raise MensajeDesconocido(mensaje_id)

    desde = Estado(mensaje["estado"])
    nuevo = (
        transicionar(desde, hasta, motivo)
        if hasta is not Estado.ENVIANDO
        else tomar_para_enviar(desde)
    )

    cambios: dict[str, Any] = {"estado": str(nuevo), "motivo": str(motivo) if motivo else None}
    if senales is not None:
        cambios["senales"] = senales

    resultado = await base["mensajes"].update_one(
        # El filtro incluye el estado de origen: es lo que hace que dos procesos
        # no puedan mover el mismo mensaje a la vez.
        {"_id": mensaje_id, "estado": str(desde)},
        {"$set": cambios},
    )
    if resultado.matched_count == 0:
        raise CarreraDeEstados(mensaje_id, desde)

    if nuevo is Estado.DESCARTADO:
        await auditoria.registrar(
            base,
            que=auditoria.Que.MENSAJE_DESCARTADO,
            quien=quien,
            mensaje_id=mensaje_id,
            detalle={"desde": str(desde), "motivo": str(motivo)},
            ahora=momento,
        )
    elif nuevo is Estado.ENVIADO:
        await auditoria.registrar(
            base,
            que=auditoria.Que.MENSAJE_ENVIADO,
            quien=quien,
            mensaje_id=mensaje_id,
            detalle={"contacto_id": mensaje["contacto_id"], "maquina": mensaje["maquina"]},
            ahora=momento,
        )

    return nuevo


class MensajeDesconocido(Exception):
    def __init__(self, mensaje_id: ObjectId) -> None:
        super().__init__(f"no existe el mensaje {mensaje_id}")


class CarreraDeEstados(Exception):
    """Alguien movió el mensaje entre que lo leímos y lo quisimos escribir."""

    def __init__(self, mensaje_id: ObjectId, esperado: Estado) -> None:
        self.mensaje_id = mensaje_id
        self.esperado = esperado
        super().__init__(f"el mensaje {mensaje_id} ya no está en {esperado}")


async def editar_texto(
    base, mensaje_id: ObjectId, texto: str, *, quien: str, ahora: datetime | None = None
) -> None:
    """Cambia el texto de un borrador.

    Sólo en `EN_ESPERA` o `RETENIDO`. Un mensaje que ya se está enviando o que
    ya salió no se edita: editarlo sería mentir sobre lo que se envió.

    **Quien llama tiene que revalidar después.** Un humano también puede
    empeorar un mensaje —escribir `{nombre}` a mano, pasarse de largo—, y el
    texto editado no es más confiable que el del modelo.
    """
    momento = ahora or datetime.now(UTC)
    mensaje = await base["mensajes"].find_one({"_id": mensaje_id})
    if mensaje is None:
        raise MensajeDesconocido(mensaje_id)

    estado = Estado(mensaje["estado"])
    if estado not in (Estado.EN_ESPERA, Estado.RETENIDO):
        raise NoSePuedeEditar(estado)

    nueva_clave = clave_idempotencia(
        corrida_id=mensaje["corrida_id"], contacto_id=mensaje["contacto_id"], texto=texto
    )
    await base["mensajes"].update_one(
        {"_id": mensaje_id},
        {"$set": {"texto": texto, "clave_idempotencia": nueva_clave, "editado_por": quien}},
    )
    await auditoria.registrar(
        base,
        que=auditoria.Que.MENSAJE_EDITADO,
        quien=quien,
        mensaje_id=mensaje_id,
        ahora=momento,
    )


class NoSePuedeEditar(Exception):
    def __init__(self, estado: Estado) -> None:
        self.estado = estado
        super().__init__(f"un mensaje en {estado} no se edita")


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------


async def de_la_corrida(base, corrida_id: ObjectId) -> list[dict[str, Any]]:
    return (
        await base["mensajes"].find({"corrida_id": corrida_id}).sort("creado_en", 1).to_list(None)
    )


async def le_escribimos_hace_poco(
    base, contacto_id: str, *, dias: int, ahora: datetime | None = None
) -> bool:
    """¿Este contacto recibió algo nuestro en los últimos `dias`? (guardrail G5)

    Cuenta los que **salieron** y los que están por salir. Uno encolado todavía
    no llegó, pero va a llegar: si no contara, una corrida disparada dos veces
    seguidas le mandaría dos mensajes a la misma persona.
    """
    corte = (ahora or datetime.now(UTC)) - timedelta(days=dias)
    return (
        await base["mensajes"].count_documents(
            {
                "contacto_id": contacto_id,
                "creado_en": {"$gte": corte},
                "estado": {
                    "$in": [str(Estado.EN_ESPERA), str(Estado.ENVIANDO), str(Estado.ENVIADO)]
                },
            },
            limit=1,
        )
        > 0
    )


async def enviados_hoy(base, maquina: str, *, ahora: datetime | None = None) -> int:
    """Cuántos salieron o están por salir hoy desde esta máquina (guardrail G4)."""
    momento = ahora or datetime.now(UTC)
    medianoche = momento.replace(hour=0, minute=0, second=0, microsecond=0)
    return await base["mensajes"].count_documents(
        {
            "maquina": maquina,
            "creado_en": {"$gte": medianoche},
            "estado": {"$in": [str(Estado.EN_ESPERA), str(Estado.ENVIANDO), str(Estado.ENVIADO)]},
        }
    )


async def vencer_viejos(base, *, ahora: datetime | None = None) -> int:
    """Descarta los borradores de más de 24 h (D3).

    Corre en APScheduler. Alcanza a los que están esperando y a los retenidos
    que nadie resolvió — **los retenidos vencen, no se liberan solos**. Liberar
    por defecto invertiría el sentido del triage: son justamente los casos donde
    un error cuesta caro.
    """
    momento = ahora or datetime.now(UTC)
    corte = momento - timedelta(hours=HORAS_PARA_VENCER)

    vivos = (
        await base["mensajes"]
        .find(
            {
                "creado_en": {"$lt": corte},
                "estado": {
                    "$in": [str(Estado.BORRADOR), str(Estado.RETENIDO), str(Estado.EN_ESPERA)]
                },
            }
        )
        .to_list(None)
    )

    vencidos = 0
    for mensaje in vivos:
        try:
            await mover(
                base, mensaje["_id"], Estado.DESCARTADO, motivo=Motivo.VENCIDO, ahora=momento
            )
            vencidos += 1
        except CarreraDeEstados:
            # Alguien lo movió mientras barríamos. Que gane el otro: si lo
            # liberaron o lo vetaron recién, esa decisión es más nueva que ésta.
            continue

    if vencidos:
        log.info("mensajes_vencidos", cantidad=vencidos, horas=HORAS_PARA_VENCER)
    return vencidos


async def contar_por_estado(base, corrida_id: ObjectId) -> dict[str, int]:
    """Cuántos hay en cada estado. Lo usa la pantalla de revisión."""
    conteo: dict[str, int] = {}
    for mensaje in await de_la_corrida(base, corrida_id):
        conteo[mensaje["estado"]] = conteo.get(mensaje["estado"], 0) + 1
    return conteo


async def tasa_de_edicion(base, corrida_id: ObjectId) -> float:
    """Qué proporción de borradores reescribió el humano.

    Es la métrica de calidad del prompt, y la más importante de todas: si el
    dueño reescribe el 80%, el sistema no está aportando valor y hay que saberlo
    antes de que lo diga él.
    """
    mensajes = await de_la_corrida(base, corrida_id)
    if not mensajes:
        return 0.0
    editados = sum(1 for m in mensajes if m.get("editado_por"))
    return editados / len(mensajes)


__all__ = [
    "CarreraDeEstados",
    "Estado",
    "MensajeDesconocido",
    "MensajeDuplicado",
    "Motivo",
    "NoSePuedeEditar",
    "clave_idempotencia",
    "contar_por_estado",
    "crear_borrador",
    "de_la_corrida",
    "editar_texto",
    "enviados_hoy",
    "es_terminal",
    "le_escribimos_hace_poco",
    "mover",
    "tasa_de_edicion",
    "vencer_viejos",
]
