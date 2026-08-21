"""El puente entre `LISTAR` y `REDACTAR`, y entre `REDACTAR` y un borrador.

Sin esto los dos ejecutores del agente no se tocan: un resultado de `LISTAR` se
guardaba y ahí moría, y `Tipo.REDACTAR` no lo encolaba nadie. Una corrida leía
los chats y se detenía.

El recorrido completo queda así, y cada flecha vive en un lugar distinto:

    panel                    -> LISTAR            (corridas.disparar)
    LISTAR   -> N REDACTAR                        (acá: encolar_redacciones)
    REDACTAR -> un borrador en BORRADOR           (acá: guardar_borrador)
    borradores -> EN_ESPERA | RETENIDO            (validacion.validar_corrida)

El problema que resuelve `encolar_redacciones` y que no es evidente: `REDACTAR`
**no lleva teléfono**. No lo necesita —redacta sin navegador y no envía nada— y
`PayloadRedactar` lo prohíbe con `extra="forbid"`. Pero el borrador que sale de
su resultado sí necesita saber a quién es, y el triage necesita el `contacto_id`
para revisar identidad y anti-duplicado. Por eso el número viaja en el
`contexto` del job, que se queda de este lado: el agente sólo recibe `payload`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from app.core import cola, configuracion, mensajes, triage
from app.core.contactos import NumeroInvalido, normalizar
from app.core.estados import Estado
from app.logging import obtener_logger

log = obtener_logger(__name__)


@dataclass
class Encoladas:
    """Qué pasó con los chats que leyó una máquina."""

    jobs: list[ObjectId] = field(default_factory=list)
    #  Vino sin teléfono legible. El prompt pide explícitamente no deducirlo, así
    #  que esto es una respuesta correcta y no un error del modelo.
    sin_telefono: int = 0
    #  El número no está en `destinos_permitidos` (R4).
    no_permitidos: int = 0
    #  Ya se habían encolado: el agente reportó dos veces el mismo `LISTAR`.
    repetido: bool = False

    @property
    def total(self) -> int:
        return len(self.jobs)


async def encolar_redacciones(
    base,
    *,
    corrida_id: ObjectId,
    maquina: str,
    chats: list[dict[str, Any]],
    ahora: datetime | None = None,
) -> Encoladas:
    """Un `REDACTAR` por cada chat al que efectivamente se le podría escribir."""
    momento = ahora or datetime.now(UTC)
    resultado = Encoladas()

    # Idempotencia. Un `LISTAR` se puede reportar dos veces: el agente mandó el
    # resultado, se le cortó la red antes de leer la respuesta, y el barrido lo
    # devolvió a la cola. Sin esto, la segunda vez se encolan de nuevo los
    # veinte REDACTAR y se paga todo dos veces.
    ya = await base["jobs"].find_one(
        {"corrida_id": corrida_id, "maquina": maquina, "tipo": str(cola.Tipo.REDACTAR)}
    )
    if ya is not None:
        log.warning("redacciones_ya_encoladas", corrida=str(corrida_id), maquina=maquina)
        resultado.repetido = True
        return resultado

    config = await configuracion.obtener(base)
    largo_maximo = config.get("largo_maximo", 600)

    for chat in chats:
        contacto_id = _a_e164(chat.get("contacto_telefono"))
        if contacto_id is None:
            resultado.sin_telefono += 1
            continue

        # ⚠️ R4, y acá es además una decisión de plata. Redactar para un número
        # al que el sistema no puede escribirle cuesta una llamada al modelo y
        # produce un borrador que nunca va a poder salir. Con la lista en los
        # tres números de prueba, saltearlos es la diferencia entre pagar tres
        # redacciones y pagar veinte.
        #
        # Lista vacía significa a nadie, así que una corrida sin destinos
        # configurados no encola nada — y el conteo lo deja dicho.
        if not configuracion.destino_permitido(config, contacto_id):
            resultado.no_permitidos += 1
            continue

        job = await cola.encolar(
            base,
            tipo=cola.Tipo.REDACTAR,
            maquina=maquina,
            corrida_id=corrida_id,
            payload={
                "contacto_nombre": chat["contacto_nombre"],
                "resumen": chat["ultimo_mensaje_resumen"],
                "quien_hablo_ultimo": chat.get("quien_hablo_ultimo", "contacto"),
                "antiguedad_dias": chat.get("antiguedad_dias", 0),
                "largo_maximo": largo_maximo,
            },
            contexto={
                "contacto_id": contacto_id,
                "contacto_nombre": chat["contacto_nombre"],
                "resumen": chat["ultimo_mensaje_resumen"],
                "quien_hablo_ultimo": chat.get("quien_hablo_ultimo", "contacto"),
                "antiguedad_dias": chat.get("antiguedad_dias", 0),
            },
            ahora=momento,
        )
        resultado.jobs.append(job)

    log.info(
        "redacciones_encoladas",
        corrida=str(corrida_id),
        maquina=maquina,
        encolados=resultado.total,
        sin_telefono=resultado.sin_telefono,
        no_permitidos=resultado.no_permitidos,
    )
    return resultado


async def guardar_borrador(
    base,
    *,
    job: dict[str, Any],
    detalle: dict[str, Any],
    ahora: datetime | None = None,
) -> ObjectId | None:
    """Convierte el resultado de un `REDACTAR` en un mensaje.

    Nace en `BORRADOR` y ahí se queda: quien lo mueve a `EN_ESPERA` o `RETENIDO`
    es `validacion.validar_corrida()`, que corre sobre la tanda entera porque
    necesita verla junta —dos contactos con el mismo nombre sólo se detectan
    así—. La excepción es `sin_contexto`, que no tiene texto que validar.
    """
    momento = ahora or datetime.now(UTC)
    contexto = job.get("contexto") or {}
    contacto_id = contexto.get("contacto_id")
    if not contacto_id:
        # Un job de REDACTAR sin contexto no se puede convertir en nada: no
        # sabemos a quién era. Falla explícito (R2) en vez de inventar un
        # destinatario.
        log.error("redactar_sin_contexto_guardado", job=str(job.get("_id")))
        return None

    sin_contexto = detalle.get("status") == "sin_contexto"
    texto = "" if sin_contexto else str(detalle.get("texto", ""))

    try:
        mensaje_id = await mensajes.crear_borrador(
            base,
            corrida_id=job["corrida_id"],
            maquina=job["maquina"],
            contacto_id=contacto_id,
            contacto_nombre=contexto.get("contacto_nombre", ""),
            texto=texto,
            resumen_ultimo=contexto.get("resumen", ""),
            quien_hablo_ultimo=contexto.get("quien_hablo_ultimo", "contacto"),
            antiguedad_dias=contexto.get("antiguedad_dias", 0),
            ahora=momento,
        )
    except mensajes.MensajeDuplicado:
        # Mismo contacto, misma corrida, mismo texto. El reporte llegó dos veces.
        log.warning("borrador_duplicado", contacto=contacto_id, corrida=str(job["corrida_id"]))
        return None

    if sin_contexto:
        # ⚠️ No pasa por la validación, y es a propósito: no tiene texto, así que
        # el guardrail G3 lo descartaría por vacío y se perdería el motivo. Va
        # derecho a RETENIDO, que es donde una persona lo puede escribir a mano
        # y soltarlo, o descartarlo.
        await mensajes.mover(
            base,
            mensaje_id,
            Estado.RETENIDO,
            senales=[str(triage.Senal.SIN_CONTEXTO)],
            quien=job["maquina"],
            ahora=momento,
        )
        log.info("borrador_sin_contexto", contacto=contacto_id, motivo=detalle.get("motivo", ""))

    return mensaje_id


def _a_e164(crudo: Any) -> str | None:
    """El teléfono normalizado, o `None` si no hay uno usable.

    `None` no es un error: el prompt de `LISTAR` pide explícitamente devolver
    `null` antes que deducir un número, porque un número inventado hace que el
    sistema le escriba a otra persona. Un número ilegible se trata igual.
    """
    if not crudo:
        return None
    try:
        return normalizar(str(crudo))
    except NumeroInvalido as error:
        log.warning("telefono_ilegible", crudo=str(crudo)[:30], motivo=error.motivo)
        return None
