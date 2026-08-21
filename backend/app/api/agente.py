"""Los cuatro endpoints que consume el agente de cada máquina.

Contrato en `docs/02-ARQUITECTURA.md` §4.1, que manda sobre este archivo: si el
código se desvía, el que está mal es el código.

`GET /jobs/proximo` es un `GET` normal que devuelve un job o `204`. **No es
long-poll.** El plan anterior sostenía la conexión 25 segundos, lo que dependía
de que Render y Cloudflare no la cortaran — algo que nunca se verificó, y que
Cloudflare corta a los 100 s en los planes que usamos. Con máquinas consultando
cada 10 segundos, un `GET` alcanza y no depende de nadie.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app import db
from app.core import cola, configuracion, corridas, mensajes, vendedores
from app.logging import obtener_logger

log = obtener_logger(__name__)

router = APIRouter(prefix="/api/agente", tags=["agente"])


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------


async def maquina_autenticada(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """La máquina dueña del token del encabezado, o `401`.

    Un token vacío, mal formado o inventado dan todos lo mismo: `401` sin
    detalle. Distinguirlos le diría a quien prueba tokens cuál se acercó más.
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    vendedor = await vendedores.autenticar(db.obtener_base(), token)
    if vendedor is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido")
    return vendedor


Maquina = Annotated[dict[str, Any], Depends(maquina_autenticada)]


# ---------------------------------------------------------------------------
# Esquemas
# ---------------------------------------------------------------------------


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Registro(Estricto):
    version: Annotated[str, Field(max_length=32)]
    diagnostico: dict[str, str] = Field(default_factory=dict)


class Latido(Estricto):
    diagnostico: dict[str, str] = Field(default_factory=dict)


class JobEntregado(BaseModel):
    id: str
    tipo: str
    payload: dict[str, Any]


class ResultadoJob(Estricto):
    """Lo que el agente reporta cuando termina un job.

    `raw` y `stderr` no tienen valor por defecto vacío por casualidad: son
    obligatorios en el contrato y opcionales en el esquema, para que un agente
    viejo que todavía no los manda no falle — pero se guardan siempre, también
    en éxito (R5).
    """

    ok: bool
    codigo: cola.Codigo | None = None
    detalle: dict[str, Any] = Field(default_factory=dict)
    raw: Annotated[str, Field(max_length=200_000)] = ""
    stderr: Annotated[str, Field(max_length=200_000)] = ""
    costo_usd: Annotated[float, Field(ge=0)] = 0.0


class RespuestaRegistro(BaseModel):
    maquina: str
    activo: bool
    pausada: bool
    puede_enviar: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/registrar", response_model=RespuestaRegistro)
async def registrar(cuerpo: Registro, maquina: Maquina) -> RespuestaRegistro:
    """El agente se presenta al arrancar.

    Le devolvemos en qué situación está, para que el ícono de la barra de menú
    pueda decir algo útil antes de pedir el primer job.
    """
    await vendedores.registrar_latido(
        db.obtener_base(),
        maquina["maquina"],
        diagnostico=cuerpo.diagnostico,
        version_agente=cuerpo.version,
    )
    log.info("agente_registrado", maquina=maquina["maquina"], version=cuerpo.version)
    return RespuestaRegistro(
        maquina=maquina["maquina"],
        activo=bool(maquina.get("activo")),
        pausada=vendedores.esta_pausada(maquina),
        puede_enviar=vendedores.puede_enviar(maquina),
    )


@router.get(
    "/jobs/proximo",
    response_model=JobEntregado,
    responses={
        204: {"description": "No hay trabajo"},
        423: {"description": "Pausa global o máquina pausada"},
    },
)
async def proximo_job(maquina: Maquina):
    """Un job para esta máquina, o nada.

    Tres respuestas posibles, y la del medio importa: `423` significa "no
    preguntes por un rato", y es lo que hace que el kill switch tenga efecto en
    segundos sin que el backend tenga que empujar nada.
    """
    base = db.obtener_base()

    if await configuracion.esta_pausado(base):
        raise HTTPException(status.HTTP_423_LOCKED, "pausa global")

    if vendedores.esta_pausada(maquina):
        raise HTTPException(status.HTTP_423_LOCKED, "máquina pausada")

    # La consulta es el latido: una máquina que pregunta está viva, tenga o no
    # trabajo. Sin esto, una Mac sana sin nada que hacer aparecería caída.
    await vendedores.registrar_latido(base, maquina["maquina"])

    job = await cola.tomar(base, maquina["maquina"])

    # Un `ENVIAR` entregado significa que el agente lo tiene: a partir de acá le
    # va a escribir a una persona. Es el único momento del sistema en que
    # corresponde marcar el mensaje como ENVIANDO — y por eso está pegado a la
    # entrega y no en otro lado.
    if job is not None and job["tipo"] == cola.Tipo.ENVIAR:
        await _marcar_enviando(base, job)

    if job is None:
        # Un `Response` crudo y no `None`: con `response_model` puesto, FastAPI
        # intentaría validar el `None` contra el esquema y devolvería un 500.
        # Devolver el Response lo saltea, que es lo correcto — un 204 no lleva
        # cuerpo que validar.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return JobEntregado(id=str(job["_id"]), tipo=job["tipo"], payload=job["payload"])


