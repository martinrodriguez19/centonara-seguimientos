"""Una corrida: lo que pasa cuando el dueño aprieta el botón.

El sistema **no se despierta solo**. No hay cron, no hay temporizador: si nadie
aprieta el botón, no pasa nada. Eso es una característica, no una limitación —
el dueño sabe siempre por qué salieron mensajes hoy.

**Enviar de verdad es un segundo acto explícito.** Nada le llega a un cliente
por inacción. Los *borradores*, en cambio, se dejan solos (D36): cada redacción
que pasa los guardrails se escribe como borrador de WhatsApp apenas vuelve —
el vendedor los encuentra en sus chats al día siguiente, y quien decide si algo
sale sigue siendo una persona: él, chat por chat, o el dueño con el botón de
Envío.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from bson import ObjectId

from app.core import auditoria, cola, configuracion
from app.core.vendedores import esta_pausada, sin_cuota_hasta
from app.logging import obtener_logger

log = obtener_logger(__name__)

# D59. Para entrar a una corrida, la máquina tiene que haber dado señales hace
# menos que esto. Es el mismo número que la alerta `maquina_caida`: que una PC
# parpadee no la deja afuera; que lleve diez minutos callada, sí.
MINUTOS_SIN_LATIDO = 10

# D59. Una máquina de una corrida en curso que lleva esto sin latido se da por
# ausente y sus jobs vivos se cierran. Más que `MINUTOS_SIN_LATIDO` a propósito:
# a mitad de corrida cortar cuesta trabajo hecho, y un reinicio del agente por
# versión nueva tarda un par de minutos. Un agente ocupado no cuenta como
# ausente: el latido corre en paralelo cada 30 s, también durante una tanda.
MINUTOS_AUSENTE = 20

_VIVOS = ["pendiente", "tomado"]


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
    CANCELADA = "cancelada"
    """La canceló una persona desde el panel. Distinta de `frenada`, que es el
    sistema frenándose solo (canario, kill switch)."""


class CorridaEnCurso(Exception):
    """Ya hay una corrida con trabajo pendiente (D59).

    El botón del panel ya no ofrecía disparar en ese caso; con la corrida
    programada y la repesca disparando solas, la guarda tiene que estar acá.
    """


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


def motivo_de_exclusion(vendedor: dict[str, Any], *, ahora: datetime) -> str | None:
    """Por qué esta máquina no entra a una corrida, o `None` si entra.

    `inactiva` no se anota en la corrida (nunca estuvo en juego); el resto sí,
    para que el panel diga quién quedó afuera y por qué.
    """
    if not vendedor.get("activo"):
        return "inactiva"
    if vendedor.get("frenado_por_canario_en") is not None:
        return "frenada"
    if sin_cuota_hasta(vendedor, ahora=ahora) is not None:
        return "sin_cuota"
    if esta_pausada(vendedor, ahora=ahora):
        return "pausada"
    latido = vendedor.get("ultimo_latido")
    if latido is None or _utc(latido) < ahora - timedelta(minutes=MINUTOS_SIN_LATIDO):
        return "sin_latido"
    return None


def _utc(momento: datetime) -> datetime:
    """Mongo devuelve fechas sin zona; todo el sistema las piensa en UTC."""
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


async def clasificar_maquinas(
    base, *, ahora: datetime | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Las máquinas que entran a una corrida, y las que quedan afuera con su motivo.

    Hasta D59 entraban también las que estaban sin conexión ("si la Mac se
    prende más tarde, toma el job"), y una sola PC apagada dejaba la corrida
    abierta para siempre. Ahora entra quien dio señales hace poco.
    """
    momento = ahora or datetime.now(UTC)
    disponibles: list[dict[str, Any]] = []
    excluidas: list[dict[str, str]] = []
    for vendedor in await base["vendedores"].find({}).to_list(None):
        motivo = motivo_de_exclusion(vendedor, ahora=momento)
        if motivo is None:
            disponibles.append(vendedor)
        elif motivo != "inactiva":
            excluidas.append({"maquina": vendedor["maquina"], "motivo": motivo})
    return disponibles, excluidas


async def maquinas_disponibles(base, *, ahora: datetime | None = None) -> list[dict[str, Any]]:
    """Las máquinas a las que tiene sentido darles trabajo (ver `clasificar_maquinas`)."""
    disponibles, _ = await clasificar_maquinas(base, ahora=ahora)
    return disponibles


