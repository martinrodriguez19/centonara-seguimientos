"""Las etiquetas del nombre del contacto (D50): quién es el cliente, y si se le escribe.

Los vendedores empezaron a agendar a sus contactos con una palabra al final del
nombre: `Juan Pérez ARQ`, `Corralón Sur (DIST)`, `Mamá XX`. No está en todos
los contactos y no lo va a estar, así que la regla es la de siempre para los
que no la tienen, y algo mejor para los que sí.

Lo que decide este módulo es **si un nombre trae etiqueta y cuál**. Qué
significa cada una, si se contacta y cómo se le habla es del dueño y vive en
la configuración (`etiquetas_contacto`); acá sólo se lee.

Tres reglas, y las tres son para no equivocarse hacia el lado caro:

- **La última palabra**, y sólo ésa. Los vendedores la ponen al final.
- **En mayúsculas.** "Colo" es un apodo común: `Juan el Colo` no es un
  colocador, `Juan COLO` sí.
- **Con nombre delante.** Un contacto agendado todo en mayúsculas (`JUAN COLO`)
  es ambiguo, y un nombre que es sólo la etiqueta no es un nombre: en los dos
  casos, sin etiqueta. Ante la duda, el comportamiento de hoy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Lo que separa la etiqueta del nombre: espacio, guion, punto, barra, paréntesis
# o corchetes, en cualquier cantidad.
_SEPARADORES = re.compile(r"[\s\-\.\/\(\)\[\]_,]+")

# Cuando dos etiquetas van al final del nombre (`Tío Pedro COLO XX`), manda la
# que no contacta: es la que cuesta más equivocarse.
NO_CONTACTAR = "XX"


@dataclass(frozen=True)
class Etiqueta:
    etiqueta: str
    significado: str = ""
    contactar: bool = True
    enfoque: str = ""

    @property
    def no_contactar(self) -> bool:
        return not self.contactar

    def a_dict(self) -> dict[str, Any]:
        return {
            "etiqueta": self.etiqueta,
            "significado": self.significado,
            "contactar": self.contactar,
            "enfoque": self.enfoque,
        }


def conocidas(config: dict[str, Any]) -> dict[str, Etiqueta]:
    """Las etiquetas que el dueño definió, por palabra. Lo raro se ignora."""
    resultado: dict[str, Etiqueta] = {}
    for cruda in config.get("etiquetas_contacto") or []:
        if not isinstance(cruda, dict):
            continue
        palabra = str(cruda.get("etiqueta") or "").strip().upper()
        if not palabra.isalpha() or not palabra.isascii():
            continue
        resultado[palabra] = Etiqueta(
            etiqueta=palabra,
            significado=str(cruda.get("significado") or "").strip()[:80],
            contactar=bool(cruda.get("contactar", True)),
            enfoque=" ".join(str(cruda.get("enfoque") or "").split())[:300],
        )
    return resultado


def _palabras(nombre: str) -> list[str]:
    return [p for p in _SEPARADORES.split(nombre.strip()) if p]


def detectar(nombre: str, config: dict[str, Any]) -> Etiqueta | None:
    """La etiqueta de este nombre, o `None`. Nunca adivina."""
    tabla = conocidas(config)
    if not tabla:
        return None
    palabras = _palabras(nombre)
    if len(palabras) < 2:
        return None

    ultima = palabras[-1]
    if ultima not in tabla:
        return None

    resto = palabras[:-1]
    #  Si la anteúltima también es etiqueta, se saca del "nombre" y decide la
    #  que no contacta.
    candidatas = [ultima]
    if len(resto) >= 2 and resto[-1] in tabla:
        candidatas.append(resto[-1])
        resto = resto[:-1]

    #  Sin una minúscula en el nombre no se sabe si "COLO" es etiqueta o apodo.
    if not any(c.islower() for c in "".join(resto)):
        return None

    for palabra in candidatas:
        if palabra == NO_CONTACTAR or tabla[palabra].no_contactar:
            return tabla[palabra]
    return tabla[candidatas[0]]


def nombre_sin_etiqueta(nombre: str, config: dict[str, Any]) -> str:
    """El nombre como se saluda: `Juan Pérez ARQ` → `Juan Pérez`. Sin etiqueta, igual."""
    if detectar(nombre, config) is None:
        return nombre.strip()
    tabla = conocidas(config)
    palabras = _palabras(nombre)
    while len(palabras) > 1 and palabras[-1] in tabla:
        palabras.pop()
    return " ".join(palabras)


def para_el_payload(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Las etiquetas como viajan al pase único, en el orden en que el dueño las escribió."""
    return [e.a_dict() for e in conocidas(config).values()]
