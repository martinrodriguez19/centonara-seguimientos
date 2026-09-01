"""Máquina de estados de un mensaje.

Es la pieza central del sistema: todo lo demás la sirve. Siete estados y un
campo `motivo`, en vez de los doce del plan anterior — lo que allá eran estados
distintos (rechazado, vetado, vencido, fallido) acá es el porqué de uno solo.

```
  BORRADOR ──▶ EN_ESPERA ──▶ ENVIANDO ──▶ ENVIADO
      │ │           ▲  │          │└─────▶ BORRADOR_DEJADO   (modo borradores, D30)
      │ └───────────│──│──────────────────▶ BORRADOR_DEJADO  (pase único, 01/09)
      │             │  │          └──(falla, quedan intentos)──▶ EN_ESPERA
      ▼             │  ▼
  RETENIDO ─(libera)┘  └──────────────────▶ DESCARTADO
      │                                          ▲
      └──────────(veto / vence / rechaza)────────┘
```

**Una transición que no está declarada acá abajo no existe.** No hay camino
alternativo, no hay atajo, y no hay forma de escribir un estado a mano en la
base sin pasar por `transicionar`. Si algo del sistema necesita una transición
nueva, se agrega a la tabla con su test — no se sortea la tabla.
"""

from __future__ import annotations

from enum import StrEnum


class Estado(StrEnum):
    """Los siete estados. `StrEnum` para que se guarden legibles en Mongo."""

    BORRADOR = "BORRADOR"
    """El modelo lo redactó, todavía no pasó las reglas."""

    RETENIDO = "RETENIDO"
    """El triage encendió una señal. Necesita decisión humana."""

    EN_ESPERA = "EN_ESPERA"
    """Validado. Sale cuando el dueño apriete enviar."""

    ENVIANDO = "ENVIANDO"
    """Un agente lo tomó y está operando el navegador."""

    ENVIADO = "ENVIADO"
    """Salió y se confirmó en el hilo. Terminal."""

    BORRADOR_DEJADO = "BORRADOR_DEJADO"
    """Quedó escrito como borrador en el WhatsApp del vendedor, sin enviarse
    (D30). Lo manda el vendedor a mano, o no lo manda. Terminal: el sistema no
    vuelve a tocar ese chat — un Envío posterior lo abortaría con
    `CAMPO_NO_VACIO`, que es el circuito esperado, no un error."""

    DESCARTADO = "DESCARTADO"
    """No sale nunca. El porqué está en `motivo`. Terminal."""


class Motivo(StrEnum):
    """Por qué un mensaje quedó en `DESCARTADO`.

    Existe para que la pantalla de historial pueda decir qué pasó sin que haya
    que inferirlo, y para poder contar cuántos se vetaron a mano contra cuántos
    frenó el sistema — que es la diferencia entre un triage que sirve y uno que
    molesta.
    """

    RECHAZADO = "rechazado"
    """Violó un guardrail. Nunca pudo salir."""

    VETADO = "vetado"
    """Un humano lo frenó desde el panel."""

    VENCIDO = "vencido"
    """Pasaron 24 h desde que se generó. El contexto ya no aplica (D3)."""

    FALLIDO = "fallido"
    """Se agotaron los intentos, o falló con un código que no se reintenta."""

    SIN_CONFIRMAR = "sin_confirmar"
    """Se apretó enviar y no apareció en el hilo. **Dispara alerta.**"""

    CANCELADO = "cancelado"
    """Una persona canceló la corrida antes de que saliera (D31)."""


TERMINALES: frozenset[Estado] = frozenset(
    {Estado.ENVIADO, Estado.BORRADOR_DEJADO, Estado.DESCARTADO}
)

