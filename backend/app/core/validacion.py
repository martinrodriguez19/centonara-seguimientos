"""De borradores a mensajes listos: dónde se juntan los guardrails y el triage.

Es el paso que corre después de que el modelo redactó y antes de que alguien
mire la pantalla. Por cada borrador decide una de tres cosas:

    guardrail violado  → DESCARTADO (motivo `rechazado`). No sale nunca.
    señal de triage    → RETENIDO.  Lo mira una persona.
    nada               → EN_ESPERA. Sale cuando el dueño apriete enviar.

**El orden importa.** Primero los guardrails: si un mensaje no puede salir, no
tiene sentido apartarlo para que alguien decida si sale. Y así el panel no le
pide una decisión a nadie sobre algo que ya está decidido.

Una decisión que parece un detalle y no lo es: **acá NO se verifica la ventana
horaria.** Generar a las ocho de la noche es perfectamente válido; lo que no se
puede es *enviar* fuera del horario. El chequeo de ventana corre cuando se
encola el envío, que es cuando importa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from app.core import configuracion, guardrails, mensajes, triage
from app.core.estados import Estado, Motivo
from app.logging import obtener_logger

log = obtener_logger(__name__)


@dataclass
class Resultado:
    """Qué pasó con una tanda de borradores."""

    en_espera: list[ObjectId] = field(default_factory=list)
    retenidos: list[ObjectId] = field(default_factory=list)
    rechazados: list[ObjectId] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.en_espera) + len(self.retenidos) + len(self.rechazados)

    @property
    def proporcion_retenida(self) -> float:
        """Para calibrar el triage con datos. El objetivo es 10 a 20%."""
        listos = len(self.en_espera) + len(self.retenidos)
        return len(self.retenidos) / listos if listos else 0.0


async def validar_corrida(
    base, corrida_id: ObjectId, *, ahora: datetime | None = None
) -> Resultado:
    """Pasa por las reglas todos los borradores de una corrida.

    Se procesan de a uno y en orden, no en paralelo, y eso es a propósito: el
    anti-duplicado y el tope diario miran lo que ya se aprobó. Si dos borradores
    para el mismo contacto se validaran a la vez, los dos verían "todavía no le
    escribimos" y los dos pasarían.
    """
    momento = ahora or datetime.now(UTC)
    resultado = Resultado()

    config = await configuracion.obtener(base)
    borradores = [
        m for m in await mensajes.de_la_corrida(base, corrida_id) if m["estado"] == Estado.BORRADOR
    ]
    if not borradores:
        return resultado

    # Se calcula una vez sobre la tanda entera: dos contactos con el mismo
    # nombre y distinto número sólo se ven mirando todo junto.
    repetidos = triage.nombres_repetidos(borradores)

    # Una lectura por máquina en vez de una por mensaje.
    cache_vendedores: dict[str, dict[str, Any] | None] = {}

    for borrador in borradores:
        maquina = borrador["maquina"]
        if maquina not in cache_vendedores:
            cache_vendedores[maquina] = await base["vendedores"].find_one({"maquina": maquina})

        await _validar_uno(
            base,
            borrador,
            config=config,
            vendedor=cache_vendedores[maquina],
            repetidos=repetidos,
            resultado=resultado,
            ahora=momento,
        )

    log.info(
        "corrida_validada",
        corrida=str(corrida_id),
        en_espera=len(resultado.en_espera),
        retenidos=len(resultado.retenidos),
        rechazados=len(resultado.rechazados),
        retencion=round(resultado.proporcion_retenida, 2),
    )
    return resultado


async def _validar_uno(
    base,
    borrador: dict[str, Any],
    *,
    config: dict[str, Any],
    vendedor: dict[str, Any] | None,
    repetidos: set[str],
    resultado: Resultado,
    ahora: datetime,
) -> None:
    mensaje_id = borrador["_id"]

    # 1. Guardrails. Sin la ventana horaria: se verifica al encolar el envío.
    violaciones = await guardrails.revisar(
        base,
        contacto_id=borrador["contacto_id"],
        texto=borrador["texto"],
        maquina=borrador["maquina"],
        config=config,
        vendedor=vendedor,
        verificar_ventana=False,
        ahora=ahora,
    )

    # El tope por corrida es la otra mitad de G4: protege de un `LISTAR` que
    # devuelve mil chats en vez de veinte. Se cuenta sobre lo ya aprobado.
    sin_lugar = guardrails.cabe_en_la_corrida(len(resultado.en_espera), config)
    if sin_lugar:
        violaciones = [*violaciones, sin_lugar]

    if violaciones:
        await mensajes.mover(
            base,
            mensaje_id,
            Estado.DESCARTADO,
            motivo=Motivo.RECHAZADO,
            senales=[str(v.guardrail) for v in violaciones],
            ahora=ahora,
        )
        resultado.rechazados.append(mensaje_id)
        return

    # 2. Triage. Sólo llega acá lo que sí puede salir.
    ya_le_escribimos = await mensajes.le_escribimos_hace_poco(
        base,
        borrador["contacto_id"],
        dias=config.get("dias_anti_duplicado", 7),
        ahora=ahora,
    )
    hallazgos = triage.evaluar(
        texto=borrador["texto"],
        resumen=borrador.get("resumen_ultimo", ""),
        contacto_id=borrador["contacto_id"],
        contacto_nombre=borrador.get("contacto_nombre", ""),
        quien_hablo_ultimo=borrador.get("quien_hablo_ultimo", "contacto"),
        config=config,
        ya_le_escribimos=ya_le_escribimos,
        nombre_repetido=_nombre_repetido(borrador, repetidos),
    )

    if hallazgos:
        await mensajes.mover(
            base,
            mensaje_id,
            Estado.RETENIDO,
            senales=[str(h.senal) for h in hallazgos],
            ahora=ahora,
        )
        resultado.retenidos.append(mensaje_id)
        return

    # 3. Nada que decir: sale cuando el dueño apriete enviar.
    await mensajes.mover(base, mensaje_id, Estado.EN_ESPERA, ahora=ahora)
    resultado.en_espera.append(mensaje_id)


def _nombre_repetido(borrador: dict[str, Any], repetidos: set[str]) -> bool:
    from app.core.triage import _sin_acentos

    return _sin_acentos((borrador.get("contacto_nombre") or "").strip()) in repetidos


async def revalidar_editado(
    base, mensaje_id: ObjectId, *, ahora: datetime | None = None
) -> list[guardrails.Violacion]:
    """Vuelve a pasar por los guardrails un mensaje que un humano editó.

    **Un humano también puede empeorar un mensaje.** Si escribe `{nombre}` a
    mano, o se pasa del largo, el texto editado no es más confiable que el del
    modelo — y el sistema no tiene forma de saber cuál de los dos lo escribió.

    Devuelve las violaciones. Si hay alguna, quien llama decide qué mostrar; el
    mensaje **no** se mueve de estado, porque lo que corresponde es que la
    persona lo corrija, no que se descarte lo que acaba de escribir.

    ⚠️ **No corre los seis guardrails, sólo dos.** Y no es una simplificación:
    el anti-duplicado y el tope diario cuentan los mensajes que están por salir,
    y este mensaje es uno de ellos — se encontraría a sí mismo y diría "ya le
    escribimos a este contacto". El tope y el duplicado ya se verificaron cuando
    el mensaje se aprobó; editar el texto no los vuelve a poner en juego.

    Lo que sí se revisa es lo que el editor pudo romper (el texto) y lo que pudo
    cambiar desde entonces (la lista de destinos).
    """
    momento = ahora or datetime.now(UTC)
    mensaje = await base["mensajes"].find_one({"_id": mensaje_id})
    if mensaje is None:
        raise mensajes.MensajeDesconocido(mensaje_id)

    config = await configuracion.obtener(base)
    violaciones: list[guardrails.Violacion] = []

    problema = guardrails.revisar_texto(
        mensaje["texto"], largo_maximo=config.get("largo_maximo", 600)
    )
    if problema:
        violaciones.append(problema)

    if not configuracion.destino_permitido(config, mensaje["contacto_id"]):
        violaciones.append(
            guardrails.Violacion(
                guardrails.Guardrail.DESTINO,
                f"{mensaje['contacto_id']} no está en los destinos permitidos",
            )
        )

    del momento
    return violaciones
