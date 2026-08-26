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
from app.core import cola, configuracion, corridas, generacion, mensajes, vendedores
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
    """Un job, y las reglas que valían **en el momento de entregarlo**.

    `payload` es lo que se decidió al encolar y no cambia. `vigente` es lo que
    se lee recién ahora, y existe por una razón concreta:

    El agente revalida `destinos_permitidos` antes de escribir (R4). No es
    desconfianza del backend —ya lo verificó al encolar— es **contra el paso del
    tiempo**: entre que un mensaje se encoló y que el agente lo toma pueden pasar
    minutos, y en el medio alguien pudo cerrar la lista desde el panel.

    Por eso no va en el payload. Un `destinos_permitidos` congelado al encolar
    haría que la segunda verificación mire exactamente lo mismo que la primera,
    que es lo mismo que no tenerla.
    """

    id: str
    tipo: str
    payload: dict[str, Any]
    vigente: dict[str, Any] = Field(default_factory=dict)


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

    # Sólo para `ENVIAR`: es el único que escribe, y leer la configuración en
    # cada entrega de cualquier tipo sería una consulta de más por cada vuelta
    # del bucle de cada máquina.
    vigente: dict[str, Any] = {}
    if job["tipo"] == cola.Tipo.ENVIAR:
        config = await configuracion.obtener(base)
        vigente["destinos_permitidos"] = config.get("destinos_permitidos", [])

    return JobEntregado(
        id=str(job["_id"]), tipo=job["tipo"], payload=job["payload"], vigente=vigente
    )


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

    # El resto de la cadena de generacion. Va despues de `cola.reportar` a
    # proposito: si esto falla, el job ya quedo cerrado con su `raw`, y lo que se
    # pierde es el paso siguiente y no la evidencia de lo que contesto el modelo.
    if cuerpo.ok and job["tipo"] == cola.Tipo.LISTAR:
        await _encolar_redacciones(base, job, cuerpo)

    if cuerpo.ok and job["tipo"] == cola.Tipo.RESOLVER:
        await _encolar_desde_resolver(base, job, cuerpo)

    if cuerpo.ok and job["tipo"] == cola.Tipo.REDACTAR:
        await generacion.guardar_borrador(base, job=job, detalle=cuerpo.detalle)

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


async def _encolar_redacciones(base, job: dict[str, Any], cuerpo: ResultadoJob) -> None:
    """Los chats que leyo `LISTAR` se convierten en un `REDACTAR` cada uno.

    Los chats vienen en `detalle`, ya revisados por el agente: los mal formados
    se descartaron alla y estan contados en `detalle["descartados"]`.

    Si la corrida era un barrido (D27), aca ademas avanza el cursor de la
    maquina: la antiguedad del chat mas nuevo de la tanda es el "hasta" de la
    proxima, y los nombres recien vistos desempatan la frontera.
    """
    payload_listar = job.get("payload") or {}
    estrategia = str(payload_listar.get("estrategia", "recientes"))

    chats = cuerpo.detalle.get("chats") or []
    if not isinstance(chats, list) or not chats:
        log.warning("listar_sin_chats", corrida=str(job.get("corrida_id")), maquina=job["maquina"])
        if estrategia == "barrido":
            #  Tanda vacia: el barrido llego al presente solo si el agente lo
            #  dice. Vacia por un tropiezo no cierra nada — el cursor queda
            #  donde estaba y la proxima corrida reintenta desde ahi.
            await vendedores.registrar_barrido(
                base,
                job["maquina"],
                hasta_dias=None,
                tanda=[],
                completado=bool(cuerpo.detalle.get("fin_del_historial")),
            )
        return

    encoladas = await generacion.encolar_redacciones(
        base,
        corrida_id=job["corrida_id"],
        maquina=job["maquina"],
        chats=chats,
        estrategia=estrategia,
    )

    if estrategia == "barrido" and not encoladas.repetido:
        antiguedades = [int(c.get("antiguedad_dias", 0)) for c in chats if isinstance(c, dict)]
        await vendedores.registrar_barrido(
            base,
            job["maquina"],
            hasta_dias=min(antiguedades) if antiguedades else None,
            tanda=[str(c.get("contacto_nombre", ""))[:120] for c in chats if isinstance(c, dict)],
            # ⚠️ Lo dice el agente, no lo deduce el backend contando. Una tanda
            # corta puede ser "no queda nada más viejo" o "corté por tiempo", y
            # confundirlas daría el barrido por terminado a mitad del historial.
            completado=bool(cuerpo.detalle.get("fin_del_historial")),
        )

    # Que no se encole nada no es lo mismo segun por que. Sin destinos
    # permitidos es el sistema haciendo lo que le pidieron (R4); sin telefono es
    # el modelo negandose a inventar uno. Las dos cosas hay que poder verlas.
    if encoladas.total == 0 and not encoladas.repetido:
        log.warning(
            "ninguna_redaccion_encolada",
            corrida=str(job.get("corrida_id")),
            leidos=len(chats),
            sin_telefono=encoladas.sin_telefono,
            ya_contactados=encoladas.ya_contactados,
            no_permitidos=encoladas.no_permitidos,
        )


async def _encolar_desde_resolver(base, job: dict[str, Any], cuerpo: ResultadoJob) -> None:
    """Los números que el `RESOLVER` leyó del panel de contacto siguen el
    circuito normal: R4 y un `REDACTAR` cada uno. Los que no se pudieron leer
    quedan contados en el detalle del job — no se deduce ninguno."""
    contactos = cuerpo.detalle.get("contactos") or []
    if not isinstance(contactos, list) or not contactos:
        log.warning(
            "resolver_sin_contactos", corrida=str(job.get("corrida_id")), maquina=job["maquina"]
        )
        return

    await generacion.encolar_redacciones_resueltas(
        base, job=job, contactos=[c for c in contactos if isinstance(c, dict)]
    )


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