async def disparar(
    base,
    *,
    quien: str,
    tipo: TipoCorrida = TipoCorrida.DIAGNOSTICO,
    modo: str = "prueba",
    n_chats: int | None = None,
    solo: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    ahora: datetime | None = None,
) -> Disparo:
    """El botón. Crea la corrida y encola un job por máquina.

    Devuelve al instante: encolar es rápido, ejecutar no. El panel muestra el
    progreso preguntando por la corrida, no esperando esta llamada.

    `solo` limita la corrida a esas máquinas (la repesca, D61), con las mismas
    reglas de quién entra. `extra` son campos que se guardan en la corrida.
    """
    if await configuracion.esta_pausado(base):
        raise Pausado("el sistema está pausado: soltá el kill switch primero")
    if await en_curso(base) is not None:
        raise CorridaEnCurso("ya hay una corrida en curso: esperá a que termine o cancelala")

    momento = ahora or datetime.now(UTC)
    disponibles, excluidas = await clasificar_maquinas(base, ahora=momento)
    if solo is not None:
        disponibles = [v for v in disponibles if v["maquina"] in solo]
        excluidas = [e for e in excluidas if e["maquina"] in solo]
    if not disponibles:
        raise NoHayMaquinas("no hay ninguna máquina activa, sin pausar y con señal de vida")

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
            "maquinas_excluidas": excluidas,
            "maquinas_ausentes": [],
            "costo_usd": 0.0,
            "creada_en": momento,
            "terminada_en": None,
            **(extra or {}),
        }
    )
    corrida_id = resultado.inserted_id

    from app.core import pase_unico

    modo_borrador = str(config.get("modo_borrador", "playwright"))

    encolados = 0
    for vendedor in disponibles:
        maquina = vendedor["maquina"]
        if tipo is TipoCorrida.DIAGNOSTICO:
            payload: dict[str, Any] = {}
            job = cola.Tipo.DIAGNOSTICO
        elif tipo is TipoCorrida.GENERACION and modo_borrador in (
            "extension",
            "extension_con_respaldo",
        ):
            # El pase único (01/09): una tanda de BORRADORES por máquina; las
            # siguientes las encadena el backend al procesar cada reporte. Si
            # el payload no se puede armar —destinos vacíos: a nadie (R4)— se
            # cae al circuito de siempre, que tampoco va a escribirle a nadie
            # pero deja la corrida con su recorrido normal y visible.
            payload_pase = await pase_unico.armar_payload(
                base, corrida_id=corrida_id, maquina=maquina, config=config, ahora=momento
            )
            if payload_pase is not None:
                payload = payload_pase
                job = cola.Tipo.BORRADORES
            else:
                payload = _payload_listar(config, vendedor, corrida_id, chats)
                job = cola.Tipo.LISTAR
        else:
            payload = _payload_listar(config, vendedor, corrida_id, chats)
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
        detalle={
            "tipo": str(tipo),
            "modo": modo,
            "maquinas": maquinas,
            "excluidas": excluidas,
        },
        ahora=momento,
    )
    log.info("corrida_disparada", corrida=str(corrida_id), tipo=str(tipo), maquinas=len(maquinas))

    return Disparo(corrida_id=corrida_id, maquinas=maquinas, jobs=encolados)


def _payload_listar(
    config: dict[str, Any], vendedor: dict[str, Any], corrida_id: ObjectId, chats: int
) -> dict[str, Any]:
    """El payload del `LISTAR` con el que arranca el circuito de siempre."""
    estrategia = str(config.get("modo_lectura", "recientes"))
    payload: dict[str, Any] = {
        "n_chats": chats,
        "run_id": str(corrida_id),
        "estrategia": estrategia,
        # La ventana viaja al agente para que el LISTAR busque los
        # chats fríos de verdad, no los N de arriba de la lista.
        "antiguedad_min_dias": config.get("antiguedad_min_dias", 0),
        "antiguedad_max_dias": config.get("antiguedad_max_dias", 3650),
    }
    if estrategia == "barrido":
        # El cursor de ESTA máquina (D27): hasta dónde llegó el barrido
        # la última vez, y los nombres de esa tanda para no repetir en
        # la frontera. Cada Mac avanza a su ritmo.
        barrido = vendedor.get("barrido") or {}
        payload["barrido_hasta_dias"] = int(barrido.get("hasta_dias") or 3650)
        payload["ya_vistos"] = [
            str(n)[:120] for n in (barrido.get("ultima_tanda") or []) if str(n).strip()
        ][:20]
    return payload


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
        # D59: quién quedó afuera al largar, y a quién se le cortó el trabajo
        # por quedarse sin latido a mitad de corrida.
        "maquinas_excluidas": list(corrida.get("maquinas_excluidas") or []),
        "maquinas_ausentes": list(corrida.get("maquinas_ausentes") or []),
        # D61: `repesca` en la corrida que largó la repesca, con lo que revisó.
        "motivo": corrida.get("motivo"),
        "revision_del_dia": corrida.get("revision_del_dia"),
        "creada_en": corrida["creada_en"],
        "jobs": {"total": len(jobs), "pendientes": pendientes, **por_estado},
        "terminada": pendientes == 0 and len(jobs) > 0,
        "costo_usd": corrida.get("costo_usd", 0.0),
        # Las tandas del pase único (D39, D44): cuántos pidió, dejó y salteó
        # cada una, con el desglose de motivos. Es lo que distingue "el prompt
        # se puso estricto" de "el recorrido se rompió". Vacía en el circuito
        # viejo y en los diagnósticos.
        "tandas": [t for t in (corrida.get("tandas") or []) if isinstance(t, dict)],
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