@router.post("/jobs/{job_id}/resultado")
async def reportar_resultado(job_id: str, cuerpo: ResultadoJob, maquina: Maquina) -> dict[str, Any]:
    """El agente reporta cómo le fue.

    Se verifica que el job sea **de esta máquina**: sin eso, un token filtrado
    podría cerrar los jobs de otra, y el sistema daría por enviado algo que no
    salió.
    """
    from bson import ObjectId
    from bson.errors import InvalidId

    base = db.obtener_base()
    try:
        identificador = ObjectId(job_id)
    except InvalidId:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe ese job") from None

    job = await base["jobs"].find_one({"_id": identificador})
    if job is None or job["maquina"] != maquina["maquina"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe ese job")

    reporte = await cola.reportar(
        base,
        identificador,
        ok=cuerpo.ok,
        codigo=cuerpo.codigo,
        detalle=cuerpo.detalle,
        raw=cuerpo.raw,
        stderr=cuerpo.stderr,
        costo_usd=cuerpo.costo_usd,
    )

    # El resultado del envío decide qué pasa con el mensaje: salió, vuelve a la
    # cola, o no sale más. La cola ya decidió si se reintenta; acá sólo se
    # traduce esa decisión al estado del mensaje.
    if job["tipo"] == cola.Tipo.ENVIAR:
        await _resolver_mensaje(base, job, cuerpo, reporte, maquina["maquina"])
        await corridas.revisar_canario(base, job["corrida_id"], quien=maquina["maquina"])

    if reporte.frena_corrida:
        # El DOM de WhatsApp cambió: los envíos siguientes tienen exactamente el
        # mismo problema. Frenar todo es más barato que gastar intentos y
        # arriesgar escrituras en una página que ya no entendemos.
        await configuracion.pausar(base, pausado=True, quien=maquina["maquina"])
        log.error("corrida_frenada", motivo=str(cuerpo.codigo), maquina=maquina["maquina"])

    return {
        "estado": str(reporte.estado),
        "reintenta": reporte.reintenta,
        "frena_corrida": reporte.frena_corrida,
    }


@router.post("/latido")
async def latido(cuerpo: Latido, maquina: Maquina) -> dict[str, Any]:
    """Cada 30 segundos, para que el panel sepa que sigue viva."""
    await vendedores.registrar_latido(
        db.obtener_base(), maquina["maquina"], diagnostico=cuerpo.diagnostico
    )
    return {"ok": True, "pausada": vendedores.esta_pausada(maquina)}


# ---------------------------------------------------------------------------
# El puente entre un job de envío y el estado de su mensaje
# ---------------------------------------------------------------------------


async def _marcar_enviando(base, job: dict[str, Any]) -> None:
    """El agente tomó el envío. Si el mensaje ya no está listo, no se manda.

    Puede pasar: entre que se encoló y que el agente lo tomó, alguien lo vetó
    desde el panel o venció. El job se descarta en silencio y el agente recibe
    un payload que no va a usar — es preferible a mandar algo que una persona
    decidió frenar.
    """
    from bson import ObjectId

    from app.core.estados import Estado, TransicionInvalida

    mensaje_id = job["payload"].get("mensaje_id")
    if not mensaje_id:
        return

    try:
        await mensajes.mover(base, ObjectId(mensaje_id), Estado.ENVIANDO)
    except (TransicionInvalida, mensajes.CarreraDeEstados, mensajes.MensajeDesconocido) as error:
        log.warning("envio_ya_no_corresponde", job=str(job["_id"]), motivo=str(error))


async def _resolver_mensaje(base, job, cuerpo: ResultadoJob, reporte, maquina: str) -> None:
    from bson import ObjectId

    from app.core.estados import Estado, Motivo, TransicionInvalida

    mensaje_id = job["payload"].get("mensaje_id")
    if not mensaje_id:
        return
    identificador = ObjectId(mensaje_id)

    try:
        if cuerpo.ok:
            await mensajes.mover(base, identificador, Estado.ENVIADO, quien=maquina)
        elif reporte.reintenta:
            # Vuelve a la cola. El mensaje vuelve a estar listo, no descartado:
            # todavía puede salir.
            await mensajes.mover(base, identificador, Estado.EN_ESPERA, quien=maquina)
        else:
            await mensajes.mover(
                base,
                identificador,
                Estado.DESCARTADO,
                motivo=(
                    Motivo.SIN_CONFIRMAR
                    if cuerpo.codigo is cola.Codigo.SIN_CONFIRMAR
                    else Motivo.FALLIDO
                ),
                quien=maquina,
                senales=[str(cuerpo.codigo)] if cuerpo.codigo else None,
            )
    except (TransicionInvalida, mensajes.CarreraDeEstados, mensajes.MensajeDesconocido) as error:
        log.warning("mensaje_no_se_pudo_resolver", job=str(job["_id"]), motivo=str(error))
