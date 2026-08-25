"""`LISTAR`: leer los chats recientes de WhatsApp Web. **Sólo lectura.**

Es el único job que abre el navegador con un modelo del otro lado. Lo que se le
pide es acotado a propósito —leer y anotar— y el `CLAUDE.md` de la máquina lo
dice también, desde afuera del pedido: escribir en el campo de texto y apretar
enviar los hace código con selectores explícitos, no un modelo.

Lo que este módulo agrega sobre la invocación cruda es **desconfiar de la
respuesta**. El modelo puede devolver un chat sin nombre, una antigüedad
negativa o un teléfono que se inventó. Nada de eso puede llegar al backend como
si fuera un dato bueno:

- Un chat mal formado **se descarta y se cuenta**, nunca se descarta en silencio.
- `contacto_telefono` puede venir en `null`, y eso es una respuesta correcta: el
  prompt pide explícitamente no deducirlo. Un número inventado acá termina en un
  mensaje comercial a otra persona.
- Si el `run_id` que vuelve no es el que se mandó, la respuesta no es de esta
  corrida y no se usa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agente.jobs.claude_code import Invocacion, invocar, rellenar
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# La misma cota que el backend (`app/modelos/jobs.py`). Está repetida a
# propósito: es la última barrera antes de pedirle a un modelo que lea chats, y
# no depende de que el backend la haya respetado.
MAX_CHATS = 50

# Qué significa cada motivo que el prompt puede devolver, en códigos de la cola.
MOTIVOS = {
    "sesion_no_iniciada": "SESION_CAIDA",
    "browser_no_disponible": "ERROR_INESPERADO",
}

QUIEN_HABLO = {"contacto": "contacto", "yo": "vendedor", "vendedor": "vendedor"}


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


async def listar(
    *,
    n_chats: int,
    run_id: str,
    device_id: str,
    claude_bin: str,
    carpeta: Path,
    antiguedad_min_dias: int = 0,
    antiguedad_max_dias: int = 3650,
    invocador=invocar,
) -> Resultado:
    """Lee chats dentro de la ventana de antigüedad y devuelve lo certero.

    La ventana existe porque el caso de uso son los clientes fríos: el chat de
    hoy no necesita seguimiento, el de hace un mes sí. El modelo recorre la
    lista hacia atrás hasta cubrirla, con `n_chats` de tope.
    """
    if not device_id:
        # Problema #5 del MVP. Sin esto, con más de un Chrome conectado a la
        # cuenta, headless elige cualquiera — y "cualquiera" puede ser el Chrome
        # de otra máquina, con el WhatsApp de otra persona.
        return Resultado(
            False, "ERROR_INESPERADO", {"motivo": "sin deviceId: no se sabe a qué Chrome ir"}
        )

    minimo = max(0, int(antiguedad_min_dias))
    maximo = max(minimo, int(antiguedad_max_dias))
    prompt = rellenar(
        carpeta / "prompts" / "prompt-listar.txt",
        {
            "N_CHATS": str(max(1, min(int(n_chats), MAX_CHATS))),
            "RUN_ID": run_id[:64],
            "DEVICE_ID": device_id,
            "ANTIGUEDAD_MIN": str(minimo),
            "ANTIGUEDAD_MAX": str(maximo),
        },
    )

    invocacion = await invocador(prompt, claude_bin=claude_bin, carpeta=carpeta, con_navegador=True)
    if not invocacion.ok:
        return _desde_invocacion(invocacion)

    return _interpretar(invocacion, run_id=run_id)


def _desde_invocacion(invocacion: Invocacion) -> Resultado:
    return Resultado(
        False,
        invocacion.codigo or "ERROR_INESPERADO",
        invocacion.detalle,
        raw=invocacion.raw,
        stderr=invocacion.stderr,
        costo_usd=invocacion.costo_usd,
    )


def _interpretar(invocacion: Invocacion, *, run_id: str) -> Resultado:
    datos = invocacion.datos or {}
    comunes = {
        "raw": invocacion.raw,
        "stderr": invocacion.stderr,
        "costo_usd": invocacion.costo_usd,
    }

    devuelto = datos.get("run_id")
    if devuelto is not None and str(devuelto) != run_id:
        log.error("listar_run_id_ajeno", esperado=run_id, recibido=str(devuelto)[:64])
        return Resultado(
            False,
            "ERROR_INESPERADO",
            {
                "motivo": "la respuesta no es de esta corrida",
                "esperado": run_id,
                "recibido": str(devuelto)[:64],
            },
            **comunes,
        )

    estado = datos.get("status")
    if estado == "error":
        motivo = str(datos.get("motivo", "otro"))
        codigo = MOTIVOS.get(motivo, "ERROR_INESPERADO")
        log.warning("listar_reporto_error", motivo=motivo, codigo=codigo)
        return Resultado(
            False,
            codigo,
            {"motivo": motivo, "detalle": str(datos.get("detalle", ""))[:500]},
            **comunes,
        )

    if estado != "ok":
        return Resultado(
            False, "ERROR_INESPERADO", {"motivo": f"status inesperado: {estado!r}"}, **comunes
        )

    crudos = datos.get("chats")
    if not isinstance(crudos, list):
        return Resultado(
            False,
            "ERROR_INESPERADO",
            {"motivo": "la respuesta no trae una lista de chats"},
            **comunes,
        )

    buenos: list[dict[str, Any]] = []
    descartados: list[str] = []
    for i, crudo in enumerate(crudos[:MAX_CHATS]):
        limpio, problema = _revisar_chat(crudo)
        if limpio is None:
            descartados.append(f"#{i}: {problema}")
            continue
        buenos.append(limpio)

    if descartados:
        # Contados y nombrados. Un chat que se cae sin que nadie se entere es un
        # cliente al que no se le escribe y nadie sabe por qué.
        log.warning("listar_chats_descartados", cuantos=len(descartados), motivos=descartados[:5])

    log.info("listar_ok", leidos=len(buenos), descartados=len(descartados))
    return Resultado(
        True,
        detalle={
            "chats": buenos,
            "leidos": len(buenos),
            "descartados": descartados,
            "sin_telefono": sum(1 for c in buenos if c["contacto_telefono"] is None),
        },
        **comunes,
    )


def _revisar_chat(crudo: Any) -> tuple[dict[str, Any] | None, str]:
    """Un chat, o el motivo por el que no se puede usar."""
    if not isinstance(crudo, dict):
        return None, f"se esperaba un objeto y vino {type(crudo).__name__}"

    nombre = str(crudo.get("contacto_nombre") or "").strip()
    if not nombre:
        return None, "sin contacto_nombre"

    resumen = str(crudo.get("ultimo_mensaje_resumen") or "").strip()
    if not resumen:
        return None, f"{nombre!r}: sin resumen"

    quien = QUIEN_HABLO.get(str(crudo.get("ultimo_lo_mando") or "").strip().lower())
    if quien is None:
        return None, f"{nombre!r}: ultimo_lo_mando no es 'contacto' ni 'yo'"

    try:
        dias = int(crudo.get("antiguedad_dias"))
    except (TypeError, ValueError):
        return None, f"{nombre!r}: antiguedad_dias no es un entero"
    if dias < 0:
        return None, f"{nombre!r}: antiguedad_dias negativa"

    # `null` es una respuesta válida y esperada: el prompt pide no deducirlo.
    # Quien decide qué hacer con un chat sin teléfono es el backend, en el
    # triage, no este módulo.
    telefono = crudo.get("contacto_telefono")
    telefono = str(telefono).strip() if telefono else None

    return {
        "contacto_nombre": nombre[:120],
        "contacto_telefono": telefono,
        "ultimo_mensaje_resumen": resumen[:400],
        "quien_hablo_ultimo": quien,
        "antiguedad_dias": min(dias, 3650),
    }, ""
