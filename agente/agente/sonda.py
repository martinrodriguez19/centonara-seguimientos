"""La sonda: lo que el diagnóstico no puede contestar sin abrir el navegador.

Dos de los nueve chequeos salen siempre en `n/a`, y no por pereza:

- `permiso_sitio` — la extensión tiene que tener habilitado `web.whatsapp.com`
  en **su propia** lista de sitios, que es una capa distinta del permiso de host
  de Chrome y de `mcp__claude-in-chrome` en `settings.json`. No queda registrada
  en ningún archivo que se pueda leer: probamos buscarla en el almacenamiento de
  la extensión y no está ahí. La única forma de saber si está es usarla.
- `whatsapp_sesion` — que la página no pida un QR sólo se ve abriéndola.

Esto los contesta, con el **mismo camino que va a usar `LISTAR`**: headless,
`--chrome`, el `deviceId` de esta máquina. Si la sonda pasa, `LISTAR` va a poder
llegar a la página; si falla, dice cuál de los dos es.

**Por qué no está adentro de `--diagnostico`:** cuesta plata y tarda minutos. El
diagnóstico se corre al arrancar el agente y en cada latido; esto se corre a
mano cuando se instala una máquina, y una vez.

**No lee ningún chat.** Abre la lista y la cuenta. Es deliberado: en la máquina
donde se prueba esto, la línea de WhatsApp suele ser la personal de alguien.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agente.jobs.claude_code import invocar, rellenar
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# Más corto que el de `LISTAR`: abrir una página y contar no puede tardar diez
# minutos, y si tarda es que algo está mal y conviene enterarse antes.
TIMEOUT = 300.0

QUE_SIGNIFICA = {
    "sin_permiso": "falta el permiso de sitio de la extensión para web.whatsapp.com",
    "sesion_no_iniciada": "WhatsApp Web pide escanear el código QR",
    "browser_no_disponible": "el deviceId configurado no está entre los Chrome conectados",
}


@dataclass(frozen=True)
class Resultado:
    ok: bool
    motivo: str = ""
    detalle: str = ""
    sesion_iniciada: bool = False
    chats_visibles: int = 0
    costo_usd: float = 0.0
    raw: str = ""

    def como_texto(self) -> str:
        if self.ok:
            return (
                f"[OK ] permiso_sitio    la extensión puede entrar a web.whatsapp.com\n"
                f"[OK ] whatsapp_sesion  sesión iniciada, {self.chats_visibles} chats a la vista"
            )
        explicacion = QUE_SIGNIFICA.get(self.motivo, self.motivo or "no se pudo determinar")
        return f"[MAL] sonda            {explicacion}\n       {self.detalle}"


async def probar(
    *,
    device_id: str,
    claude_bin: str,
    carpeta: Path,
    # Mismo motivo que en `claude_code.invocar`: el timeout lo tiene que aplicar
    # `subprocess.run`, que mata el proceso. `asyncio.timeout` cortaria el await
    # y dejaria a `claude` corriendo suelto.
    timeout: float = TIMEOUT,  # noqa: ASYNC109
    invocador=invocar,
) -> Resultado:
    """Abre WhatsApp Web por el mismo camino que `LISTAR` y reporta si se pudo."""
    if not device_id:
        return Resultado(False, "browser_no_disponible", "AGENTE_DEVICE_ID está vacío")

    prompt = rellenar(carpeta / "prompts" / "prompt-sonda.txt", {"DEVICE_ID": device_id})
    invocacion = await invocador(
        prompt, claude_bin=claude_bin, carpeta=carpeta, con_navegador=True, timeout=timeout
    )

    if not invocacion.ok:
        return Resultado(
            False,
            str(invocacion.codigo or "otro"),
            str(invocacion.detalle.get("motivo", ""))[:300],
            costo_usd=invocacion.costo_usd,
            raw=invocacion.raw,
        )

    return _interpretar(invocacion.datos or {}, invocacion.costo_usd, invocacion.raw)


def _interpretar(datos: dict[str, Any], costo: float, raw: str) -> Resultado:
    if datos.get("status") != "ok":
        motivo = str(datos.get("motivo", "otro"))
        log.warning("sonda_fallo", motivo=motivo)
        return Resultado(
            False, motivo, str(datos.get("detalle", ""))[:300], costo_usd=costo, raw=raw
        )

    if not datos.get("sesion_iniciada"):
        # Llegó a la página pero pide QR. El permiso está; la sesión no.
        return Resultado(
            False,
            "sesion_no_iniciada",
            "la extensión entró, pero WhatsApp no tiene sesión",
            costo_usd=costo,
            raw=raw,
        )

    try:
        chats = max(0, int(datos.get("chats_visibles", 0)))
    except (TypeError, ValueError):
        chats = 0

    log.info("sonda_ok", chats_visibles=chats, costo_usd=costo)
    return Resultado(True, sesion_iniciada=True, chats_visibles=chats, costo_usd=costo, raw=raw)