async def recientes(base, *, limite: int = 50) -> list[dict[str, Any]]:
    """Las últimas corridas, de la más nueva a la más vieja.

    Existe porque el panel no tenía forma de contestar "¿qué corridas hubo esta
    semana?". Había `estado` —que trae sólo la última— y el historial de
    auditoría, que es un registro de eventos y sirve para otra cosa: para
    reconstruir qué pasó con **un mensaje**, no para mirar el trabajo de los
    últimos días.

    Trae los jobs de todas de una sola consulta y no una por corrida. Con
    cincuenta corridas, hacerlo adentro del bucle son cincuenta viajes a la base
    para pintar una tabla que alguien mira dos segundos.
    """
    documentos = await base["corridas"].find().sort("creada_en", -1).limit(limite).to_list(None)
    if not documentos:
        return []

    ids = [documento["_id"] for documento in documentos]
    jobs = await base["jobs"].find({"corrida_id": {"$in": ids}}).to_list(None)

    por_corrida: dict[Any, dict[str, int]] = {}
    for job in jobs:
        conteo = por_corrida.setdefault(job["corrida_id"], {})
        conteo[job["estado"]] = conteo.get(job["estado"], 0) + 1

    resumen = []
    for documento in documentos:
        conteo = por_corrida.get(documento["_id"], {})
        total = sum(conteo.values())
        pendientes = conteo.get("pendiente", 0) + conteo.get("tomado", 0)
        resumen.append(
            {
                "id": str(documento["_id"]),
                "tipo": documento["tipo"],
                "modo": documento["modo"],
                "estado": documento["estado"],
                "maquinas": documento["maquinas"],
                "creada_en": documento["creada_en"],
                "jobs": {"total": total, "pendientes": pendientes, **conteo},
                "terminada": pendientes == 0 and total > 0,
                "costo_usd": documento.get("costo_usd", 0.0),
            }
        )
    return resumen


async def cancelar(base, corrida_id: ObjectId, *, quien: str, ahora: datetime | None = None) -> int:
    """Corta una corrida: sus jobs sin hacer se marcan fallidos y se termina.

    Existe porque una corrida sin esto no tiene salida: un `REDACTAR` que
    reintenta tarda minutos por intento, y mientras haya un job pendiente el
    panel muestra "en curso" y no deja disparar otra. Cancelar es una decisión
    de una persona, y queda en la auditoría como tal.

    Lo que ya se hizo, se hizo: no toca los jobs terminados ni borra borradores
    generados — esos se resuelven en la pantalla de revisión. Devuelve cuántos
    jobs cortó.

    Los **mensajes** de los envíos cortados también se resuelven (D31): un
    `ENVIANDO` cuyo job se cortó quedaba en ese estado para siempre, y un
    `EN_ESPERA` con su envío ya encolado esperaba un envío que no iba a llegar.
    Pasan a `DESCARTADO` con motivo `cancelado`. Los `EN_ESPERA` de una corrida
    que todavía no encoló envíos se conservan: son la pantalla de revisión.
    """
    from app.core import mensajes as mensajes_mod
    from app.core.cola import Codigo
    from app.core.estados import Estado, Motivo, TransicionInvalida

    momento = ahora or datetime.now(UTC)

    corrida = await base["corridas"].find_one({"_id": corrida_id})
    if corrida is None:
        raise CorridaDesconocida(corrida_id)

    resultado = await base["jobs"].update_many(
        {"corrida_id": corrida_id, "estado": {"$in": ["pendiente", "tomado"]}},
        {
            "$set": {
                "estado": "fallido",
                "codigo": str(Codigo.CANCELADO),
                "terminado_en": momento,
            }
        },
    )

    a_cortar = {Estado.ENVIANDO}
    if corrida.get("estado") == str(EstadoCorrida.ENVIANDO):
        a_cortar.add(Estado.EN_ESPERA)
    cortados = 0
    for mensaje in await mensajes_mod.de_la_corrida(base, corrida_id):
        if Estado(mensaje["estado"]) not in a_cortar:
            continue
        try:
            await mensajes_mod.mover(
                base,
                mensaje["_id"],
                Estado.DESCARTADO,
                motivo=Motivo.CANCELADO,
                quien=quien,
                ahora=momento,
            )
            cortados += 1
        except (TransicionInvalida, mensajes_mod.CarreraDeEstados):
            # Alguien lo movió en el medio (un agente reportando justo ahora).
            # Su estado nuevo es más verdadero que nuestro corte: se respeta.
            continue

    await base["corridas"].update_one(
        {"_id": corrida_id},
        {"$set": {"estado": str(EstadoCorrida.CANCELADA), "terminada_en": momento}},
    )
    # D35: cancelar también suelta los frenos del canario de esta corrida. Sin
    # esto, una Mac frenada quedaría pausada para siempre después de cancelar —
    # el freno esperaba una decisión, y cancelar ES la decisión.
    from app.core import vendedores

    await vendedores.soltar_freno_de_canario(base, list(corrida.get("maquinas", [])))
    await auditoria.registrar(
        base,
        que=auditoria.Que.CORRIDA_CANCELADA,
        quien=quien,
        corrida_id=corrida_id,
        detalle={"jobs_cortados": resultado.modified_count, "mensajes_cortados": cortados},
        ahora=momento,
    )
    log.info(
        "corrida_cancelada",
        corrida=str(corrida_id),
        jobs=resultado.modified_count,
        mensajes=cortados,
    )
    return resultado.modified_count


