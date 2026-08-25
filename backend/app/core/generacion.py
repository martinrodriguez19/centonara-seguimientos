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
    #  Vinieron sin teléfono legible. Ya no se descartan: van a un `RESOLVER`
    #  que abre cada chat y lee el número real del panel de contacto — los
    #  contactos reales están agendados por nombre y el número no viene servido.
    sin_telefono: int = 0
    #  El número no está en `destinos_permitidos` (R4).
    no_permitidos: int = 0
    #  Fuera de la ventana de antigüedad: demasiado fresco o demasiado viejo.
    fuera_de_antiguedad: int = 0
    #  El job RESOLVER que quedó encolado con los sin-teléfono, si hubo.
    resolver_job: ObjectId | None = None
    #  Ya se habían encolado: el agente reportó dos veces el mismo `LISTAR`.
    repetido: bool = False

    @property
    def total(self) -> int:
        return len(self.jobs)


def _en_ventana(config: dict[str, Any], chat: dict[str, Any]) -> bool:
    """¿La antigüedad del chat cae en la ventana configurada?

    El caso de uso del sistema son los clientes que quedaron fríos: la ventana
    dice desde y hasta cuántos días de silencio vale la pena un seguimiento.
    """
    dias = int(chat.get("antiguedad_dias", 0))
    minimo = int(config.get("antiguedad_min_dias", 0))
    maximo = int(config.get("antiguedad_max_dias", 3650))
    return minimo <= dias <= maximo


async def _encolar_redaccion(
    base,
    *,
    corrida_id: ObjectId,
    maquina: str,
    chat: dict[str, Any],
    contacto_id: str,
    largo_maximo: int,
    momento: datetime,
) -> ObjectId:
    """Un `REDACTAR`, con el teléfono en el `contexto` y nunca en el payload."""
    return await cola.encolar(
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


async def encolar_redacciones(
    base,
    *,
    corrida_id: ObjectId,
    maquina: str,
    chats: list[dict[str, Any]],
    ahora: datetime | None = None,
) -> Encoladas:
    """Un `REDACTAR` por cada chat al que efectivamente se le podría escribir.

    Los chats sin teléfono no se descartan: se juntan en un único `RESOLVER`
    (una sola sesión de navegador para todos) que va a leer los números reales,
    y recién con el número se decide R4 y se redacta.
    """
    momento = ahora or datetime.now(UTC)
    resultado = Encoladas()

    # Idempotencia. Un `LISTAR` se puede reportar dos veces: el agente mandó el
    # resultado, se le cortó la red antes de leer la respuesta, y el barrido lo
    # devolvió a la cola. Sin esto, la segunda vez se encolan de nuevo los
    # veinte REDACTAR y se paga todo dos veces. El RESOLVER cuenta igual que un
    # REDACTAR para esto: cualquiera de los dos prueba que este LISTAR ya pasó.
    ya = await base["jobs"].find_one(
        {
            "corrida_id": corrida_id,
            "maquina": maquina,
            "tipo": {"$in": [str(cola.Tipo.REDACTAR), str(cola.Tipo.RESOLVER)]},
        }
    )
    if ya is not None:
        log.warning("redacciones_ya_encoladas", corrida=str(corrida_id), maquina=maquina)
        resultado.repetido = True
        return resultado

    config = await configuracion.obtener(base)
    largo_maximo = config.get("largo_maximo", 600)
    sin_numero: dict[str, dict[str, Any]] = {}

    for chat in chats:
        if not _en_ventana(config, chat):
            resultado.fuera_de_antiguedad += 1
            continue

        contacto_id = _a_e164(chat.get("contacto_telefono"))
        if contacto_id is None:
            # A resolver: el número vive en el panel de contacto de ese chat, y
            # eso lo lee código con selectores, no un modelo. Dos chats con el
            # mismo nombre quedan en uno — abrir "Juan" abre un solo chat — y
            # ese caso lo termina atajando la validación de nombres duplicados.
            resultado.sin_telefono += 1
            sin_numero[chat["contacto_nombre"]] = chat
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

        job = await _encolar_redaccion(
            base,
            corrida_id=corrida_id,
            maquina=maquina,
            chat=chat,
            contacto_id=contacto_id,
            largo_maximo=largo_maximo,
            momento=momento,
        )
        resultado.jobs.append(job)

    # Con la lista de destinos VACÍA no se resuelve nada: vacía significa a
    # nadie (R4), así que cualquier número que volviera se filtraría igual.
    # Mismo criterio que con las redacciones: no se trabaja para un mensaje
    # que no puede existir.
    if sin_numero and (config.get("destinos_permitidos") or []):
        resultado.resolver_job = await cola.encolar(
            base,
            tipo=cola.Tipo.RESOLVER,
            maquina=maquina,
            corrida_id=corrida_id,
            payload={"contactos": sorted(sin_numero)},
            # Los datos del chat esperan acá, del lado del backend, a que
            # vuelva el número. El agente sólo recibe los nombres.
            contexto={"chats": sin_numero},
            ahora=momento,
        )

    log.info(
        "redacciones_encoladas",
        corrida=str(corrida_id),
        maquina=maquina,
        encolados=resultado.total,
        sin_telefono=resultado.sin_telefono,
        a_resolver=len(sin_numero),
        no_permitidos=resultado.no_permitidos,
        fuera_de_antiguedad=resultado.fuera_de_antiguedad,
    )
    return resultado


async def encolar_redacciones_resueltas(
    base,
    *,
    job: dict[str, Any],
    contactos: list[dict[str, Any]],
    ahora: datetime | None = None,
) -> Encoladas:
    """Los números que trajo un `RESOLVER` se convierten en `REDACTAR`.

    `job` es el RESOLVER reportado: su `contexto` guarda los datos de cada chat
    (resumen, antigüedad) esperando el número. `contactos` es lo que el agente
    leyó: `{"nombre": ..., "telefono": ... | null, "motivo": ...}`.

    Idempotente por contacto: si el reporte llega dos veces, un `REDACTAR` con
    el mismo número en la misma corrida no se encola de nuevo.
    """
    momento = ahora or datetime.now(UTC)
    resultado = Encoladas()
    corrida_id = job["corrida_id"]
    maquina = job["maquina"]
    chats: dict[str, Any] = (job.get("contexto") or {}).get("chats") or {}

    config = await configuracion.obtener(base)
    largo_maximo = config.get("largo_maximo", 600)

    for contacto in contactos:
        nombre = str(contacto.get("nombre") or "")
        chat = chats.get(nombre)
        if chat is None:
            # Un nombre que no estaba en el pedido no tiene datos con qué
            # redactar. Se anota y no se inventa nada.
            log.warning("resolver_nombre_ajeno", nombre=nombre[:60], corrida=str(corrida_id))
            continue

        contacto_id = _a_e164(contacto.get("telefono"))
        if contacto_id is None:
            resultado.sin_telefono += 1
            continue

        if not configuracion.destino_permitido(config, contacto_id):
            resultado.no_permitidos += 1
            continue

        repetido = await base["jobs"].find_one(
            {
                "corrida_id": corrida_id,
                "maquina": maquina,
                "tipo": str(cola.Tipo.REDACTAR),
                "contexto.contacto_id": contacto_id,
            }
        )
        if repetido is not None:
            continue

        encolado = await _encolar_redaccion(
            base,
            corrida_id=corrida_id,
            maquina=maquina,
            chat=chat,
            contacto_id=contacto_id,
            largo_maximo=largo_maximo,
            momento=momento,
        )
        resultado.jobs.append(encolado)

    log.info(
        "redacciones_resueltas_encoladas",
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
