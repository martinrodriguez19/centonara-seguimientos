"""La cola de trabajo, sobre MongoDB.

Sin Redis: para este volumen, un `findOneAndUpdate` con `sort` da exclusión
mutua sin condiciones de carrera, y `disponible_desde` implementa el espaciado
sin más infraestructura (D7).

Tres cosas que parecen detalles y no lo son:

- **`tomar` es atómico.** Buscar y después marcar sería una condición de
  carrera, y una condición de carrera acá se traduce en un cliente recibiendo
  el mismo mensaje dos veces.
- **El espaciado es `disponible_desde`, no `sleep`.** Un ritmo fijo es lo que
  dispara bloqueos de línea, y un hilo dormido no sobrevive a un reinicio del
  proceso.
- **Los reintentos son por código de motivo, no genéricos.** Reintentar un envío
  que abortó porque el contacto no coincidía es la forma exacta de convertir un
  aborto correcto en un error real.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, ReturnDocument

from app.logging import obtener_logger

log = obtener_logger(__name__)

# Cuántas veces se reintenta un job que falló con un código reintentable.
MAX_INTENTOS = 3

# Un job que quedó TOMADO más que esto es de un agente que se murió: la Mac se
# apagó, se cortó la red, alguien mató el proceso. Vuelve a la cola.
#
# Generoso a propósito: `LISTAR` abre el navegador y puede tardar minutos. Un
# valor corto haría que un job lento se ejecute dos veces, que es peor que uno
# que tarda en recuperarse.
SEGUNDOS_PARA_DAR_POR_COLGADO = 15 * 60

# Espaciado entre envíos. Aleatorio, siempre (03-REGLAS §4).
PAUSA_ENTRE_ENVIOS = (45, 180)

# El canario: cuántos salen primero, y cuánto se espera antes de soltar el
# resto. Si los tres fallan, algo está roto y frenar cuesta diecisiete mensajes
# menos que enterarse al final.
CANARIO = 3
ESPERA_CANARIO_S = 10 * 60


class Tipo(StrEnum):
    LISTAR = "LISTAR"
    REDACTAR = "REDACTAR"
    ENVIAR = "ENVIAR"
    DIAGNOSTICO = "DIAGNOSTICO"


class EstadoJob(StrEnum):
    PENDIENTE = "pendiente"
    TOMADO = "tomado"
    LISTO = "listo"
    FALLIDO = "fallido"


class Codigo(StrEnum):
    """Por qué falló un job. La política de reintento cuelga de acá.

    Está en el código y no en un `if` desparramado por el llamador: si mañana
    alguien agrega un código nuevo y se olvida de decidir si se reintenta, el
    test de abajo lo agarra.
    """

    CONTACTO_NO_COINCIDE = "CONTACTO_NO_COINCIDE"
    NUMERO_NO_RESOLUBLE = "NUMERO_NO_RESOLUBLE"
    DESTINO_NO_PERMITIDO = "DESTINO_NO_PERMITIDO"
    SIN_CONFIRMAR = "SIN_CONFIRMAR"
    SELECTOR_ROTO = "SELECTOR_ROTO"
    CAMPO_NO_VACIO = "CAMPO_NO_VACIO"
    CHAT_NO_ABRE = "CHAT_NO_ABRE"
    SESION_CAIDA = "SESION_CAIDA"
    TIMEOUT = "TIMEOUT"
    ERROR_INESPERADO = "ERROR_INESPERADO"

    @property
    def reintenta(self) -> bool:
        """¿Tiene sentido volver a intentarlo?

        Los cuatro que devuelven `False` no son fallas transitorias: son el
        sistema haciendo su trabajo. `CONTACTO_NO_COINCIDE` significa que la
        verificación de identidad abortó el envío — reintentar sería insistir
        con el chat equivocado.

        `SIN_CONFIRMAR` es distinto y peor: se apretó enviar y no se pudo
        confirmar. El mensaje **puede haber salido**. Reintentar sería mandarlo
        dos veces; por eso alerta en vez de reintentar.
        """
        return self not in _NO_SE_REINTENTAN

    @property
    def frena_corrida(self) -> bool:
        """`SELECTOR_ROTO` frena todo, no sólo este job.

        Si el DOM de WhatsApp cambió, los envíos siguientes tienen exactamente
        el mismo problema. Seguir es gastar intentos y arriesgar escrituras en
        una página que ya no entendemos.
        """
        return self is Codigo.SELECTOR_ROTO


_NO_SE_REINTENTAN = frozenset(
    {
        Codigo.CONTACTO_NO_COINCIDE,
        Codigo.NUMERO_NO_RESOLUBLE,
        Codigo.DESTINO_NO_PERMITIDO,
        Codigo.SIN_CONFIRMAR,
        Codigo.SELECTOR_ROTO,
    }
)


@dataclass(frozen=True)
class Reporte:
    """Qué pasó con el job después de reportarlo."""

    estado: EstadoJob
    intentos: int
    reintenta: bool
    frena_corrida: bool


def _ahora(ahora: datetime | None = None) -> datetime:
    return ahora or datetime.now(UTC)


# ---------------------------------------------------------------------------
# Encolar
# ---------------------------------------------------------------------------


async def encolar(
    base,
    *,
    tipo: Tipo,
    maquina: str,
    corrida_id: ObjectId | None = None,
    payload: dict[str, Any] | None = None,
    contexto: dict[str, Any] | None = None,
    disponible_desde: datetime | None = None,
    ahora: datetime | None = None,
) -> ObjectId:
    """Pone un job en la cola. Disponible ya, salvo que se diga otra cosa.

    `contexto` es lo que el backend necesita recordar para interpretar el
    resultado, y que **el agente no recibe**: `JobEntregado` sólo lleva
    `payload`. La distincion importa en `REDACTAR`, que redacta sin navegador y
    por eso no lleva telefono: el numero del contacto queda de este lado, pegado
    al job que lo va a necesitar cuando vuelva el texto.
    """
    momento = _ahora(ahora)
    documento = {
        "tipo": str(tipo),
        "maquina": maquina,
        "corrida_id": corrida_id,
        "payload": payload or {},
        "contexto": contexto or {},
        "estado": str(EstadoJob.PENDIENTE),
        "disponible_desde": disponible_desde or momento,
        "intentos": 0,
        # R5: presentes desde el principio, también cuando sale bien. Si se
        # agregan recién cuando falla, el día que hagan falta no están.
        "raw": "",
        "stderr": "",
        "costo_usd": 0.0,
        "creado_en": momento,
        "tomado_en": None,
        "terminado_en": None,
    }
    resultado = await base["jobs"].insert_one(documento)
    return resultado.inserted_id


def escalonar(
    cantidad: int,
    *,
    desde: datetime,
    pausa: tuple[int, int] = PAUSA_ENTRE_ENVIOS,
    canario: int = 0,
    espera_canario: float = ESPERA_CANARIO_S,
    aleatorio: random.Random | None = None,
) -> list[datetime]:
    """Los momentos en que sale cada mensaje, con pausas aleatorias.

    Función pura: sin base de datos y sin reloj propio, así se puede testear
    que dos corridas nunca dan el mismo patrón.

    **La pausa nunca es fija.** Lo que dispara bloqueos de línea no es
    principalmente el volumen: son los patrones de tiempo regulares. Un
    `sleep(60)` entre envíos es un bug con consecuencias sobre la herramienta de
    trabajo de una persona.

    El primero sale enseguida; a partir del segundo se acumulan las pausas.
    """
    if cantidad < 0:
        raise ValueError("cantidad negativa")

    dado = aleatorio or random.Random()
    minimo, maximo = pausa
    if minimo > maximo:
        raise ValueError(f"pausa inválida: {pausa}")

    momentos = []
    acumulado = 0.0
    for indice in range(cantidad):
        if indice:
            acumulado += dado.uniform(minimo, maximo)
        # El canario: después del enésimo se abre un hueco grande, para que
        # alguien pueda mirar si los primeros llegaron antes de que salgan los
        # otros diecisiete.
        if canario and indice == canario:
            acumulado += espera_canario
        momentos.append(desde + timedelta(seconds=acumulado))
    return momentos


async def encolar_envios(
    base,
    *,
    maquina: str,
    corrida_id: ObjectId,
    payloads: list[dict[str, Any]],
    pausa: tuple[int, int] = PAUSA_ENTRE_ENVIOS,
    canario: int = CANARIO,
    espera_canario: float = ESPERA_CANARIO_S,
    aleatorio: random.Random | None = None,
    ahora: datetime | None = None,
) -> list[ObjectId]:
    """Encola una tanda de envíos, espaciada y **en orden aleatorio**.

    Las dos cosas importan y son distintas: el espaciado evita el patrón de
    tiempo regular, y el barajado evita que el recorrido sea siempre el mismo
    —siempre los mismos contactos primero, siempre a la misma hora—, que es otra
    forma de patrón.
    """
    dado = aleatorio or random.Random()
    barajados = list(payloads)
    dado.shuffle(barajados)

    momentos = escalonar(
        len(barajados),
        desde=_ahora(ahora),
        pausa=pausa,
        canario=canario,
        espera_canario=espera_canario,
        aleatorio=dado,
    )

    return [
        await encolar(
            base,
            tipo=Tipo.ENVIAR,
            maquina=maquina,
            corrida_id=corrida_id,
            payload=payload,
            disponible_desde=momento,
            ahora=ahora,
        )
        for payload, momento in zip(barajados, momentos, strict=True)
    ]


# ---------------------------------------------------------------------------
# Tomar
# ---------------------------------------------------------------------------


async def tomar(base, maquina: str, *, ahora: datetime | None = None) -> dict[str, Any] | None:
    """Entrega **un** job a esta máquina, o `None` si no hay.

    Es la consulta que corre cada 10 segundos por cada máquina, y la razón por
    la que existe el índice `{estado, maquina, disponible_desde}`.

    `find_one_and_update` es una sola operación atómica en el servidor: dos
    agentes que consulten en el mismo milisegundo no pueden llevarse el mismo
    job. Buscar y después marcar —dos operaciones— sí sería una carrera, y esa
    carrera se traduce en un cliente recibiendo el mismo mensaje dos veces.
    """
    momento = _ahora(ahora)
    return await base["jobs"].find_one_and_update(
        {
            "estado": str(EstadoJob.PENDIENTE),
            "maquina": maquina,
            "disponible_desde": {"$lte": momento},
        },
        {
            "$set": {"estado": str(EstadoJob.TOMADO), "tomado_en": momento},
            "$inc": {"intentos": 1},
        },
        # El más viejo primero: sin esto, un job podría quedarse esperando para
        # siempre mientras entran otros.
        sort=[("disponible_desde", ASCENDING)],
        return_document=ReturnDocument.AFTER,
    )


# ---------------------------------------------------------------------------
# Reportar
# ---------------------------------------------------------------------------


async def reportar(
    base,
    job_id: ObjectId,
    *,
    ok: bool,
    codigo: Codigo | None = None,
    detalle: dict[str, Any] | None = None,
    raw: str = "",
    stderr: str = "",
    costo_usd: float = 0.0,
    max_intentos: int = MAX_INTENTOS,
    ahora: datetime | None = None,
) -> Reporte:
    """Cierra un job, o lo devuelve a la cola si vale la pena reintentarlo.

    `raw` y `stderr` se guardan **siempre**, también cuando sale bien (R5). Es
    lo primero que se lee cuando algo falla, y sólo está ahí si se puso desde el
    principio.
    """
    momento = _ahora(ahora)
    job = await base["jobs"].find_one({"_id": job_id})
    if job is None:
        raise JobDesconocido(job_id)

    comun = {
        "raw": raw,
        "stderr": stderr,
        "costo_usd": costo_usd,
        "codigo": str(codigo) if codigo else None,
        "detalle": detalle or {},
    }

    if ok:
        await base["jobs"].update_one(
            {"_id": job_id},
            {"$set": {**comun, "estado": str(EstadoJob.LISTO), "terminado_en": momento}},
        )
        return Reporte(EstadoJob.LISTO, job["intentos"], reintenta=False, frena_corrida=False)

    reintentable = codigo is None or codigo.reintenta
    quedan = job["intentos"] < max_intentos

    if reintentable and quedan:
        # Vuelve a la cola con un respiro, para no reintentar en bucle contra
        # algo que todavía no se recuperó.
        await base["jobs"].update_one(
            {"_id": job_id},
            {
                "$set": {
                    **comun,
                    "estado": str(EstadoJob.PENDIENTE),
                    "disponible_desde": momento + timedelta(seconds=30 * job["intentos"]),
                    "tomado_en": None,
                }
            },
        )
        log.info("job_reintenta", job=str(job_id), intentos=job["intentos"], codigo=str(codigo))
        return Reporte(EstadoJob.PENDIENTE, job["intentos"], reintenta=True, frena_corrida=False)

    await base["jobs"].update_one(
        {"_id": job_id},
        {"$set": {**comun, "estado": str(EstadoJob.FALLIDO), "terminado_en": momento}},
    )
    log.warning(
        "job_fallido",
        job=str(job_id),
        intentos=job["intentos"],
        codigo=str(codigo),
        reintentable=reintentable,
    )
    return Reporte(
        EstadoJob.FALLIDO,
        job["intentos"],
        reintenta=False,
        frena_corrida=bool(codigo and codigo.frena_corrida),
    )


class JobDesconocido(Exception):
    """Se reportó un job que no existe. Es un bug, no una condición esperada."""

    def __init__(self, job_id: ObjectId) -> None:
        super().__init__(f"no existe el job {job_id}")


# ---------------------------------------------------------------------------
# Recuperación
# ---------------------------------------------------------------------------


async def recuperar_colgados(
    base,
    *,
    segundos: int = SEGUNDOS_PARA_DAR_POR_COLGADO,
    ahora: datetime | None = None,
) -> int:
    """Devuelve a la cola los jobs de agentes que se murieron.

    Una Mac que se apaga a mitad de corrida deja su job en `tomado` para
    siempre. Esto lo devuelve a `pendiente` para que lo tome otro intento.

    Corre en APScheduler, y es la mitad de lo que hace que el escenario de caos
    "apagar una máquina a mitad de corrida" no pierda trabajo. La otra mitad es
    que el agente reporte sus jobs en curso al apagarse ordenadamente.

    No resetea `intentos`: un job que cuelga tres veces seguidas termina en
    `fallido`, que es lo correcto. Si no, un envío que hace colgar al agente
    entraría en un bucle infinito.
    """
    corte = _ahora(ahora) - timedelta(seconds=segundos)
    resultado = await base["jobs"].update_many(
        {"estado": str(EstadoJob.TOMADO), "tomado_en": {"$lt": corte}},
        {"$set": {"estado": str(EstadoJob.PENDIENTE), "tomado_en": None}},
    )
    if resultado.modified_count:
        log.warning("jobs_colgados_recuperados", cantidad=resultado.modified_count)
    return resultado.modified_count


async def pendientes(base, *, corrida_id: ObjectId | None = None) -> int:
    """Cuántos jobs quedan por hacer. Lo usa el panel para el progreso."""
    filtro: dict[str, Any] = {"estado": {"$in": [str(EstadoJob.PENDIENTE), str(EstadoJob.TOMADO)]}}
    if corrida_id is not None:
        filtro["corrida_id"] = corrida_id
    return await base["jobs"].count_documents(filtro)