async def reanudar(
    base, corrida_id: ObjectId, *, quien: str, ahora: datetime | None = None
) -> None:
    """Suelta una corrida que el canario frenó (D31).

    Es el "ya lo miré, continuar": la corrida vuelve a `enviando` y se suelta
    el kill switch que puso el canario, así los agentes retoman los envíos que
    quedaron encolados. Antes de esto, `frenada` era un estado sin salida — la
    alerta quedaba encendida para siempre y la única forma de apagarla era
    cancelar, perdiendo los envíos pendientes.

    Sólo reanuda corridas en `frenada`: reanudar otra cosa no significa nada, y
    aceptarlo escondería un bug de quien llama.
    """
    momento = ahora or datetime.now(UTC)

    corrida = await base["corridas"].find_one({"_id": corrida_id})
    if corrida is None:
        raise CorridaDesconocida(corrida_id)
    if corrida.get("estado") != str(EstadoCorrida.FRENADA):
        raise NoEstaFrenada(corrida.get("estado", ""))

    await base["corridas"].update_one(
        {"_id": corrida_id},
        {"$set": {"estado": str(EstadoCorrida.ENVIANDO)}},
    )
    await configuracion.pausar(base, pausado=False, quien=quien)
    # D35: el canario frena por máquina. Reanudar es "ya lo miré": las Macs de
    # esta corrida que el canario frenó vuelven a tomar sus envíos pendientes.
    from app.core import vendedores

    await vendedores.soltar_freno_de_canario(base, list(corrida.get("maquinas", [])))
    await auditoria.registrar(
        base,
        que=auditoria.Que.CORRIDA_REANUDADA,
        quien=quien,
        corrida_id=corrida_id,
        ahora=momento,
    )
    log.info("corrida_reanudada", corrida=str(corrida_id), quien=quien)


class NoEstaFrenada(Exception):
    """Se intentó reanudar una corrida que no está frenada."""

    def __init__(self, estado: str) -> None:
        self.estado = estado
        super().__init__(f"la corrida está en {estado!r}, no en frenada")


class CorridaDesconocida(Exception):
    def __init__(self, corrida_id: ObjectId) -> None:
        super().__init__(f"no existe la corrida {corrida_id}")


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
    # la noche está bien, enviar no. Y sólo para el envío REAL (D37): dejar un
    # borrador tampoco es enviar — no le llega nada al cliente hasta que el
    # vendedor lo mande, en su propio horario.
    if modo == "real":
        fuera = guardrails.revisar_ventana(config.get("ventana", {}), ahora=momento)
        if fuera:
            raise FueraDeVentana(fuera.detalle)

    listos = [
        m for m in await mensajes.de_la_corrida(base, corrida_id) if m["estado"] == Estado.EN_ESPERA
    ]

    # Sin doble encolado: un EN_ESPERA cuyo envío ya está en la cola —lo puso
    # el encadenado automático (D36), o un segundo click del botón— no se
    # encola otra vez. Dos jobs para el mismo mensaje serían dos escrituras.
    con_job_vivo = {
        j["payload"].get("mensaje_id")
        for j in await base["jobs"]
        .find(
            {
                "corrida_id": corrida_id,
                "tipo": str(cola.Tipo.ENVIAR),
                "estado": {"$in": [str(cola.EstadoJob.PENDIENTE), str(cola.EstadoJob.TOMADO)]},
            }
        )
        .to_list(None)
    }
    listos = [m for m in listos if str(m["_id"]) not in con_job_vivo]
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


