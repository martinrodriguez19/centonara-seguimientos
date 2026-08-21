"""Una corrida: lo que pasa cuando el dueño aprieta el botón.

El sistema **no se despierta solo**. No hay cron, no hay temporizador: si nadie
aprieta el botón, no pasa nada. Eso es una característica, no una limitación —
el dueño sabe siempre por qué salieron mensajes hoy.

Y enviar es un **segundo** acto explícito. La corrida genera borradores y se
detiene ahí; nada sale por inacción. El plan anterior tenía una ventana de veto
donde no hacer nada equivalía a aprobar, que era la confusión más probable de
toda la interfaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from bson import ObjectId

from app.core import auditoria, cola, configuracion
from app.core.vendedores import esta_pausada
from app.logging import obtener_logger

log = obtener_logger(__name__)


class TipoCorrida(StrEnum):
    DIAGNOSTICO = "diagnostico"
    """Todas las máquinas corren sus chequeos y reportan. No lee ni escribe nada."""

    GENERACION = "generacion"
    """Leer chats y redactar borradores. Llega en la fase 3."""


class EstadoCorrida(StrEnum):
    GENERANDO = "generando"
    REVISION = "revision"
    ENVIANDO = "enviando"
    TERMINADA = "terminada"
    FRENADA = "frenada"


class NoHayMaquinas(Exception):
    """Ninguna máquina activa y sin pausar. Apretar el botón no haría nada.

    Es un error y no un silencio: alguien apretó esperando que pasara algo, y
    "no pasó nada" sin explicación es peor que un mensaje.
    """


@dataclass(frozen=True)
class Disparo:
    corrida_id: ObjectId
    maquinas: list[str]
    jobs: int


async def maquinas_disponibles(base, *, ahora: datetime | None = None) -> list[dict[str, Any]]:
    """Las máquinas a las que tiene sentido darles trabajo.

    Excluye las inactivas y las que el vendedor pausó desde su barra de menú.
    No excluye las que están sin conexión: si la Mac se prende más tarde, toma
    el job encolado — eso es media razón por la que el agente consulta en vez de
    recibir.
    """
    todas = await base["vendedores"].find({}).to_list(None)
    return [v for v in todas if not esta_pausada(v, ahora=ahora)]


async def disparar(
    base,
    *,
    quien: str,
    tipo: TipoCorrida = TipoCorrida.DIAGNOSTICO,
    modo: str = "prueba",
    n_chats: int | None = None,
    ahora: datetime | None = None,
) -> Disparo:
    """El botón. Crea la corrida y encola un job por máquina.

    Devuelve al instante: encolar es rápido, ejecutar no. El panel muestra el
    progreso preguntando por la corrida, no esperando esta llamada.
    """
    if await configuracion.esta_pausado(base):
        raise Pausado("el sistema está pausado: soltá el kill switch primero")

    momento = ahora or datetime.now(UTC)
    disponibles = await maquinas_disponibles(base, ahora=momento)
    if not disponibles:
        raise NoHayMaquinas("no hay ninguna máquina activa y sin pausar")

    config = await configuracion.obtener(base)
    chats = n_chats or config["n_chats_por_defecto"]
    maquinas = [v["maquina"] for v in disponibles]

    resultado = await base["corridas"].insert_one(
        {
            "disparada_por": quien,
            "tipo": str(tipo),
            "modo": modo,
            "estado": str(EstadoCorrida.GENERANDO),
            "n_chats": chats,
            "maquinas": maquinas,
            "costo_usd": 0.0,
            "creada_en": momento,
            "terminada_en": None,
        }
    )
    corrida_id = resultado.inserted_id

    encolados = 0
    for maquina in maquinas:
        if tipo is TipoCorrida.DIAGNOSTICO:
            payload: dict[str, Any] = {}
            job = cola.Tipo.DIAGNOSTICO
        else:
            payload = {"n_chats": chats, "run_id": str(corrida_id)}
            job = cola.Tipo.LISTAR

        await cola.encolar(
            base,
            tipo=job,
            maquina=maquina,
            corrida_id=corrida_id,
            payload=payload,
            ahora=momento,
        )
        encolados += 1

    await auditoria.registrar(
        base,
        que=auditoria.Que.CORRIDA_DISPARADA,
        quien=quien,
        corrida_id=corrida_id,
        detalle={"tipo": str(tipo), "modo": modo, "maquinas": maquinas},
        ahora=momento,
    )
    log.info("corrida_disparada", corrida=str(corrida_id), tipo=str(tipo), maquinas=len(maquinas))

    return Disparo(corrida_id=corrida_id, maquinas=maquinas, jobs=encolados)


class Pausado(Exception):
    """Se intentó disparar con el kill switch puesto."""


async def progreso(base, corrida_id: ObjectId) -> dict[str, Any] | None:
    """Cómo viene una corrida. Es lo que el panel consulta mientras espera."""
    corrida = await base["corridas"].find_one({"_id": corrida_id})
    if corrida is None:
        return None

    jobs = await base["jobs"].find({"corrida_id": corrida_id}).to_list(None)
    por_estado: dict[str, int] = {}
    for job in jobs:
        por_estado[job["estado"]] = por_estado.get(job["estado"], 0) + 1

    pendientes = por_estado.get("pendiente", 0) + por_estado.get("tomado", 0)

    return {
        "id": str(corrida_id),
        "tipo": corrida["tipo"],
        "modo": corrida["modo"],
        "estado": corrida["estado"],
        "maquinas": corrida["maquinas"],
        "creada_en": corrida["creada_en"],
        "jobs": {"total": len(jobs), "pendientes": pendientes, **por_estado},
        "terminada": pendientes == 0 and len(jobs) > 0,
        "costo_usd": corrida.get("costo_usd", 0.0),
    }


async def en_curso(base) -> dict[str, Any] | None:
    """La corrida más reciente que todavía tiene trabajo pendiente, si hay."""
    ultima = await ultima_corrida(base)
    return ultima if ultima and not ultima["terminada"] else None


async def ultima_corrida(base) -> dict[str, Any] | None:
    """La más reciente, haya terminado o no.

    El panel la necesita terminada también: cuando la generación acaba, lo que
    corresponde es ofrecer "revisá los borradores", no dejar la pantalla como si
    no hubiera pasado nada.
    """
    ultima = await base["corridas"].find_one(sort=[("creada_en", -1)])
    return await progreso(base, ultima["_id"]) if ultima else None


# ---------------------------------------------------------------------------
# El segundo botón: de borradores aprobados a envíos encolados
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Encolado:
    jobs: list[Any]
    mensajes: int
    fuera_de_ventana: bool


async def preparar_envios(
    base, corrida_id: ObjectId, *, quien: str, modo: str = "prueba", ahora: datetime | None = None
) -> Encolado:
    """Encola un `ENVIAR` por cada mensaje que quedó listo.

    **Es el segundo acto explícito.** La corrida generó borradores y se detuvo;
    esto es lo que pasa cuando alguien mira y aprieta enviar. Nada llega acá por
    inacción ni por un temporizador.

    Los envíos salen barajados y espaciados, con el canario adelante: los tres
    primeros y después un hueco de diez minutos. Si esos tres fallan, frenar
    cuesta diecisiete mensajes menos que enterarse al final.
    """
    from app.core import cola, guardrails, mensajes
    from app.core.estados import Estado

    momento = ahora or datetime.now(UTC)
    config = await configuracion.obtener(base)

    if config.get("pausa_global"):
        raise Pausado("el sistema está pausado")

    # La ventana horaria se verifica ACÁ y no al validar: generar a las ocho de
    # la noche está bien, enviar no. Es el único momento en que la pregunta
    # "¿es hora de mandar?" tiene sentido.
    fuera = guardrails.revisar_ventana(config.get("ventana", {}), ahora=momento)
    if fuera:
        raise FueraDeVentana(fuera.detalle)

    listos = [
        m for m in await mensajes.de_la_corrida(base, corrida_id) if m["estado"] == Estado.EN_ESPERA
    ]
    if not listos:
        return Encolado(jobs=[], mensajes=0, fuera_de_ventana=False)

    # Un job por mensaje, agrupado por máquina: cada agente tiene su propia cola
    # y su propio ritmo, así que el espaciado se calcula por separado.
    por_maquina: dict[str, list[dict[str, Any]]] = {}
    for mensaje in listos:
        por_maquina.setdefault(mensaje["maquina"], []).append(mensaje)

    jobs: list[Any] = []
    for maquina, suyos in por_maquina.items():
        payloads = [
            {
                "mensaje_id": str(m["_id"]),
                "contacto_id": m["contacto_id"],
                "contacto_nombre": m.get("contacto_nombre", ""),
                "texto": m["texto"],
                "modo": modo,
            }
            for m in suyos
        ]
        jobs += await cola.encolar_envios(
            base,
            maquina=maquina,
            corrida_id=corrida_id,
            payloads=payloads,
            pausa=tuple(config.get("pausa_entre_envios_s", [45, 180])),
            ahora=momento,
        )

    await base["corridas"].update_one(
        {"_id": corrida_id},
        {"$set": {"estado": str(EstadoCorrida.ENVIANDO), "modo": modo}},
    )
    await auditoria.registrar(
        base,
        que=auditoria.Que.CORRIDA_DISPARADA,
        quien=quien,
        corrida_id=corrida_id,
        detalle={"accion": "enviar", "mensajes": len(listos), "modo": modo},
        ahora=momento,
    )
    log.info("envios_encolados", corrida=str(corrida_id), mensajes=len(listos), modo=modo)

    return Encolado(jobs=jobs, mensajes=len(listos), fuera_de_ventana=False)


class FueraDeVentana(Exception):
    """Se intentó enviar fuera del horario hábil."""


async def revisar_canario(base, corrida_id: ObjectId, *, quien: str = "sistema") -> bool:
    """¿Fallaron los primeros envíos? Si sí, frena todo.

    Se llama después de cada `ENVIAR` que termina. Mientras los primeros
    `CANARIO` jobs no hayan terminado todos, no decide nada: con uno solo
    reportado no se puede distinguir mala suerte de sistema roto.

    Devuelve `True` si frenó.
    """
    from app.core import cola

    jobs = (
        await base["jobs"]
        .find({"corrida_id": corrida_id, "tipo": str(cola.Tipo.ENVIAR)})
        .sort("disponible_desde", 1)
        .to_list(None)
    )
    primeros = jobs[: cola.CANARIO]

    if len(primeros) < cola.CANARIO:
        return False
    if any(j["estado"] not in (cola.EstadoJob.LISTO, cola.EstadoJob.FALLIDO) for j in primeros):
        return False
    if any(j["estado"] == cola.EstadoJob.LISTO for j in primeros):
        return False

    # Los tres terminaron y ninguno salió bien.
    await configuracion.pausar(base, pausado=True, quien=quien)
    await base["corridas"].update_one(
        {"_id": corrida_id}, {"$set": {"estado": str(EstadoCorrida.FRENADA)}}
    )
    await auditoria.registrar(
        base,
        que=auditoria.Que.KILL_SWITCH,
        quien=quien,
        corrida_id=corrida_id,
        detalle={"motivo": "canario_fallido", "revisados": cola.CANARIO},
    )
    log.error("canario_fallido", corrida=str(corrida_id), revisados=cola.CANARIO)
    return True
