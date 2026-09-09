"""Señales sobre lo que el pase único escribió (D40). Informativas, nunca bloqueantes.

Cuando el reporte de una tanda llega, los borradores **ya están escritos** en
los chats del vendedor. Nada de lo que se calcule acá puede des-escribir uno:
lo que hace es marcar la fila del panel para que una persona decida si lo borra
a mano. Por eso este módulo no vive en `guardrails.py` —ahí las señales tienen
semántica de bloqueo en el circuito viejo y el CI exige cobertura total— y por
eso devuelve una lista y no levanta nada.

Funciones puras: reciben texto y configuración, no tocan la base. Lo que dicen
es, en orden de importancia:

- `CHAT_DISCONFORME` — se dejó borrador en un chat que las palabras del dueño
  marcaban como conflicto. El modelo no lo detectó; alguien tiene que mirar.
- `SIN_ANCLAJE` — el borrador afirma un tema concreto pero no trae la cita
  literal del chat en la que se apoya. Es la forma barata de dudar de que leyó.
- `TONO_FORMAL` y `EXCESO_DE_SIGNOS` — las reglas contables del prompt, medidas.
  No molestan a nadie: dicen si el prompt está funcionando.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core.triage import contiene_alguna


class Senal(StrEnum):
    EXCESO_DE_SIGNOS = "EXCESO_DE_SIGNOS"
    TONO_FORMAL = "TONO_FORMAL"
    SIN_ANCLAJE = "SIN_ANCLAJE"
    CHAT_DISCONFORME = "CHAT_DISCONFORME"
    #  La enciende `pase_unico`, no `revisar`: necesita la base. Un segundo
    #  borrador a la misma persona en la misma corrida, con otro nombre de chat.
    NUMERO_REPETIDO = "NUMERO_REPETIDO"


@dataclass(frozen=True)
class Hallazgo:
    senal: Senal
    detalle: str

    def __str__(self) -> str:
        return f"{self.senal}: {self.detalle}"


# Cuántos signos de pregunta admite un borrador. "¿...?" cuenta como uno: se
# mira sólo el de cierre.
MAX_PREGUNTAS = 1

_EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿]")
_PUNTOS_SUSPENSIVOS = re.compile(r"\.{3}|…")
# Cuatro mayúsculas seguidas o más. Tres deja pasar las siglas normales del
# rubro (PVC, USD, IVA); "HOLA" o "URGENTE" no son siglas.
_MAYUSCULA_SOSTENIDA = re.compile(r"\b[A-ZÁÉÍÓÚÑ]{4,}\b")


def exceso_de_signos(texto: str) -> str | None:
    """Lo primero que rompe la regla contable del prompt, o `None`."""
    if "!" in texto or "¡" in texto:
        return "signos de exclamación"
    if texto.count("?") > MAX_PREGUNTAS:
        return "más de una pregunta"
    if _PUNTOS_SUSPENSIVOS.search(texto):
        return "puntos suspensivos"
    if _EMOJI.search(texto):
        return "emojis"
    sostenida = _MAYUSCULA_SOSTENIDA.search(texto)
    if sostenida:
        return f"mayúscula sostenida ({sostenida.group(0)})"
    return None


def revisar(
    *,
    texto: str,
    resumen: str,
    tema: str | None,
    cita: str | None,
    motivo: str | None,
    config: dict[str, Any],
) -> list[Hallazgo]:
    """Las señales que enciende este borrador ya escrito. Vacío = nada que mirar."""
    hallazgos: list[Hallazgo] = []

    # 1. Conflicto que el modelo no vio. Un post-venta (`ya_compro`) no cuenta:
    #    ahí el chat habla de una compra hecha, no de un reclamo.
    if motivo != "ya_compro":
        palabra = contiene_alguna(resumen, config.get("palabras_conflicto") or [])
        if palabra:
            hallazgos.append(
                Hallazgo(Senal.CHAT_DISCONFORME, f"el chat menciona {palabra!r} y se le escribió")
            )

    # 2. Afirma tema y no lo respalda con una cita: no se puede saber si leyó.
    if (tema or "").strip() and not (cita or "").strip():
        hallazgos.append(Hallazgo(Senal.SIN_ANCLAJE, f"dice {tema!r} sin citar el chat"))

    # 3. Las frases de oficina que el dueño prohibió.
    frase = contiene_alguna(texto, config.get("frases_prohibidas") or [])
    if frase:
        hallazgos.append(Hallazgo(Senal.TONO_FORMAL, f"usa {frase!r}"))

    # 4. Los signos, contados.
    exceso = exceso_de_signos(texto)
    if exceso:
        hallazgos.append(Hallazgo(Senal.EXCESO_DE_SIGNOS, exceso))

    return hallazgos