async def encadenar_borrador(
    base, mensaje_id: ObjectId, *, quien: str, ahora: datetime | None = None
) -> ObjectId | None:
    """D36: una redacción limpia se convierte al instante en "dejar borrador".

    Se llama por cada `REDACTAR` que vuelve, sin esperar la tanda ni un botón:
    guardrails sobre ese mensaje → `EN_ESPERA` → un `ENVIAR` en modo `prueba`,
    espaciado detrás de los que su máquina ya tiene. El vendedor entra al día
    siguiente y los borradores están en sus chats.

    Lo que se mantiene y lo que no, decidido con el dueño (28/08):

    - **Los guardrails son código y corren igual** (R3): destino, texto, topes,
      anti-duplicado. Una violación descarta, como en la validación por tanda.
    - **G7 (pausa/consentimiento) no descarta: espera.** El mensaje queda en
      `BORRADOR` — descartarlo tiraría una redacción pagada por un freno que es
      transitorio. El botón "Revisar ahora" del panel lo retoma, o vence (D3).
    - **El triage ya no retiene borradores.** Sus señales se calculan y se
      guardan como información visible en el panel; la revisión humana es el
      vendedor, que ve el borrador antes de mandarlo a mano.

    Devuelve el job encolado, o `None` si este mensaje no siguió. Nunca lanza
    por una carrera: si alguien más movió el mensaje, esa decisión gana.
    """
    from app.core import cola, guardrails, mensajes, triage
    from app.core.estados import Estado, Motivo, TransicionInvalida

    momento = ahora or datetime.now(UTC)

    mensaje = await base["mensajes"].find_one({"_id": mensaje_id})
    if mensaje is None or mensaje["estado"] != str(Estado.BORRADOR):
        # `sin_contexto` ya está en RETENIDO; un duplicado no existe. Nada que hacer.
        return None
    corrida_id = mensaje["corrida_id"]

    config = await configuracion.obtener(base)
    vendedor = await base["vendedores"].find_one({"maquina": mensaje["maquina"]})

    violaciones = await guardrails.revisar(
        base,
        contacto_id=mensaje["contacto_id"],
        texto=mensaje["texto"],
        maquina=mensaje["maquina"],
        config=config,
        vendedor=vendedor,
        verificar_ventana=False,
        ahora=momento,
    )
    frenos = [v for v in violaciones if v.guardrail is guardrails.Guardrail.PAUSA]
    defectos = [v for v in violaciones if v.guardrail is not guardrails.Guardrail.PAUSA]

    # La otra mitad de G4: el tope por corrida, contado sobre lo ya aprobado.
    aprobados = await base["mensajes"].count_documents(
        {
            "corrida_id": corrida_id,
            "estado": {
                "$in": [
                    str(Estado.EN_ESPERA),
                    str(Estado.ENVIANDO),
                    str(Estado.ENVIADO),
                    str(Estado.BORRADOR_DEJADO),
                ]
            },
        }
    )
    if sin_lugar := guardrails.cabe_en_la_corrida(aprobados, config):
        defectos.append(sin_lugar)

    if defectos:
        #  Si alguien más lo movió en el medio, su decisión gana (suppress).
        with contextlib.suppress(TransicionInvalida, mensajes.CarreraDeEstados):
            await mensajes.mover(
                base,
                mensaje_id,
                Estado.DESCARTADO,
                motivo=Motivo.RECHAZADO,
                senales=[str(v.guardrail) for v in defectos],
                quien=quien,
                ahora=momento,
            )
        return None

    if frenos:
        log.info(
            "encadenado_en_espera_de_freno",
            mensaje=str(mensaje_id),
            motivos=[v.detalle for v in frenos],
        )
        return None

    # Señales de triage: información para el panel, no retención (D36). La de
    # nombres repetidos se calcula contra lo que la corrida lleva hasta acá —
    # la tanda completa ya no existe como momento.
    todos = await mensajes.de_la_corrida(base, corrida_id)
    repetidos = triage.nombres_repetidos(todos)
    hallazgos = triage.evaluar(
        texto=mensaje["texto"],
        resumen=mensaje.get("resumen_ultimo", ""),
        contacto_id=mensaje["contacto_id"],
        contacto_nombre=mensaje.get("contacto_nombre", ""),
        quien_hablo_ultimo=mensaje.get("quien_hablo_ultimo", "contacto"),
        config=config,
        ya_le_escribimos=await mensajes.le_escribimos_hace_poco(
            base,
            mensaje["contacto_id"],
            dias=config.get("dias_anti_duplicado", 7),
            ahora=momento,
        ),
        nombre_repetido=_nombre_esta_repetido(mensaje, repetidos),
    )

    try:
        await mensajes.mover(
            base,
            mensaje_id,
            Estado.EN_ESPERA,
            senales=[str(h.senal) for h in hallazgos],
            ahora=momento,
        )
    except (TransicionInvalida, mensajes.CarreraDeEstados):
        return None

    job = await cola.encolar_envio_escalonado(
        base,
        maquina=mensaje["maquina"],
        corrida_id=corrida_id,
        payload={
            "mensaje_id": str(mensaje_id),
            "contacto_id": mensaje["contacto_id"],
            "contacto_nombre": mensaje.get("contacto_nombre", ""),
            "texto": mensaje["texto"],
            "modo": "prueba",
        },
        pausa=tuple(config.get("pausa_entre_envios_s", [45, 180])),
        ahora=momento,
    )

    # La corrida pasa a `enviando` con el primer borrador encolado. La escritura
    # condicional hace que sólo el primero gane la carrera y audite una vez.
    arranque = await base["corridas"].update_one(
        {
            "_id": corrida_id,
            "estado": {"$in": [str(EstadoCorrida.GENERANDO), str(EstadoCorrida.REVISION)]},
        },
        {"$set": {"estado": str(EstadoCorrida.ENVIANDO)}},
    )
    if arranque.modified_count:
        await auditoria.registrar(
            base,
            que=auditoria.Que.CORRIDA_DISPARADA,
            quien=quien,
            corrida_id=corrida_id,
            detalle={"accion": "borradores_automaticos", "modo": "prueba"},
            ahora=momento,
        )
        log.info("borradores_automaticos", corrida=str(corrida_id))

    return job