# La tabla. Es la única fuente de verdad sobre qué transición existe.
#
# Ojo con lo que NO está:
#   - BORRADOR nunca va directo a ENVIANDO. Tiene que pasar por las reglas.
#   - RETENIDO nunca va directo a ENVIANDO. Alguien tiene que liberarlo primero.
#   - ENVIADO no vuelve. Un mensaje que salió, salió.
#   - DESCARTADO no resucita: si hay que mandar ese mensaje, se genera uno nuevo.
TRANSICIONES: dict[Estado, frozenset[Estado]] = {
    # BORRADOR → BORRADOR_DEJADO es del pase único (01/09): cuando el reporte
    # del agente llega, el texto YA está escrito en el chat — el estado sólo se
    # pone al día con la realidad. No pasa por EN_ESPERA porque no hay envío
    # que esperar: en esta ruta no envía nadie.
    Estado.BORRADOR: frozenset(
        {Estado.RETENIDO, Estado.EN_ESPERA, Estado.BORRADOR_DEJADO, Estado.DESCARTADO}
    ),
    Estado.RETENIDO: frozenset({Estado.EN_ESPERA, Estado.DESCARTADO}),
    Estado.EN_ESPERA: frozenset({Estado.ENVIANDO, Estado.DESCARTADO}),
    # ENVIANDO vuelve a EN_ESPERA cuando falla algo reintentable: el agente no
    # pudo abrir el chat, se cayó la sesión. El mensaje sigue vivo y lo toma
    # otro intento. BORRADOR_DEJADO es el final del modo borradores (D30).
    Estado.ENVIANDO: frozenset(
        {Estado.ENVIADO, Estado.BORRADOR_DEJADO, Estado.EN_ESPERA, Estado.DESCARTADO}
    ),
    Estado.ENVIADO: frozenset(),
    Estado.BORRADOR_DEJADO: frozenset(),
    Estado.DESCARTADO: frozenset(),
}


class TransicionInvalida(Exception):
    """Se intentó una transición que no está en la tabla.

    No se atrapa para "seguir de largo". Si aparece, hay un bug en quien la
    pidió: el sistema falla cerrado (R2) y el mensaje se queda donde estaba.
    """

    def __init__(self, desde: Estado, hasta: Estado, detalle: str = "") -> None:
        self.desde = desde
        self.hasta = hasta
        razon = "es terminal" if desde in TERMINALES else "no es una transición declarada"
        super().__init__(f"{desde} → {hasta}: {razon}. {detalle}".strip())


class MotivoRequerido(Exception):
    """Se intentó descartar sin decir por qué.

    `DESCARTADO` sin `motivo` deja un mensaje que nadie puede explicar el día
    que un cliente pregunte. La auditoría existe justamente para responder eso.
    """


def puede(desde: Estado, hasta: Estado) -> bool:
    """¿La transición existe? Sin efectos: sirve para preguntar antes de actuar."""
    return hasta in TRANSICIONES[desde]


def transicionar(desde: Estado, hasta: Estado, motivo: Motivo | None = None) -> Estado:
    """Valida la transición y devuelve el estado nuevo.

    No toca la base: eso es del repositorio. Acá vive la regla, sola y testeable.

        >>> transicionar(Estado.BORRADOR, Estado.EN_ESPERA)
        <Estado.EN_ESPERA: 'EN_ESPERA'>
        >>> transicionar(Estado.EN_ESPERA, Estado.DESCARTADO, Motivo.VETADO)
        <Estado.DESCARTADO: 'DESCARTADO'>
    """
    if not puede(desde, hasta):
        raise TransicionInvalida(desde, hasta)

    if hasta is Estado.DESCARTADO and motivo is None:
        raise MotivoRequerido(f"descartar desde {desde} sin motivo")

    if hasta is not Estado.DESCARTADO and motivo is not None:
        raise TransicionInvalida(desde, hasta, f"'{motivo}' sólo aplica a DESCARTADO")

    return hasta


def tomar_para_enviar(desde: Estado) -> Estado:
    """**El único camino a `ENVIANDO`.**

    Está separado a propósito, aunque `transicionar` haría lo mismo: es la
    transición más peligrosa del sistema —a partir de acá el agente le escribe
    a una persona real— y queremos poder buscar en el repositorio quién la
    llama y encontrar una lista corta.

    Si alguna vez aparece un `transicionar(algo, Estado.ENVIANDO)` suelto por el
    código, es un hallazgo, no un atajo.
    """
    if desde is not Estado.EN_ESPERA:
        raise TransicionInvalida(
            desde,
            Estado.ENVIANDO,
            "sólo EN_ESPERA puede pasar a ENVIANDO, sin excepciones",
        )
    return transicionar(desde, Estado.ENVIANDO)


def es_terminal(estado: Estado) -> bool:
    """Un estado del que no se sale. `ENVIADO` y `DESCARTADO`."""
    return estado in TERMINALES
