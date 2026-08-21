"""Los ocho guardrails: lo que impide que salga un mensaje que no debía salir.

Son ocho, no veinte. Cada uno cubre un modo de falla que cuesta caro; el resto
se agrega el día que aparezca el caso, no antes.

**Viven acá, en Python, con tests.** Nunca en un prompt: un prompt se puede
reinterpretar, un `if` con un test que lo cubre no. Si alguna vez parece más
fácil pedírselo al modelo, la respuesta es no (regla R3).

Cuatro de los ocho también se verifican en el agente, y no porque el agente
desconfíe del backend: **porque un job puede quedar encolado y ejecutarse
minutos después**, y en el medio el tope, la pausa o la lista de destinos
pueden haber cambiado. Esa segunda verificación es contra el paso del tiempo.

Cobertura exigida de este archivo: 100%.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.core import configuracion, mensajes, vendedores
from app.logging import obtener_logger

log = obtener_logger(__name__)


class Guardrail(StrEnum):
    """Los ocho. El valor es lo que se guarda y lo que ve el panel."""

    IDENTIDAD = "G1_IDENTIDAD"
    """El header del chat abierto no es el contacto esperado. **Sólo en el agente.**"""

    DESTINO = "G2_DESTINO_NO_PERMITIDO"
    TEXTO = "G3_TEXTO_INVALIDO"
    TOPE = "G4_TOPE"
    DUPLICADO = "G5_DUPLICADO"
    VENTANA = "G6_FUERA_DE_VENTANA"
    PAUSA = "G7_PAUSA"

    CAMPO_NO_VACIO = "G8_CAMPO_NO_VACIO"
    """Había texto escrito en el chat. **Sólo en el agente.**"""


@dataclass(frozen=True)
class Violacion:
    guardrail: Guardrail
    detalle: str

    def __str__(self) -> str:
        return f"{self.guardrail}: {self.detalle}"


class GuardrailViolado(Exception):
    """Un mensaje intentó salir y no debía.

    Lleva el guardrail que lo frenó para poder contarlos: "cuántos frenó el tope
    diario" y "cuántos frenó el anti-duplicado" son preguntas distintas, y la
    respuesta decide qué aflojar.
    """

    def __init__(self, violacion: Violacion) -> None:
        self.violacion = violacion
        self.codigo = violacion.guardrail
        super().__init__(str(violacion))


# ---------------------------------------------------------------------------
# G3 — Texto válido
# ---------------------------------------------------------------------------

# Lo que delata un texto a medio armar. Cinco formas de lo mismo: alguien —el
# modelo o una persona— dejó un hueco que iba a completar después.
#
# `\{[^}]*\}` cubre `{nombre}` y también `{{nombre}}`, porque el segundo
# contiene al primero.
PLACEHOLDERS = re.compile(
    r"\{[^}]*\}"  # {nombre}, {{nombre}}
    r"|\[[^\]]*\]"  # [producto]
    r"|\bXXX+\b"  # XXX
    r"|\bTODO\b"  # TODO
    r"|\bTBD\b",
    re.IGNORECASE,
)


def revisar_texto(texto: str, *, largo_maximo: int) -> Violacion | None:
    """G3. Vacío, con placeholders, o demasiado largo.

    El de los placeholders es el que más importa y el menos obvio: el texto se
    envía **exactamente como está**, sin que nadie lo complete después. Un
    `Hola {nombre}` que sale es peor que uno que no sale.
    """
    if not texto or not texto.strip():
        return Violacion(Guardrail.TEXTO, "el texto está vacío")

    encontrado = PLACEHOLDERS.search(texto)
    if encontrado:
        return Violacion(
            Guardrail.TEXTO, f"quedó un placeholder sin resolver: {encontrado.group(0)!r}"
        )

    if len(texto) > largo_maximo:
        return Violacion(Guardrail.TEXTO, f"{len(texto)} caracteres, el máximo es {largo_maximo}")

    return None


# ---------------------------------------------------------------------------
# G6 — Ventana horaria
# ---------------------------------------------------------------------------


def _minutos(hhmm: str) -> int:
    horas, _, minutos = hhmm.partition(":")
    return int(horas) * 60 + int(minutos)


def revisar_ventana(ventana: dict[str, Any], *, ahora: datetime) -> Violacion | None:
    """G6. Fuera del horario hábil no sale nada.

    No es cortesía: es comportamiento plausible. Mensajes comerciales a las tres
    de la mañana son de las cosas que hacen que a alguien lo reporten, y lo que
    dispara bloqueos no es el volumen sino los patrones que no parecen humanos.

    `isoweekday()`: lunes es 1, domingo es 7. Igual que la lista de la
    configuración.
    """
    if ahora.isoweekday() not in ventana.get("dias", [1, 2, 3, 4, 5]):
        return Violacion(Guardrail.VENTANA, f"hoy no es día hábil ({ahora:%A})")

    minuto = ahora.hour * 60 + ahora.minute
    inicio = _minutos(ventana.get("inicio", "09:00"))
    fin = _minutos(ventana.get("fin", "19:00"))

    if not (inicio <= minuto < fin):
        return Violacion(
            Guardrail.VENTANA,
            f"son las {ahora:%H:%M} y la ventana es {ventana.get('inicio')} a {ventana.get('fin')}",
        )
    return None


# ---------------------------------------------------------------------------
# La revisión completa
# ---------------------------------------------------------------------------


async def revisar(
    base,
    *,
    contacto_id: str,
    texto: str,
    maquina: str,
    config: dict[str, Any] | None = None,
    vendedor: dict[str, Any] | None = None,
    verificar_ventana: bool = True,
    ahora: datetime | None = None,
) -> list[Violacion]:
    """Corre los seis guardrails del backend y devuelve **todas** las violaciones.

    Devuelve la lista completa en vez de cortar en la primera: si un mensaje
    tiene el texto vacío *y* está fuera de la ventana, quien lo mira quiere
    saber las dos cosas. Cortar en la primera obliga a arreglar, reintentar,
    descubrir la segunda, y así.

    G1 y G8 no están acá: sólo se pueden verificar mirando la pantalla real, y
    eso lo hace el agente.
    """
    momento = ahora or datetime.now(UTC)
    config = config if config is not None else await configuracion.obtener(base)
    violaciones: list[Violacion] = []

    # G7 — Pausa. Va primero porque si el sistema está frenado, lo demás no
    # importa: es la respuesta más corta que se le puede dar a quien pregunta.
    if config.get("pausa_global"):
        violaciones.append(Violacion(Guardrail.PAUSA, "el sistema está frenado"))

    if vendedor is None:
        vendedor = await base["vendedores"].find_one({"maquina": maquina})

    if vendedor is None:
        violaciones.append(Violacion(Guardrail.PAUSA, f"no existe la máquina '{maquina}'"))
        return violaciones

    if vendedores.esta_pausada(vendedor, ahora=momento):
        violaciones.append(Violacion(Guardrail.PAUSA, f"la máquina '{maquina}' está pausada"))

    # Sin consentimiento no se le encolan envíos (R6). Se cuenta como pausa
    # porque para el sistema es lo mismo —esa máquina no manda— y para la
    # persona que mira el panel es una sola frase.
    if not vendedores.puede_enviar(vendedor):
        violaciones.append(
            Violacion(Guardrail.PAUSA, f"'{maquina}' no tiene el consentimiento registrado")
        )

    # G2 — Destino permitido. **El que hace que todo lo demás sea seguro de
    # construir**: mientras la lista no esté abierta, ninguna corrida puede
    # alcanzar a un cliente real, corra donde corra el sistema.
    if not configuracion.destino_permitido(config, contacto_id):
        violaciones.append(
            Violacion(Guardrail.DESTINO, f"{contacto_id} no está en los destinos permitidos")
        )

    # G3 — Texto.
    problema = revisar_texto(texto, largo_maximo=config.get("largo_maximo", 600))
    if problema:
        violaciones.append(problema)

    # G6 — Ventana horaria.
    if verificar_ventana:
        fuera = revisar_ventana(config.get("ventana", {}), ahora=momento)
        if fuera:
            violaciones.append(fuera)

    # G4 — Tope diario de esta máquina.
    tope = vendedor.get("tope_diario", config.get("tope_diario_maquina", 20))
    ya = await mensajes.enviados_hoy(base, maquina, ahora=momento)
    if ya >= tope:
        violaciones.append(
            Violacion(Guardrail.TOPE, f"'{maquina}' ya tiene {ya} hoy, el tope es {tope}")
        )

    # G5 — Anti-duplicado.
    dias = config.get("dias_anti_duplicado", 7)
    if await mensajes.le_escribimos_hace_poco(base, contacto_id, dias=dias, ahora=momento):
        violaciones.append(
            Violacion(
                Guardrail.DUPLICADO, f"a {contacto_id} ya le escribimos en los últimos {dias} días"
            )
        )

    return violaciones


async def exigir(base, **kwargs) -> None:
    """Como `revisar`, pero lanza con la primera violación.

    Para los caminos donde no hay nada que mostrar y sólo hay que frenar.
    """
    violaciones = await revisar(base, **kwargs)
    if violaciones:
        log.warning(
            "guardrail_violado",
            cantidad=len(violaciones),
            codigos=[str(v.guardrail) for v in violaciones],
        )
        raise GuardrailViolado(violaciones[0])


def cabe_en_la_corrida(ya_encolados: int, config: dict[str, Any]) -> Violacion | None:
    """G4, la otra mitad: el tope por corrida.

    Separado del tope diario porque protege de otra cosa. El diario protege la
    línea del vendedor; éste protege de un bug que encole de más — un
    `LISTAR` que devuelve mil chats en vez de veinte.
    """
    tope = config.get("tope_por_corrida", 25)
    if ya_encolados >= tope:
        return Violacion(Guardrail.TOPE, f"la corrida ya tiene {ya_encolados}, el tope es {tope}")
    return None