def _nombre_esta_repetido(mensaje: dict[str, Any], repetidos: set[str]) -> bool:
    from app.core.triage import _sin_acentos

    return _sin_acentos((mensaje.get("contacto_nombre") or "").strip()) in repetidos


async def revisar_canario(
    base, corrida_id: ObjectId, *, maquina: str, quien: str = "sistema"
) -> bool:
    """¿Fallaron los primeros envíos **de esta máquina**? Si sí, la frena (D35).

    Se llama después de cada `ENVIAR` que termina. Mientras los primeros
    `CANARIO` jobs de la máquina no hayan terminado todos, no decide nada: con
    uno solo reportado no se puede distinguir mala suerte de sistema roto.

    Frena la Mac, no el sistema: el 27/08 el canario global pausó todo por los
    fallos de una sola máquina, con las demás enviando bien. La corrida pasa a
    `frenada` recién cuando ya no queda ninguna máquina avanzando.

    Devuelve `True` si frenó la máquina.
    """
    from app.core import cola, vendedores

    jobs = (
        await base["jobs"]
        .find({"corrida_id": corrida_id, "tipo": str(cola.Tipo.ENVIAR), "maquina": maquina})
        .sort("disponible_desde", 1)
        .to_list(None)
    )
    # Un job CANCELADO no dice nada del sistema: es una persona vetando un
    # mensaje, o un mensaje que venció antes de entregarse (G3). Contarlo como
    # fallo frenaría una máquina sana por una decisión del panel.
    evaluables = [j for j in jobs if j.get("codigo") != str(cola.Codigo.CANCELADO)]
    primeros = evaluables[: cola.CANARIO]

    if len(primeros) < cola.CANARIO:
        return False
    if any(j["estado"] not in (cola.EstadoJob.LISTO, cola.EstadoJob.FALLIDO) for j in primeros):
        return False
    if any(j["estado"] == cola.EstadoJob.LISTO for j in primeros):
        return False

    # G1 — el piso de reanudación. Si los tres evaluados terminaron ANTES del
    # último `soltar_freno` de esta máquina, ya se miraron: son exactamente los
    # fallos por los que alguien apretó reanudar. Volver a frenar por ellos es
    # el loop freno→soltar→freno para siempre — ocurre incluso con los
    # selectores arreglados, porque los jobs viejos no cambian.
    vendedor = await base["vendedores"].find_one({"maquina": maquina})
    piso = (vendedor or {}).get("freno_soltado_en")
    if piso is not None and all(
        j.get("terminado_en") is not None and j["terminado_en"] < piso for j in primeros
    ):
        return False

    # Los tres de esta máquina terminaron y ninguno salió bien.
    await vendedores.frenar_por_canario(base, maquina)
    await auditoria.registrar(
        base,
        que=auditoria.Que.KILL_SWITCH,
        quien=quien,
        corrida_id=corrida_id,
        detalle={
            "motivo": "canario_fallido",
            "revisados": cola.CANARIO,
            "alcance": "maquina",
            "maquina": maquina,
        },
    )
    log.error("canario_fallido", corrida=str(corrida_id), maquina=maquina, revisados=cola.CANARIO)

    await _frenar_corrida_si_nadie_avanza(base, corrida_id)
    return True


