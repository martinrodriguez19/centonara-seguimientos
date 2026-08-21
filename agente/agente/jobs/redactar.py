"""`REDACTAR`: escribir un seguimiento. **Sin navegador.**

Que no abra el navegador no es una optimización menor: es donde está el ahorro
del proyecto. `REDACTAR` es el job más frecuente —uno por chat, mientras que
`LISTAR` es uno por máquina— y sacarlo del circuito del navegador es lo que
decide el costo por mensaje. El criterio verificable de `docs/04-AGENTE.md` §6
es literal: redactar veinte borradores no abre ninguna pestaña. El test de este
módulo lo comprueba mirando que no aparezca `--chrome` en el comando.

Todo el contexto viaja en el payload, que el backend ya validó contra un
esquema. Acá no se busca nada ni se completa nada.

**Este módulo no decide si el texto sirve.** Los placeholders sin resolver, el
largo y el texto vacío los revisa el guardrail G3 en el backend, que es donde
vive la política. Es la regla R3: el modelo redacta, el código decide. Repetir
la validación acá crearía dos lugares donde puede aflojarse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agente.jobs.claude_code import Invocacion, invocar, rellenar
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# El payload habla en términos del sistema (`vendedor`); el prompt, en primera
# persona (`yo`), porque se lo lee un modelo que está mirando ese chat.
COMO_LO_DICE_EL_PROMPT = {"contacto": "contacto", "vendedor": "yo"}


@dataclass(frozen=True)
class Resultado:
    ok: bool
    codigo: str | None = None
    detalle: dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    stderr: str = ""
    costo_usd: float = 0.0

    def a_reporte(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "codigo": self.codigo,
            "detalle": self.detalle,
            "raw": self.raw,
            "stderr": self.stderr,
            "costo_usd": self.costo_usd,
        }


async def redactar(
    *,
    contacto_nombre: str,
    resumen: str,
    quien_hablo_ultimo: str,
    antiguedad_dias: int,
    largo_maximo: int,
    claude_bin: str,
    carpeta: Path,
    invocador=invocar,
) -> Resultado:
    """Redacta un borrador para un chat, o explica por qué no hay contexto."""
    prompt = rellenar(
        carpeta / "prompts" / "prompt-redactar.txt",
        {
            "CONTACTO_NOMBRE": contacto_nombre[:120],
            "ULTIMO_MENSAJE_RESUMEN": resumen[:400],
            "ULTIMO_LO_MANDO": COMO_LO_DICE_EL_PROMPT.get(quien_hablo_ultimo, "contacto"),
            "ANTIGUEDAD_DIAS": str(max(0, int(antiguedad_dias))),
            "LARGO_MAXIMO": str(largo_maximo),
        },
    )

    invocacion = await invocador(
        prompt, claude_bin=claude_bin, carpeta=carpeta, con_navegador=False
    )
    if not invocacion.ok:
        return _desde_invocacion(invocacion)

    return _interpretar(invocacion, contacto_nombre=contacto_nombre)


def _desde_invocacion(invocacion: Invocacion) -> Resultado:
    return Resultado(
        False,
        invocacion.codigo or "ERROR_INESPERADO",
        invocacion.detalle,
        raw=invocacion.raw,
        stderr=invocacion.stderr,
        costo_usd=invocacion.costo_usd,
    )


def _interpretar(invocacion: Invocacion, *, contacto_nombre: str) -> Resultado:
    datos = invocacion.datos or {}
    comunes = {
        "raw": invocacion.raw,
        "stderr": invocacion.stderr,
        "costo_usd": invocacion.costo_usd,
    }
    estado = datos.get("status")

    if estado == "sin_contexto":
        # ⚠️ Esto NO es un fallo del job: el job hizo su trabajo y la conclusión
        # fue que no hay con qué escribir. El prompt lo pide explícitamente como
        # alternativa a inventar un seguimiento genérico.
        #
        # Se reporta `ok=True` porque un `ok=False` haría que la cola lo
        # reintente, y el reintento daría exactamente lo mismo. Qué se hace con
        # un chat sin contexto —apartarlo para que lo mire una persona— lo
        # decide el backend.
        motivo = str(datos.get("motivo", ""))[:300]
        log.info("redactar_sin_contexto", contacto=contacto_nombre, motivo=motivo)
        return Resultado(True, detalle={"status": "sin_contexto", "motivo": motivo}, **comunes)

    if estado != "ok":
        return Resultado(
            False, "ERROR_INESPERADO", {"motivo": f"status inesperado: {estado!r}"}, **comunes
        )

    texto = datos.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        # El modelo dijo "ok" y no mandó texto. Contradice su propia respuesta,
        # así que no se toma por buena.
        return Resultado(
            False, "ERROR_INESPERADO", {"motivo": "status ok pero sin texto"}, **comunes
        )

    limpio = texto.strip()
    log.info("redactar_ok", contacto=contacto_nombre, largo=len(limpio))
    return Resultado(
        True, detalle={"status": "ok", "texto": limpio, "largo": len(limpio)}, **comunes
    )
