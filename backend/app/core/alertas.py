"""Las alertas: lo que el panel tiene que gritar.

**No se guardan.** Se calculan del estado actual cada vez que alguien pregunta.
Una alerta guardada hay que acordarse de borrarla cuando el problema se
resuelve, y la que nadie borró es la que enseña a ignorarlas todas.

Dos niveles, y la diferencia es qué se espera de quien las lee:

    URGENTE   algo está mal AHORA y alguien tiene que hacer algo
    AVISO     conviene mirarlo, pero el sistema sigue funcionando

Nada de "informativo". Una alerta que no pide nada no es una alerta: es un
número, y los números van en las métricas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from app.core import cola, vendedores
from app.core.estados import Estado, Motivo
from app.logging import obtener_logger

log = obtener_logger(__name__)

# Cuánto tiene que llevar caída una máquina para que valga la pena avisar.
# Más largo que el corte del panel (90 s): que una Mac parpadee no es noticia,
# que lleve diez minutos caída con trabajo encolado sí.
MINUTOS_CAIDA = 10


class Nivel(StrEnum):
    URGENTE = "urgente"
    AVISO = "aviso"


@dataclass(frozen=True)
class Alerta:
    nivel: Nivel
    codigo: str
    titulo: str
    detalle: str
    #  Qué hacer. Una alerta sin acción es una queja.
    accion: str = ""
    #  La corrida involucrada, cuando la acción es sobre una en particular:
    #  el panel puede ofrecer el botón que la resuelve (D31).
    corrida_id: str | None = None

    def a_dict(self) -> dict[str, str | None]:
        return {
            "nivel": str(self.nivel),
            "codigo": self.codigo,
            "titulo": self.titulo,
            "detalle": self.detalle,
            "accion": self.accion,
            "corrida_id": self.corrida_id,
        }


async def revisar(base, *, ahora: datetime | None = None) -> list[Alerta]:
    """Todo lo que está mal ahora mismo, de lo más urgente a lo menos.

    La pausa global ya no genera alerta: el kill switch del panel muestra su
    propio cartel, y con los dos a la vez el freno aparecía duplicado (D31).
    """
    momento = ahora or datetime.now(UTC)

    alertas: list[Alerta] = []
    alertas += await _selector_roto(base, momento)
    alertas += await _sin_confirmar(base, momento)
    alertas += await _canario(base)
    alertas += await _maquinas(base, momento)

    urgentes = sum(1 for a in alertas if a.nivel is Nivel.URGENTE)
    if urgentes:
        log.warning("alertas_urgentes", cantidad=urgentes)

    orden = {Nivel.URGENTE: 0, Nivel.AVISO: 1}
    return sorted(alertas, key=lambda a: orden[a.nivel])


async def _selector_roto(base, ahora: datetime) -> list[Alerta]:
    """El DOM de WhatsApp cambió. Es cuestión de cuándo, no de si.

    Urgente porque frena la corrida entera: todos los envíos siguientes tienen
    exactamente el mismo problema, y hasta que alguien toque `selectores.py` no
    sale nada.
    """
    reciente = ahora - timedelta(hours=24)
    cuantos = await base["jobs"].count_documents(
        {"codigo": str(cola.Codigo.SELECTOR_ROTO), "terminado_en": {"$gte": reciente}}
    )
    if not cuantos:
        return []
    return [
        Alerta(
            Nivel.URGENTE,
            "selector_roto",
            "WhatsApp Web cambió",
            f"{cuantos} envíos fallaron porque la página ya no es la que el sistema conoce.",
            "Hay que actualizar los selectores. Hasta entonces no va a salir ningún mensaje.",
        )
    ]


async def _sin_confirmar(base, ahora: datetime) -> list[Alerta]:
    """⚠️ La peor de todas: puede haber salido y puede que no.

    Se apretó enviar y el mensaje no apareció en el hilo. No es "no salió": es
    "no sabemos". Por eso no se reintenta —mandarlo dos veces sería peor— y por
    eso alguien tiene que abrir ese chat y mirar con los ojos.
    """
    reciente = ahora - timedelta(hours=24)
    mensajes = (
        await base["mensajes"]
        .find(
            {
                "estado": str(Estado.DESCARTADO),
                "motivo": str(Motivo.SIN_CONFIRMAR),
                "creado_en": {"$gte": reciente},
            }
        )
        .to_list(None)
    )

    if not mensajes:
        return []

    contactos = ", ".join(m["contacto_nombre"] or m["contacto_id"] for m in mensajes[:3])
    return [
        Alerta(
            Nivel.URGENTE,
            "sin_confirmar",
            "Hay mensajes que no se pudieron confirmar",
            f"{len(mensajes)} mensajes se enviaron sin que el sistema pudiera ver "
            f"que llegaron: {contactos}.",
            "Abrí esos chats y fijate si el mensaje está. Puede haber salido, y puede que no.",
        )
    ]


async def _canario(base) -> list[Alerta]:
    """Los tres primeros fallaron y el sistema se frenó solo.

    Lleva la corrida (D31): la alerta trae al lado el botón que la resuelve
    —"ya lo miré, continuar"— en vez de quedar encendida sin salida, que es
    lo que pasó el 26/08.
    """
    frenadas = await base["corridas"].find({"estado": "frenada"}).to_list(None)
    return [
        Alerta(
            Nivel.URGENTE,
            "canario_fallido",
            "Una corrida se frenó sola",
            "Los primeros tres envíos fallaron, así que el sistema no soltó el resto.",
            "Mirá por qué fallaron antes de reanudar. Frenar costó menos que enterarse al final.",
            corrida_id=str(corrida["_id"]),
        )
        for corrida in frenadas
    ]


async def _maquinas(base, ahora: datetime) -> list[Alerta]:
    """Máquinas caídas con trabajo esperando, y máquinas degradadas.

    Una Mac apagada no es noticia: por eso el agente consulta en vez de recibir,
    y el job la espera. Se avisa cuando **hay trabajo encolado** para ella: ahí
    sí hay alguien esperando algo que no está pasando.
    """
    alertas: list[Alerta] = []
    corte = ahora - timedelta(minutes=MINUTOS_CAIDA)

    for vendedor in await base["vendedores"].find({}).to_list(None):
        maquina = vendedor["maquina"]

        # El freno del canario va ANTES del filtro de pausadas: una máquina
        # frenada cuenta como pausada, y sin esto su alerta no existiría — la
        # Mac quedaría muda justo cuando el sistema la frenó solo (D35).
        if vendedor.get("frenado_por_canario_en") is not None:
            alertas.append(
                Alerta(
                    Nivel.URGENTE,
                    "maquina_frenada_por_canario",
                    f"{vendedor.get('nombre') or maquina} se frenó sola",
                    "Sus primeros envíos de la corrida fallaron, así que sus envíos "
                    "pendientes no salen. Las demás máquinas siguen.",
                    "Mirá por qué fallaron. Reanudar o cancelar la corrida suelta el freno.",
                )
            )
            continue

        if vendedores.esta_pausada(vendedor, ahora=ahora):
            continue

        latido = vendedor.get("ultimo_latido")
        caida = latido is None or latido < corte

        if caida:
            pendientes = await base["jobs"].count_documents(
                {"maquina": maquina, "estado": str(cola.EstadoJob.PENDIENTE)}
            )
            if pendientes:
                alertas.append(
                    Alerta(
                        Nivel.URGENTE,
                        "maquina_caida",
                        f"{vendedor.get('nombre') or maquina} no responde",
                        f"Tiene {pendientes} trabajos esperando y no da señales "
                        f"hace más de {MINUTOS_CAIDA} minutos.",
                        "Fijate si la computadora está prendida y con sesión iniciada.",
                    )
                )
            continue

        fallando = sorted(
            n for n, estado in (vendedor.get("diagnostico") or {}).items() if estado == "falla"
        )

        # La sesión dedicada vencida tiene alerta propia (D24): es la falla que
        # nadie ve venir —una segunda sesión que el vendedor no mira— y tiene
        # una acción concreta. Metida en la lista genérica de chequeos se
        # perdería justo cuando más sirve: antes de encolar la corrida.
        if "whatsapp_sesion" in fallando:
            fallando.remove("whatsapp_sesion")
            alertas.append(
                Alerta(
                    Nivel.URGENTE,
                    "sesion_dedicada_vencida",
                    f"Venció la sesión del motor de {vendedor.get('nombre') or maquina}",
                    "El navegador que deja los borradores perdió su sesión: cualquier envío "
                    "va a fallar con SESION_CAIDA hasta re-vincular.",
                    "En esa Mac: correr el agente con --vincular y escanear el QR "
                    "desde el teléfono del vendedor.",
                )
            )

        if fallando:
            alertas.append(
                Alerta(
                    Nivel.AVISO,
                    "maquina_degradada",
                    f"{vendedor.get('nombre') or maquina} está a medias",
                    f"No pasa estos chequeos: {', '.join(fallando)}.",
                    "No va a tomar envíos hasta que se resuelvan.",
                )
            )

    return alertas