async def _frenar_corrida_si_nadie_avanza(base, corrida_id: ObjectId) -> None:
    """La corrida pasa a `frenada` cuando ninguna máquina puede seguir.

    "Avanzando" = tiene envíos vivos (pendientes o tomados) y no está frenada
    por su canario. Con una Mac frenada y otra terminando bien, la corrida
    sigue `enviando`; cuando la última sana termina, queda `frenada` — con el
    botón reanudar como salida (D31), que suelta los frenos.
    """
    from app.core import cola

    corrida = await base["corridas"].find_one({"_id": corrida_id})
    if corrida is None or corrida.get("estado") != str(EstadoCorrida.ENVIANDO):
        return

    for nombre in corrida.get("maquinas", []):
        vendedor = await base["vendedores"].find_one({"maquina": nombre})
        if vendedor is None or vendedor.get("frenado_por_canario_en") is not None:
            continue
        vivos = await base["jobs"].count_documents(
            {
                "corrida_id": corrida_id,
                "tipo": str(cola.Tipo.ENVIAR),
                "maquina": nombre,
                "estado": {"$in": [str(cola.EstadoJob.PENDIENTE), str(cola.EstadoJob.TOMADO)]},
            },
            limit=1,
        )
        if vivos:
            return

    await base["corridas"].update_one(
        {"_id": corrida_id}, {"$set": {"estado": str(EstadoCorrida.FRENADA)}}
    )
    log.warning("corrida_frenada_por_canario", corrida=str(corrida_id))


# ---------------------------------------------------------------------------
# Que una corrida termine siempre (D59)
# ---------------------------------------------------------------------------


async def cerrar_ausentes(base, *, ahora: datetime | None = None) -> int:
    """Cierra los jobs vivos de las máquinas que se quedaron sin latido.

    Corre en cada vuelta del mantenimiento. Mira sólo corridas con trabajo
    vivo, y dentro de ellas sólo las máquinas que tienen jobs vivos: una PC
    apagada que ya terminó lo suyo no molesta a nadie. Devuelve cuántos jobs
    cerró.
    """
    from app.core.cola import Codigo

    momento = ahora or datetime.now(UTC)
    corte = momento - timedelta(minutes=MINUTOS_AUSENTE)

    vivos = (
        await base["jobs"]
        .find({"estado": {"$in": _VIVOS}}, {"corrida_id": 1, "maquina": 1})
        .to_list(None)
    )
    por_corrida: dict[Any, set[str]] = {}
    for job in vivos:
        if job.get("corrida_id") is not None:
            por_corrida.setdefault(job["corrida_id"], set()).add(job["maquina"])
    if not por_corrida:
        return 0

    nombres = {m for maquinas in por_corrida.values() for m in maquinas}
    latidos = {
        v["maquina"]: v.get("ultimo_latido")
        for v in await base["vendedores"].find({"maquina": {"$in": sorted(nombres)}}).to_list(None)
    }
    #  Una máquina dada de baja a mitad de corrida no tiene documento: tampoco
    #  va a volver a dar señales, y cuenta como callada.
    callados = {m for m in nombres if latidos.get(m) is None or _utc(latidos[m]) < corte}

    cerrados = 0
    for corrida_id, maquinas in por_corrida.items():
        ausentes = sorted(maquinas & callados)
        if not ausentes:
            continue
        corrida = await base["corridas"].find_one({"_id": corrida_id})
        if corrida is None:
            continue
        cortados = await _cortar(
            base,
            corrida,
            maquinas=ausentes,
            codigo=Codigo.MAQUINA_AUSENTE,
            motivo="la máquina dejó de dar señales a mitad de corrida",
            ahora=momento,
        )
        await base["corridas"].update_one(
            {"_id": corrida_id},
            {
                "$push": {
                    "maquinas_ausentes": {
                        "$each": [{"maquina": m, "en": momento} for m in ausentes]
                    }
                }
            },
        )
        for maquina in ausentes:
            await auditoria.registrar(
                base,
                que=auditoria.Que.MAQUINA_AUSENTE,
                quien=auditoria.SISTEMA,
                corrida_id=corrida_id,
                detalle={"maquina": maquina, "minutos_sin_latido": MINUTOS_AUSENTE},
                ahora=momento,
            )
        await _terminar_si_quedo_vacia(base, corrida, momento)
        log.warning("maquinas_ausentes", corrida=str(corrida_id), maquinas=ausentes, jobs=cortados)
        cerrados += cortados
    return cerrados


