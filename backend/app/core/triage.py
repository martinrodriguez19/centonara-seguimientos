"""El triage: qué borradores se apartan para que alguien los mire.

**No bloquea, aparta.** Un guardrail dice "esto no sale nunca"; el triage dice
"esto lo mira una persona antes". La mayoría de los mensajes pasa sin tocar
nada.

Por qué existe, si ya hay guardrails: los guardrails atrapan lo que se puede
verificar —un placeholder, un tope, un horario—. El triage atrapa lo que no se
puede verificar pero se puede *sospechar*: un seguimiento comercial sobre un
reclamo abierto es un mensaje perfectamente bien formado que no debería salir.

**Los errores no se distribuyen al azar.** El prompt funciona bien en el chat
típico precisamente porque es típico. El error cae en el caso raro —el reclamo,
el chat que mezcla lo personal con lo laboral, el que quedó a medias— y ese
suele ser también el más caro. Por eso el triage no es redundante con "revisar
unos cuantos al azar".

**Calibración: tiene que retener entre el 10% y el 20%.** Si retiene el 40%,
molesta, y un triage que molesta se termina apagando — y un triage apagado es
peor que no tenerlo, porque el equipo cree que está protegido.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core.contactos import NumeroInvalido, normalizar
from app.logging import obtener_logger

log = obtener_logger(__name__)


class Senal(StrEnum):
    """Por qué se apartó un mensaje. El panel las muestra en palabras humanas."""

    PALABRA_CONFLICTO = "PALABRA_CONFLICTO"
    """El chat tiene un reclamo abierto. El peor error posible del sistema."""

    SIN_RESPUESTA_PREVIA = "SIN_RESPUESTA_PREVIA"
    """Ya le escribimos y no contestó. Insistir sobre silencio es lo que dispara
    que a uno lo reporten — y lo reportado es lo que bloquea líneas."""

    IDENTIDAD_AMBIGUA = "IDENTIDAD_AMBIGUA"
    """No sabemos con certeza a quién le estaríamos escribiendo."""

    COMPROMISO_CONCRETO = "COMPROMISO_CONCRETO"
    """El borrador menciona un precio, una fecha o una cantidad. Un dato
    inventado por el modelo se convierte en una promesa comercial."""

    CHAT_NO_COMERCIAL = "CHAT_NO_COMERCIAL"
    """No parece una conversación de trabajo. Las líneas mezclan lo personal."""


def _sin_acentos(texto: str) -> str:
    """Para comparar palabras sin que un acento las haga distintas.

    El cliente va a cargar "devolución" desde el panel y el resumen puede decir
    "devolucion". Que una tilde decida si un reclamo se aparta o no sería un
    resultado absurdo.
    """
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def contiene_alguna(texto: str, palabras: list[str]) -> str | None:
    """La primera palabra de la lista que aparece en el texto, o `None`.

    Compara sin acentos y por subcadena. Por subcadena a propósito: "reclamo"
    tiene que encontrar "reclamos" y "reclamó", y una lista que el cliente
    edita a mano no va a tener todas las conjugaciones.
    """
    plano = _sin_acentos(texto)
    for palabra in palabras:
        if palabra and _sin_acentos(palabra) in plano:
            return palabra
    return None


# Lo que convierte un borrador en una promesa. Cuatro formas de comprometerse a
# algo concreto que el modelo pudo haber inventado.
COMPROMISOS = (
    # Plata. Dos cosas que la primera versión hacía mal:
    #
    #   - la moneda puede ir ANTES o DESPUÉS del número. "$1.500" y "1500 pesos"
    #     comprometen lo mismo, y "USD 200" no matcheaba con el patrón viejo.
    #   - captura el importe COMPLETO. El detalle que ve quien revisa tiene que
    #     decir "$1.500"; con `\$\s?\d` decía "$1", que es peor que no decir nada.
    re.compile(
        r"(?:\$|u\$s|usd)\s?\d[\d.,]*"  # $1.500, USD 200, u$s 50
        r"|\d[\d.,]*\s*(?:pesos|d[oó]lares|usd|u\$s)"  # 1500 pesos, 200 dólares
        r"|\d+\s?%",  # 15%
        re.I,
    ),
    # Fechas: 15/8, el lunes, mañana, la semana que viene
    re.compile(
        r"\b\d{1,2}/\d{1,2}\b"
        r"|\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b"
        r"|\b(hoy|ma[ñn]ana|pasado ma[ñn]ana)\b"
        r"|\bla semana que viene\b|\bel mes que viene\b",
        re.I,
    ),
    # Plazos: en 3 días, dentro de 2 semanas, a 30 días
    re.compile(r"\b(en|dentro de|a)\s+\d+\s*(d[ií]as?|semanas?|meses?|horas?)\b", re.I),
    # Cantidades con unidad: 200 metros, 5 chapas, 3 bolsas
    re.compile(r"\b\d+\s*(m2|m²|metros?|kg|kilos?|toneladas?|unidades?|bolsas?|chapas?)\b", re.I),
)


def busca_compromiso(texto: str) -> str | None:
    """Lo que el borrador promete, si promete algo."""
    for patron in COMPROMISOS:
        encontrado = patron.search(texto)
        if encontrado:
            return encontrado.group(0).strip()
    return None


@dataclass(frozen=True)
class Hallazgo:
    senal: Senal
    detalle: str

    def __str__(self) -> str:
        return f"{self.senal}: {self.detalle}"


def evaluar(
    *,
    texto: str,
    resumen: str,
    contacto_id: str,
    contacto_nombre: str,
    quien_hablo_ultimo: str,
    config: dict[str, Any],
    ya_le_escribimos: bool = False,
    nombre_repetido: bool = False,
) -> list[Hallazgo]:
    """Las señales que enciende este borrador. Vacío = sale sin que nadie lo mire.

    Función pura: recibe todo lo que necesita y no toca la base. Lo que sí
    necesita consultar —si ya le escribimos, si el nombre se repite— se lo pasa
    quien la llama, que ya tiene esos datos a mano de la validación.
    """
    hallazgos: list[Hallazgo] = []

    # 1. Palabra de conflicto. La más importante: un seguimiento comercial sobre
    #    un reclamo abierto es el peor error posible del sistema.
    palabra = contiene_alguna(resumen, config.get("palabras_conflicto", []))
    if palabra:
        hallazgos.append(Hallazgo(Senal.PALABRA_CONFLICTO, f"el chat menciona {palabra!r}"))

    # 2. Le escribimos y no contestó. Se sabe mirando quién habló último: si
    #    fuimos nosotros, el contacto no respondió el seguimiento anterior.
    if ya_le_escribimos and quien_hablo_ultimo == "vendedor":
        hallazgos.append(
            Hallazgo(
                Senal.SIN_RESPUESTA_PREVIA,
                "ya le escribimos antes y todavía no contestó",
            )
        )

    # 3. Identidad ambigua. Duda sobre a quién le estaríamos escribiendo.
    ambigua = _revisar_identidad(contacto_id, contacto_nombre, nombre_repetido)
    if ambigua:
        hallazgos.append(ambigua)

    # 4. Compromiso concreto. El modelo puede haber inventado el número.
    compromiso = busca_compromiso(texto)
    if compromiso:
        hallazgos.append(Hallazgo(Senal.COMPROMISO_CONCRETO, f"el borrador dice {compromiso!r}"))

    # 5. No parece una conversación de trabajo.
    comerciales = config.get("palabras_comerciales", [])
    if comerciales and not contiene_alguna(resumen, comerciales):
        hallazgos.append(
            Hallazgo(Senal.CHAT_NO_COMERCIAL, "el chat no tiene señales de intención comercial")
        )

    return hallazgos


def _revisar_identidad(
    contacto_id: str, contacto_nombre: str, nombre_repetido: bool
) -> Hallazgo | None:
    if not contacto_id:
        return Hallazgo(Senal.IDENTIDAD_AMBIGUA, "no se pudo leer el número del chat")

    try:
        normalizar(contacto_id)
    except NumeroInvalido as error:
        return Hallazgo(Senal.IDENTIDAD_AMBIGUA, f"el número no se pudo resolver ({error.motivo})")

    if nombre_repetido:
        return Hallazgo(
            Senal.IDENTIDAD_AMBIGUA,
            f"hay más de un contacto llamado {contacto_nombre!r} en esta corrida",
        )
    return None


def nombres_repetidos(chats: list[dict[str, Any]]) -> set[str]:
    """Los nombres que aparecen con más de un número en la misma corrida.

    Es la parte de la ambigüedad que sólo se ve mirando la tanda entera: dos
    "Ferretería Sur" con teléfonos distintos son dos negocios, y el borrador de
    uno puede no tener nada que ver con el otro.

    Compara sin acentos, por el mismo motivo que las palabras: "Ferretería Sur"
    y "Ferreteria Sur" son el mismo negocio anotado de dos formas, y que una
    tilde decida si se detecta el duplicado sería absurdo.
    """
    por_nombre: dict[str, set[str]] = {}
    for chat in chats:
        nombre = _sin_acentos((chat.get("contacto_nombre") or "").strip())
        if nombre:
            por_nombre.setdefault(nombre, set()).add(chat.get("contacto_id") or "")
    return {nombre for nombre, numeros in por_nombre.items() if len(numeros) > 1}


def proporcion_retenida(evaluaciones: list[list[Hallazgo]]) -> float:
    """Qué proporción de una tanda se apartó.

    Existe para poder calibrar con datos y no de memoria: el objetivo es 10 a 20%,
    y la única forma de saber si se cumple es medirlo sobre borradores reales.
    """
    if not evaluaciones:
        return 0.0
    return sum(1 for hallazgos in evaluaciones if hallazgos) / len(evaluaciones)
