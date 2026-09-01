"""El pase único (01/09): la extensión lee el chat y deja el borrador ahí mismo.

Este módulo es el lado backend de esa ruta: arma cada tanda con las listas ya
calculadas (R3 — el modelo obedece datos, no calcula límites), procesa el
reporte cuando vuelve, y encadena la tanda siguiente hasta agotar la ventana o
el tope.

Tres decisiones de diseño que conviene tener presentes:

- **El reporte describe hechos consumados.** Cuando llega, los borradores YA
  están escritos en los chats del vendedor. Por eso los mensajes se crean y
  pasan directo a `BORRADOR_DEJADO`, y los guardrails corren *después*, como
  señales informativas para el panel (R5) — no hay nada que bloquear, porque
  bloquear el registro no des-escribe el borrador.
- **Nada de este módulo puede romper el trabajo hecho.** Si el procesado
  falla a mitad de camino, lo perdido es una fila del panel o una tanda
  siguiente — nunca un borrador, que vive en WhatsApp. Y un reporte procesado
  dos veces no duplica nada: la clave de idempotencia de `mensajes` lo frena.
- **La cascada es B1 → B2 → B3.** B1 es la tanda; B2 son los reintentos del
  mismo job (el campo-no-vacío hace que salteen solos lo ya dejado); B3 es el
  circuito de siempre —LISTAR → RESOLVER → REDACTAR → ENVIAR en modo prueba—
  que se activa por máquina cuando el job agota sus intentos, sólo con
  `modo_borrador = "extension_con_respaldo"`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId

from app.core import auditoria, cola, configuracion, guardrails, mensajes
from app.core.contactos import NumeroInvalido, normalizar
from app.core.estados import Estado
from app.logging import obtener_logger

log = obtener_logger(__name__)

# Cuántos nombres viajan en cada lista del payload. La cota del esquema
# (`PayloadBorradores`) es la dura; ésta es la de armado.
MAX_NOMBRES = 60


@dataclass
class Procesado:
    """Qué pasó con el reporte de una tanda."""

    registrados: list[ObjectId] = field(default_factory=list)
    #  Visitados que quedaron sin borrador, con su motivo, para el panel.
    salteados: int = 0
    #  El reporte ya se había procesado (idempotencia): no se registró de nuevo.
    repetidos: int = 0
    #  La tanda siguiente, si se encoló.
    tanda_siguiente: ObjectId | None = None
    #  Por qué no hay tanda siguiente, cuando no la hay.
    fin: str | None = None


async def armar_payload(
    base,
    *,
    corrida_id: ObjectId,
    maquina: str,
    config: dict[str, Any] | None = None,
    ya_vistos: list[str] | None = None,
    ahora: datetime | None = None,
) -> dict[str, Any] | None:
    """El payload de una tanda, con las listas ya calculadas.

    Devuelve `None` cuando no tiene sentido encolar nada: la lista de destinos
    vacía significa **a nadie** (R4), y un pase que no puede dejar ningún
    borrador no se paga.
    """
    momento = ahora or datetime.now(UTC)
    config = config if config is not None else await configuracion.obtener(base)

    destinos = [str(d) for d in (config.get("destinos_permitidos") or [])]
    if not destinos:
        log.warning("pase_unico_sin_destinos", corrida=str(corrida_id), maquina=maquina)
        return None
    #  Con "*" no hay restricción y la lista viaja vacía; con números
    #  concretos, sólo esos chats pueden recibir borrador.
    solo_numeros = [] if "*" in destinos else destinos[:MAX_NOMBRES]

    # El pase único respeta `modo_lectura` igual que el circuito viejo (D27):
    # la perilla del panel es una sola y significa lo mismo en las dos rutas.
    estrategia = str(config.get("modo_lectura", "recientes"))
    vistos = [str(n)[:120] for n in (ya_vistos or [])]

    payload = {
        "n_chats": int(config.get("chats_por_tanda", 6)),
        "run_id": str(corrida_id),
        "antiguedad_min_dias": int(config.get("antiguedad_min_dias", 0)),
        "antiguedad_max_dias": int(config.get("antiguedad_max_dias", 3650)),
        "estrategia": estrategia,
        "no_escribir": await _no_escribir(base, maquina, config=config, ahora=momento),
        "solo_numeros": solo_numeros,
        "largo_maximo": int(config.get("largo_maximo", 600)),
        "contexto_empresa": str(config.get("contexto_empresa", ""))[
            : configuracion.LARGO_CONTEXTO_EMPRESA
        ],
    }

    if estrategia == "barrido":
        # El cursor de ESTA máquina: hasta dónde llegó el barrido, y los
        # nombres de la última tanda para desempatar en la frontera cuando
        # varios chats comparten antigüedad. Es el mismo cursor que usa el
        # circuito viejo — las dos rutas avanzan sobre el mismo recorrido, así
        # que cambiar de perilla a mitad del historial no lo hace empezar de
        # nuevo ni saltearse un tramo.
        cursor = (await base["vendedores"].find_one({"maquina": maquina}) or {}).get(
            "barrido"
        ) or {}
        payload["barrido_hasta_dias"] = int(cursor.get("hasta_dias") or 3650)
        frontera = [str(n)[:120] for n in (cursor.get("ultima_tanda") or []) if str(n).strip()]
        #  Los de la corrida anterior primero: si hay que recortar, se pierden
        #  los más viejos, que ya quedaron detrás del cursor igual.
        vistos = frontera + vistos

    payload["ya_vistos"] = _sin_repetidos(vistos)[-MAX_NOMBRES:]
    return payload


def _sin_repetidos(nombres: list[str]) -> list[str]:
    """Los mismos nombres, sin duplicados, en el orden en que aparecieron.

    En barrido, la última tanda entra dos veces —por el cursor y por lo
    acumulado en la corrida— y cada repetido gasta un lugar del tope de 60 que
    le corresponde a un chat que sí hay que saltear.
    """
    return list(dict.fromkeys(nombres))


async def _no_escribir(base, maquina: str, *, config: dict[str, Any], ahora: datetime) -> list[str]:
    """Los nombres que el pase tiene que saltear sin abrir (anti-duplicado).

    El mismo criterio que `generacion._ya_contactado`: cualquier mensaje vivo o
    salido de los últimos días veta al contacto — un DESCARTADO no, porque una
    decisión de no mandar *ese* texto no veta a la persona. Se calcula por
    nombre porque es lo único que el pase ve en la lista de chats.
    """
    corte = ahora - timedelta(days=max(1, int(config.get("dias_anti_duplicado", 7))))
    nombres = await base["mensajes"].distinct(
        "contacto_nombre",
        {
            "maquina": maquina,
            "creado_en": {"$gte": corte},
            "estado": {"$ne": str(Estado.DESCARTADO)},
        },
    )
    return sorted(str(n)[:120] for n in nombres if str(n).strip())[:MAX_NOMBRES]


async def encolar_tanda(
    base,
    *,
    corrida_id: ObjectId,
    maquina: str,
    ya_vistos: list[str] | None = None,
    ahora: datetime | None = None,
) -> ObjectId | None:
    """Una tanda del pase único, si corresponde. `None` con el porqué logueado.

    Dos guardas antes de encolar: que no haya ya una tanda viva de esta máquina
    en esta corrida (un reporte procesado dos veces encolaría dos), y que el
    tope por corrida no esté alcanzado — contado sobre lo ya dejado, porque en
    esta ruta dejar ES el acto que el tope limita.
    """
    momento = ahora or datetime.now(UTC)

    viva = await base["jobs"].find_one(
        {
            "corrida_id": corrida_id,
            "maquina": maquina,
            "tipo": str(cola.Tipo.BORRADORES),
            "estado": {"$in": [str(cola.EstadoJob.PENDIENTE), str(cola.EstadoJob.TOMADO)]},
        }
    )
    if viva is not None:
        log.warning("tanda_ya_viva", corrida=str(corrida_id), maquina=maquina)
        return None

    config = await configuracion.obtener(base)
    dejados = await base["mensajes"].count_documents(
        {"corrida_id": corrida_id, "estado": str(Estado.BORRADOR_DEJADO)}
    )
    tope = int(config.get("tope_por_corrida", 25))
    if dejados >= tope:
        log.info("tope_por_corrida_alcanzado", corrida=str(corrida_id), dejados=dejados, tope=tope)
        return None

    payload = await armar_payload(
        base,
        corrida_id=corrida_id,
        maquina=maquina,
        config=config,
        ya_vistos=ya_vistos,
        ahora=momento,
    )
    if payload is None:
        return None
    #  La última tanda antes del tope se achica para no pasarlo: el modelo
    #  frena al llegar a `n_chats`, así que `n_chats` ES el tope de la tanda.
    payload["n_chats"] = max(1, min(payload["n_chats"], tope - dejados))

    return await cola.encolar(
        base,
        tipo=cola.Tipo.BORRADORES,
        maquina=maquina,
        corrida_id=corrida_id,
        payload=payload,
        ahora=momento,
    )


async def procesar_reporte(
    base,
    *,
    job: dict[str, Any],
    detalle: dict[str, Any],
    ahora: datetime | None = None,
) -> Procesado:
    """Registra lo que la tanda dejó y encadena la siguiente.

    Se llama también cuando la tanda FALLÓ, si su detalle trae chats: los
    borradores que se alcanzaron a dejar antes del error ya están en WhatsApp,
    y no registrarlos sería tener borradores que el panel no conoce.
    """
    momento = ahora or datetime.now(UTC)
    resultado = Procesado()
    corrida_id = job["corrida_id"]
    maquina = job["maquina"]

    chats = [c for c in (detalle.get("chats") or []) if isinstance(c, dict)]
    config = await configuracion.obtener(base)
    vendedor = await base["vendedores"].find_one({"maquina": maquina})

    for chat in chats:
        if chat.get("borrador_dejado") and str(chat.get("texto_borrador") or "").strip():
            try:
                await _registrar_dejado(
                    base,
                    corrida_id=corrida_id,
                    maquina=maquina,
                    chat=chat,
                    config=config,
                    vendedor=vendedor,
                    momento=momento,
                    resultado=resultado,
                )
            except Exception as error:
                # Un tropiezo con UN chat no puede perder el registro de los
                # demás ni la tanda siguiente: el borrador de este quedó en
                # WhatsApp igual, y el error queda nombrado para ir a buscarlo.
                log.error(
                    "registro_de_borrador_fallo",
                    contacto=str(chat.get("contacto_nombre"))[:60],
                    error=str(error)[:200],
                )
        else:
            resultado.salteados += 1

    log.info(
        "pase_unico_procesado",
        corrida=str(corrida_id),
        maquina=maquina,
        registrados=len(resultado.registrados),
        salteados=resultado.salteados,
        repetidos=resultado.repetidos,
    )

    # ---- El cursor del barrido ---------------------------------------------
    #
    # Se avanza SIEMPRE que la tanda haya visitado algo, incluso si falló a la
    # mitad: esos chats ya se recorrieron —y varios quedaron con borrador— así
    # que volver a pasarlos sería releerlos para saltearlos por campo ocupado.
    if str((job.get("payload") or {}).get("estrategia")) == "barrido" and chats:
        await _avanzar_cursor(base, maquina, chats=chats, detalle=detalle, momento=momento)

    # ---- La tanda siguiente ------------------------------------------------
    #
    # Sólo si la tanda vino de un job exitoso: una fallida sigue por los
    # reintentos del MISMO job (B2), no por una tanda nueva.
    if job.get("estado") == str(cola.EstadoJob.LISTO):
        if bool(detalle.get("fin_de_ventana")):
            resultado.fin = "fin_de_ventana"
        elif not chats:
            #  Visitó cero chats sin declarar fin: no hay con qué avanzar
            #  `ya_vistos`, y encolar otra tanda igual sería un bucle.
            resultado.fin = "tanda_vacia"
        else:
            vistos_antes = [str(n) for n in (job.get("payload") or {}).get("ya_vistos") or []]
            vistos = vistos_antes + [c["contacto_nombre"] for c in chats]
            resultado.tanda_siguiente = await encolar_tanda(
                base,
                corrida_id=corrida_id,
                maquina=maquina,
                ya_vistos=vistos,
                ahora=momento,
            )
            if resultado.tanda_siguiente is None:
                resultado.fin = "tope_o_tanda_viva"

    if resultado.tanda_siguiente is None:
        await _terminar_si_no_queda_nada(base, corrida_id, momento)
    return resultado


async def _avanzar_cursor(
    base,
    maquina: str,
    *,
    chats: list[dict[str, Any]],
    detalle: dict[str, Any],
    momento: datetime,
) -> None:
    """Mueve el cursor del barrido de esta máquina, del fondo hacia hoy (D27).

    `hasta_dias` pasa a ser la antigüedad del chat **más nuevo** de la tanda:
    la próxima pide "los más viejos con hasta esos días" y así avanza sin
    volver a empezar. Es el mismo cursor y la misma función que usa el circuito
    viejo, a propósito — cambiar de perilla a mitad del historial no tiene que
    hacer que el barrido reempiece ni que se saltee un tramo.

    ⚠️ `completado` lo dice el agente en `fin_de_ventana`, no se deduce contando:
    una tanda corta por tiempo y una por historial agotado se ven iguales desde
    acá, y confundirlas daría el barrido por terminado a mitad de camino.
    """
    from app.core import vendedores

    antiguedades = [
        int(c["antiguedad_dias"]) for c in chats if isinstance(c.get("antiguedad_dias"), int)
    ]
    await vendedores.registrar_barrido(
        base,
        maquina,
        hasta_dias=min(antiguedades) if antiguedades else None,
        tanda=[str(c.get("contacto_nombre", ""))[:120] for c in chats],
        completado=bool(detalle.get("fin_de_ventana")),
        ahora=momento,
    )


async def _registrar_dejado(
    base,
    *,
    corrida_id: ObjectId,
    maquina: str,
    chat: dict[str, Any],
    config: dict[str, Any],
    vendedor: dict[str, Any] | None,
    momento: datetime,
    resultado: Procesado,
) -> None:
    """Un borrador que quedó en un chat pasa a existir para el sistema.

    Nace en `BORRADOR` y pasa directo a `BORRADOR_DEJADO` — el estado se pone
    al día con la realidad, no al revés. Los guardrails corren antes, como
    señales: una violación acá no bloquea nada (el borrador ya está escrito),
    pero queda en el mensaje y el panel la muestra para que alguien decida si
    va a borrarlo a mano.
    """
    nombre = chat["contacto_nombre"]
    texto = str(chat["texto_borrador"])
    contacto_id = await _identificar(base, maquina, nombre, chat.get("contacto_telefono"), momento)

    senales = [
        str(v.guardrail)
        for v in await guardrails.revisar(
            base,
            contacto_id=contacto_id,
            texto=texto,
            maquina=maquina,
            config=config,
            vendedor=vendedor,
            #  La ventana horaria rige envíos; dejar un borrador no le llega a
            #  nadie hasta que el vendedor lo mande, en su propio horario.
            verificar_ventana=False,
            ahora=momento,
        )
    ]

    try:
        mensaje_id = await mensajes.crear_borrador(
            base,
            corrida_id=corrida_id,
            maquina=maquina,
            contacto_id=contacto_id,
            contacto_nombre=nombre,
            texto=texto,
            resumen_ultimo=chat.get("ultimo_mensaje_resumen", ""),
            quien_hablo_ultimo=chat.get("quien_hablo_ultimo", "contacto"),
            antiguedad_dias=chat.get("antiguedad_dias", 0),
            ahora=momento,
        )
    except mensajes.MensajeDuplicado:
        #  El reporte llegó dos veces: el borrador ya está registrado.
        resultado.repetidos += 1
        return

    await mensajes.mover(
        base,
        mensaje_id,
        Estado.BORRADOR_DEJADO,
        senales=senales,
        quien=maquina,
        ahora=momento,
    )
    if senales:
        log.warning("borrador_dejado_con_senales", contacto=nombre[:60], senales=senales)
    resultado.registrados.append(mensaje_id)


async def _identificar(base, maquina: str, nombre: str, telefono: Any, momento: datetime) -> str:
    """El `contacto_id` del mensaje: el número si se puede, el nombre si no.

    Tres fuentes, en orden: el número visible que reportó el pase (y de paso
    alimenta la memoria de `telefonos`), la memoria de resoluciones anteriores,
    y —último recurso— `nombre:<...>`, explícito y grepeable. Nunca se deduce
    un número: un identificador inventado envenenaría el anti-duplicado.
    """
    if telefono:
        try:
            numero = normalizar(str(telefono))
        except NumeroInvalido:
            numero = None
        if numero:
            await base["telefonos"].update_one(
                {"maquina": maquina, "nombre": nombre},
                {"$set": {"contacto_id": numero, "actualizado_en": momento}},
                upsert=True,
            )
            return numero

    conocido = await base["telefonos"].find_one({"maquina": maquina, "nombre": nombre})
    if conocido and conocido.get("contacto_id"):
        return str(conocido["contacto_id"])

    return f"nombre:{nombre[:100]}"


async def _terminar_si_no_queda_nada(base, corrida_id: ObjectId, momento: datetime) -> None:
    """La corrida del pase único termina cuando ya no hay jobs vivos.

    Sólo desde `generando`: una corrida que además tiene envíos (el respaldo
    B3 los crea) sigue su ciclo de siempre y la termina ese circuito.
    """
    from app.core.corridas import EstadoCorrida

    vivos = await base["jobs"].count_documents(
        {
            "corrida_id": corrida_id,
            "estado": {"$in": [str(cola.EstadoJob.PENDIENTE), str(cola.EstadoJob.TOMADO)]},
        },
        limit=1,
    )
    if vivos:
        return
    cambiada = await base["corridas"].update_one(
        {"_id": corrida_id, "estado": str(EstadoCorrida.GENERANDO)},
        {"$set": {"estado": str(EstadoCorrida.TERMINADA), "terminada_en": momento}},
    )
    if cambiada.modified_count:
        log.info("corrida_terminada", corrida=str(corrida_id))


async def activar_respaldo(
    base, *, job: dict[str, Any], ahora: datetime | None = None
) -> ObjectId | None:
    """B3: la tanda agotó sus intentos y esta máquina cae al circuito de siempre.

    Sólo con `modo_borrador = "extension_con_respaldo"`, y una sola vez por
    máquina y corrida. Encola el `LISTAR` con el que arranca el circuito viejo;
    de ahí en adelante todo es el sistema ya probado — incluida la comparación
    de identidad (R1), que en esa ruta rige entera. Lo ya dejado por las tandas
    no se duplica: el anti-duplicado y el campo-no-vacío lo cubren.
    """
    momento = ahora or datetime.now(UTC)
    corrida_id = job["corrida_id"]
    maquina = job["maquina"]

    # ⚠️ Tras un TEXTO_ENVIADO no hay respaldo automático: un texto salió
    # enviado en vez de quedar escrito, y lo que corresponde es que una persona
    # mire ese chat antes de que el sistema siga solo por ningún camino. La
    # corrida de esa máquina queda ahí, con el código a la vista en el panel.
    if job.get("codigo") == str(cola.Codigo.TEXTO_ENVIADO):
        log.warning("respaldo_frenado_por_texto_enviado", corrida=str(corrida_id), maquina=maquina)
        return None

    config = await configuracion.obtener(base)
    if str(config.get("modo_borrador", "playwright")) != "extension_con_respaldo":
        return None

    ya = await base["jobs"].find_one(
        {"corrida_id": corrida_id, "maquina": maquina, "tipo": str(cola.Tipo.LISTAR)}
    )
    if ya is not None:
        return None

    payload: dict[str, Any] = {
        "n_chats": int(config.get("n_chats_por_defecto", 20)),
        "run_id": str(corrida_id),
        "estrategia": "recientes",
        "antiguedad_min_dias": int(config.get("antiguedad_min_dias", 0)),
        "antiguedad_max_dias": int(config.get("antiguedad_max_dias", 3650)),
    }
    encolado = await cola.encolar(
        base,
        tipo=cola.Tipo.LISTAR,
        maquina=maquina,
        corrida_id=corrida_id,
        payload=payload,
        ahora=momento,
    )
    await auditoria.registrar(
        base,
        que=auditoria.Que.CORRIDA_DISPARADA,
        quien="sistema",
        corrida_id=corrida_id,
        detalle={
            "accion": "respaldo_del_pase_unico",
            "maquina": maquina,
            "cascada": {
                "gano": "B3_circuito_completo",
                "intentadas": ["B1_tanda", "B2_reintentos"],
            },
        },
        ahora=momento,
    )
    log.warning("pase_unico_respaldo_activado", corrida=str(corrida_id), maquina=maquina)
    return encolado
