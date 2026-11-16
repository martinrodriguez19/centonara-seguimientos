"""La página de conexiones: pública, y sólo para conexiones (D71).

Sin login, a pedido del dueño: los vendedores la abren desde el celular, ven si
se les cayó WhatsApp o Claude, y aprietan un botón. Por eso este router es
**propio** y sus respuestas tienen **modelo propio**: un campo nuevo en el
estado de la máquina no puede filtrarse acá por accidente. `test_publico.py`
fija la lista exacta de campos.

Lo que esto NO muestra nunca: números, chats, corridas, mensajes, el mail de la
cuenta de Claude, el QR o un código. El QR aparece en la pantalla física de la
máquina; el código de Claude lo pasa el dueño de persona a persona.

Lo que esto permite: encolar una reconexión (abre una ventana en la
computadora de la oficina), con tope por máquina y tipo, y cada una auditada.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Path, status
from pydantic import BaseModel

from app import db
from app.core import auditoria, conexiones, configuracion, horarios
from app.logging import obtener_logger

log = obtener_logger(__name__)

router = APIRouter(prefix="/api/publico", tags=["publico"])

# El mismo corte que el panel usa para "online": tres latidos perdidos.
SEGUNDOS_SIN_LATIDO = 90

# Cuánto se muestra una reconexión como "en curso" en la página.
MINUTOS_RECONEXION_VISIBLE = 15

Semaforo = Literal["ok", "caida", "desconocido"]
EstadoMaquina = Literal["viva", "dormida", "apagada"]
TipoReconexion = Literal["whatsapp", "claude", "verificar"]

_ACCION_DE = {
    "whatsapp": "abrir_whatsapp",
    "claude": "abrir_claude",
    "verificar": "verificar",
}
_TIPO_DE = {accion: tipo for tipo, accion in _ACCION_DE.items()}


class Reconexion(BaseModel):
    tipo: TipoReconexion
    pedida_en: datetime
    #  La máquina ya abrió la ventana (o corrió la verificación).
    hecha: bool
    #  `vencida`: la máquina no la tomó a tiempo (apagada o dormida).
    vencida: bool


class ConexionPublica(BaseModel):
    maquina: str
    nombre: str
    estado: EstadoMaquina
    whatsapp: Semaforo
    claude: Semaforo
    reconexion: Reconexion | None = None


class RespuestaConexiones(BaseModel):
    maquinas: list[ConexionPublica]
    #  A quién pedirle el código de Claude. Un nombre, nada más.
    pedir_codigo_a: str


class Pedido(BaseModel):
    ok: bool
    reconexion: Reconexion


def _estado_maquina(vendedor: dict, config: dict, ahora: datetime) -> EstadoMaquina:
    latido = conexiones._utc(vendedor.get("ultimo_latido"))
    if latido is not None and ahora - latido < timedelta(seconds=SEGUNDOS_SIN_LATIDO):
        return "viva"
    if horarios.descanso_hasta(config, ahora) is not None or horarios.dormida_desde_el_descanso(
        config, latido, ahora
    ):
        return "dormida"
    return "apagada"


def _reconexion(vendedor: dict, ahora: datetime) -> Reconexion | None:
    accion = conexiones.ultima_accion(
        vendedor,
        conexiones.ACCIONES,
        desde=ahora - timedelta(minutes=MINUTOS_RECONEXION_VISIBLE),
    )
    if accion is None:
        return None
    hecha = accion.get("hecha_en") is not None
    vence = conexiones._utc(accion.get("vence_en"))
    return Reconexion(
        tipo=_TIPO_DE[accion["tipo"]],
        pedida_en=conexiones._utc(accion["pedida_en"]),
        hecha=hecha,
        vencida=not hecha and vence is not None and vence <= ahora,
    )


def _publica(vendedor: dict, config: dict, ahora: datetime) -> ConexionPublica:
    return ConexionPublica(
        maquina=vendedor["maquina"],
        nombre=vendedor.get("nombre") or vendedor["maquina"],
        estado=_estado_maquina(vendedor, config, ahora),
        whatsapp=conexiones.semaforo_whatsapp(vendedor, config),
        claude=conexiones.semaforo_claude(vendedor),
        reconexion=_reconexion(vendedor, ahora),
    )


@router.get("/conexiones", response_model=RespuestaConexiones)
async def ver_conexiones() -> RespuestaConexiones:
    """Una tarjeta por máquina activa, con sus dos semáforos."""
    base = db.obtener_base()
    ahora = datetime.now(UTC)
    config = await configuracion.obtener(base)
    vendedores = await base["vendedores"].find({"activo": True}).sort("nombre", 1).to_list(None)
    return RespuestaConexiones(
        maquinas=[_publica(v, config, ahora) for v in vendedores],
        pedir_codigo_a=str(config.get("cuenta_claude_codigo_quien") or "")[:60],
    )


@router.post(
    "/conexiones/{maquina}/{tipo}",
    response_model=Pedido,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"description": "No existe"}, 429: {"description": "Muy seguido"}},
)
async def reconectar(
    maquina: Annotated[str, Path(max_length=40, pattern=r"^[a-z0-9][a-z0-9-]*$")],
    tipo: TipoReconexion,
    x_forwarded_for: Annotated[str | None, Header()] = None,
) -> Pedido:
    """Encola una reconexión. La máquina la ve en su próximo latido (D70)."""
    base = db.obtener_base()
    ahora = datetime.now(UTC)
    vendedor = await base["vendedores"].find_one({"maquina": maquina, "activo": True})
    if vendedor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe esa computadora")

    config = await configuracion.obtener(base)
    accion = _ACCION_DE[tipo]
    #  El mail viaja a la máquina, para la notificación. No vuelve en la respuesta.
    datos = (
        {"mail": str(config.get("cuenta_claude_mail") or "")} if accion == "abrir_claude" else {}
    )
    try:
        pedida = await conexiones.pedir(base, vendedor, accion, datos=datos, ahora=ahora)
    except conexiones.DemasiadoPronto as error:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Ya se pidió recién. Probá de nuevo en {error.segundos} segundos.",
        ) from error

    ip = (x_forwarded_for or "").split(",")[0].strip()[:60]
    await auditoria.registrar(
        base,
        que=auditoria.Que.RECONEXION_PEDIDA,
        quien="publico",
        detalle={"maquina": maquina, "tipo": tipo, "ip": ip},
    )
    return Pedido(
        ok=True,
        reconexion=Reconexion(tipo=tipo, pedida_en=pedida["pedida_en"], hecha=False, vencida=False),
    )