async def vencer_largas(base, *, ahora: datetime | None = None) -> int:
    """El techo: una corrida con trabajo vivo a las `horas_max_corrida` se cierra.

    Cubre lo que `cerrar_ausentes` no ve: un agente vivo con un job trabado, o
    una corrida frenada que nadie decidió. Devuelve cuántas corridas cerró.
    """
    from app.core.cola import Codigo

    momento = ahora or datetime.now(UTC)
    config = await configuracion.obtener(base)
    horas = int(config.get("horas_max_corrida") or 5)
    corte = momento - timedelta(hours=horas)

    vencidas = 0
    for corrida in await base["corridas"].find({"creada_en": {"$lt": corte}}).to_list(None):
        if not await base["jobs"].count_documents(
            {"corrida_id": corrida["_id"], "estado": {"$in": _VIVOS}}, limit=1
        ):
            continue
        cortados = await _cortar(
            base,
            corrida,
            maquinas=None,
            codigo=Codigo.VENCIDO,
            motivo=f"la corrida pasó su techo de {horas} horas",
            ahora=momento,
        )
        if corrida.get("estado") == str(EstadoCorrida.FRENADA):
            #  Como al cancelar: el freno esperaba una decisión, y el techo la
            #  tomó. Sin esto la máquina quedaría frenada para siempre.
            from app.core import vendedores

            await vendedores.soltar_freno_de_canario(base, list(corrida.get("maquinas", [])))
        await _terminar_si_quedo_vacia(base, corrida, momento, tambien_frenada=True)
        await auditoria.registrar(
            base,
            que=auditoria.Que.CORRIDA_VENCIDA,
            quien=auditoria.SISTEMA,
            corrida_id=corrida["_id"],
            detalle={"horas": horas, "jobs_cortados": cortados},
            ahora=momento,
        )
        log.warning("corrida_vencida", corrida=str(corrida["_id"]), horas=horas, jobs=cortados)
        vencidas += 1
    return vencidas


async def cortar_maquinas(
    base,
    corrida: dict[str, Any],
    *,
    maquinas: list[str],
    codigo,
    motivo: str,
    ahora: datetime,
) -> int:
    """Cierra los jobs vivos de esas máquinas en una corrida, y la termina si quedó vacía.

    Para quien corta por su cuenta y no por el reloj: la cuota agotada (D60,
    D65), que desde que la cuenta es una corta a todas juntas.
    """
    cortados = await _cortar(
        base, corrida, maquinas=maquinas, codigo=codigo, motivo=motivo, ahora=ahora
    )
    await _terminar_si_quedo_vacia(base, corrida, ahora)
    return cortados


async def _cortar(
    base,
    corrida: dict[str, Any],
    *,
    maquinas: list[str] | None,
    codigo,
    motivo: str,
    ahora: datetime,
) -> int:
    """Cierra los jobs vivos de una corrida —de todas sus máquinas o de algunas—
    y resuelve los mensajes de los envíos que quedaron colgando.

    Con los mensajes hace lo mismo que `cancelar` (D31): un `ENVIANDO` cuyo job
    se cortó quedaría así para siempre, y un `EN_ESPERA` de una corrida que ya
    estaba enviando esperaría un envío que no va a llegar.
    """
    from app.core import mensajes as mensajes_mod
    from app.core.estados import Estado, Motivo, TransicionInvalida

    filtro: dict[str, Any] = {"corrida_id": corrida["_id"], "estado": {"$in": _VIVOS}}
    if maquinas is not None:
        filtro["maquina"] = {"$in": maquinas}
    resultado = await base["jobs"].update_many(
        filtro,
        {
            "$set": {
                "estado": "fallido",
                "codigo": str(codigo),
                "detalle": {"motivo": motivo},
                "terminado_en": ahora,
            }
        },
    )

    a_cortar = {Estado.ENVIANDO}
    if corrida.get("estado") == str(EstadoCorrida.ENVIANDO):
        a_cortar.add(Estado.EN_ESPERA)
    motivo_mensaje = Motivo.VENCIDO if maquinas is None else Motivo.FALLIDO
    for mensaje in await mensajes_mod.de_la_corrida(base, corrida["_id"]):
        if Estado(mensaje["estado"]) not in a_cortar:
            continue
        if maquinas is not None and mensaje.get("maquina") not in maquinas:
            continue
        try:
            await mensajes_mod.mover(
                base,
                mensaje["_id"],
                Estado.DESCARTADO,
                motivo=motivo_mensaje,
                quien=auditoria.SISTEMA,
                ahora=ahora,
            )
        except (TransicionInvalida, mensajes_mod.CarreraDeEstados):
            continue
    return resultado.modified_count


async def _terminar_si_quedo_vacia(
    base, corrida: dict[str, Any], momento: datetime, *, tambien_frenada: bool = False
) -> None:
    """Si a la corrida no le queda trabajo vivo, se da por terminada.

    Una `frenada` sólo la cierra el techo: mientras tanto espera que una
    persona decida (D31), y cerrarla por una máquina ausente se lo saltearía.
    """
    estados = [str(EstadoCorrida.GENERANDO), str(EstadoCorrida.ENVIANDO)]
    if tambien_frenada:
        estados.append(str(EstadoCorrida.FRENADA))
    if await base["jobs"].count_documents(
        {"corrida_id": corrida["_id"], "estado": {"$in": _VIVOS}}, limit=1
    ):
        return
    await base["corridas"].update_one(
        {"_id": corrida["_id"], "estado": {"$in": estados}},
        {"$set": {"estado": str(EstadoCorrida.TERMINADA), "terminada_en": momento}},
    )
