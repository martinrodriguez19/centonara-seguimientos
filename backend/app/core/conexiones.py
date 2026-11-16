"""Las sesiones de cada máquina y cómo reconectarlas (D69-D73).

"Se cerró la sesión" son cuatro cosas distintas, que se caen por motivos
distintos y se arreglan distinto:

    whatsapp          WhatsApp Web en el Chrome del vendedor (la ruta de producción)
    claude_extension  la extensión Claude in Chrome, en ese mismo perfil
    claude_cli        Claude Code, que corre cada job (D68, D73)
    whatsapp_motor    el WhatsApp del navegador dedicado (D24)

**Quién sabe el estado es el agente**: él corre los jobs, la sonda y la vigía,
y lee el disco del perfil. Acá se guarda lo que reporta en cada latido, se
anotan las transiciones, y se arma lo que necesitan el panel, la página pública
y las alertas. Todo vive en el documento de `vendedores`: una colección nueva
pediría tocar el rol de Mongo de producción a mano (RUNBOOK-auditoria).

Las acciones de reconexión (`abrir_whatsapp`, `abrir_claude`, `verificar`)
viajan en la respuesta del latido y no por la cola (D70): la cola contesta 423
justo cuando más hacen falta —sin cuota, en pausa, con el canario frenado—.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.logging import obtener_logger

log = obtener_logger(__name__)

SESIONES = ("whatsapp", "claude_extension", "claude_cli", "whatsapp_motor")

OK = "ok"
CAIDA = "caida"
DESCONOCIDO = "desconocido"
ESTADOS = (OK, CAIDA, DESCONOCIDO)

# Las fuentes que saben de verdad: un job que usó la sesión, la sonda que la
# probó, la vigía que miró la página. La lectura del disco es una heurística, y
# por eso no excluye máquinas de una corrida (D69.4).
CON_AUTORIDAD = frozenset({"job", "sonda", "vigia"})

ACCIONES = ("abrir_whatsapp", "abrir_claude", "verificar")

# Una acción vieja no se ejecuta cuando la máquina despierta al otro día: diez
# minutos alcanzan para que llegue a una máquina despierta (latido cada 30 s).
MINUTOS_VENCE_ACCION = 10

# El tope de la página pública (D71): una por máquina y tipo cada dos minutos.
MINUTOS_ENTRE_ACCIONES = 2

# Cuántas acciones se recuerdan por máquina, contando las hechas.
ACCIONES_GUARDADAS = 20

# Las últimas transiciones de cada máquina, para la línea de tiempo del panel.
LARGO_HISTORIAL = 100

# Cuánto dura la alerta de "está entrando a Claude, pasale el código".
MINUTOS_RECONEXION_CLAUDE = 20

# Un token de `claude setup-token` dura un año. Se avisa un mes antes.
DIAS_TOKEN = 365
DIAS_AVISO_TOKEN = 30

ID_SECRETOS = "secretos"


class DemasiadoPronto(Exception):
    """Ya se pidió esta misma acción hace menos de `MINUTOS_ENTRE_ACCIONES`."""

    def __init__(self, segundos: int) -> None:
        self.segundos = segundos
        super().__init__(f"ya se pidió hace poco; probá de nuevo en {segundos} s")


def _utc(momento: datetime | None) -> datetime | None:
    """Mongo devuelve fechas sin zona; todo el sistema las piensa en UTC."""
    if momento is None:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Lo que reporta el latido
# ---------------------------------------------------------------------------


def _transiciones(
    anteriores: dict[str, Any], nuevas: dict[str, dict[str, str]], ahora: datetime
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """El estado a guardar, y las transiciones a anotar en el historial.

    `desde` se conserva mientras el estado no cambie: es "caída hace 3 días",
    no "caída según el último latido".
    """
    guardar: dict[str, Any] = {}
    cambios: list[dict[str, Any]] = []
    for nombre, observacion in nuevas.items():
        if nombre not in SESIONES:
            continue
        estado = observacion.get("estado")
        if estado not in ESTADOS:
            continue
        previa = anteriores.get(nombre) or {}
        cambio = previa.get("estado") != estado
        guardar[nombre] = {
            "estado": estado,
            "fuente": str(observacion.get("fuente") or "")[:20],
            "detalle": str(observacion.get("detalle") or "")[:300],
            "desde": ahora if cambio else (previa.get("desde") or ahora),
        }
        if cambio and previa:
            cambios.append(
                {
                    "sesion": nombre,
                    "antes": previa.get("estado"),
                    "estado": estado,
                    "fuente": guardar[nombre]["fuente"],
                    "detalle": guardar[nombre]["detalle"],
                    "cuando": ahora,
                }
            )
    return guardar, cambios


async def registrar(
    base,
    vendedor: dict[str, Any],
    *,
    sesiones: dict[str, dict[str, str]] | None = None,
    numero_vinculado: str | None = None,
    claude_token_hash: str | None = None,
    acciones_hechas: list[dict[str, str]] | None = None,
    ahora: datetime | None = None,
) -> None:
    """Guarda lo que el latido dijo de las sesiones. Todo opcional: un agente viejo no lo manda."""
    momento = ahora or datetime.now(UTC)
    operacion: dict[str, Any] = {}
    cambios: dict[str, Any] = {}

    if sesiones:
        guardar, transiciones = _transiciones(vendedor.get("sesiones") or {}, sesiones, momento)
        for nombre, valor in guardar.items():
            cambios[f"sesiones.{nombre}"] = valor
        if transiciones:
            operacion["$push"] = {
                "sesiones_historial": {"$each": transiciones, "$slice": -LARGO_HISTORIAL}
            }
            for t in transiciones:
                log.info(
                    "sesion_cambio",
                    maquina=vendedor.get("maquina"),
                    sesion=t["sesion"],
                    antes=t["antes"],
                    estado=t["estado"],
                    fuente=t["fuente"],
                )

    if numero_vinculado is not None:
        cambios["numero_vinculado"] = _solo_digitos(numero_vinculado) or None
    if claude_token_hash is not None:
        cambios["claude_token_hash"] = claude_token_hash[:64] or None

    if cambios:
        operacion["$set"] = cambios
    if operacion:
        await base["vendedores"].update_one({"maquina": vendedor["maquina"]}, operacion)

    # Una por una y con `arrayFilters`, no reescribiendo la lista: un `pedir`
    # que llega en el mismo instante agrega a la lista, y reescribirla con la
    # copia que se leyó al autenticar se lo llevaría puesto.
    for hecha in (acciones_hechas or [])[:ACCIONES_GUARDADAS]:
        await base["vendedores"].update_one(
            {"maquina": vendedor["maquina"]},
            {
                "$set": {
                    "acciones.$[a].hecha_en": momento,
                    "acciones.$[a].resultado": str(hecha.get("resultado") or "")[:300],
                }
            },
            array_filters=[{"a.id": str(hecha.get("id")), "a.hecha_en": None}],
        )


def estado_de(vendedor: dict[str, Any], sesion: str) -> str:
    return ((vendedor.get("sesiones") or {}).get(sesion) or {}).get("estado") or DESCONOCIDO


def _caida_con_autoridad(vendedor: dict[str, Any], sesion: str) -> bool:
    observacion = (vendedor.get("sesiones") or {}).get(sesion) or {}
    return observacion.get("estado") == CAIDA and observacion.get("fuente") in CON_AUTORIDAD


def excluida_por_sesion(vendedor: dict[str, Any]) -> str | None:
    """Por qué esta máquina no entra a una corrida por sus sesiones (D69.4), o `None`.

    Sólo lo que dijo un job o la sonda. Si la heurística del disco se equivoca,
    la máquina sigue entrando y el job dice la verdad.
    """
    if _caida_con_autoridad(vendedor, "whatsapp"):
        return "sin_whatsapp"
    if _caida_con_autoridad(vendedor, "claude_extension"):
        return "sin_claude"
    return None


# ---------------------------------------------------------------------------
# La línea vinculada (D72)
# ---------------------------------------------------------------------------


def _solo_digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def numero_coincide(telefono_linea: str | None, numero_vinculado: str | None) -> bool | None:
    """¿El WhatsApp vinculado es el de la máquina? `None` si no hay con qué comparar.

    Los últimos 10 dígitos: absorben el `9` de los móviles argentinos y el
    código de país, que WhatsApp y E.164 escriben distinto.
    """
    esperado = _solo_digitos(telefono_linea)
    vinculado = _solo_digitos(numero_vinculado)
    if len(esperado) < 10 or len(vinculado) < 10:
        return None
    return esperado[-10:] == vinculado[-10:]


def linea_equivocada(vendedor: dict[str, Any]) -> bool:
    coincide = numero_coincide(vendedor.get("telefono_linea"), vendedor.get("numero_vinculado"))
    return coincide is False


# ---------------------------------------------------------------------------
# Las acciones de reconexión (D70)
# ---------------------------------------------------------------------------


def pendientes(vendedor: dict[str, Any], *, ahora: datetime | None = None) -> list[dict[str, Any]]:
    """Lo que la máquina tiene que hacer: lo pedido, sin hacer y sin vencer."""
    momento = ahora or datetime.now(UTC)
    return [
        {"id": a["id"], "tipo": a["tipo"], "datos": a.get("datos") or {}}
        for a in vendedor.get("acciones") or []
        if a.get("hecha_en") is None and (_utc(a.get("vence_en")) or momento) > momento
    ]


async def pedir(
    base,
    vendedor: dict[str, Any],
    tipo: str,
    *,
    datos: dict[str, Any] | None = None,
    quien: str = "publico",
    ahora: datetime | None = None,
) -> dict[str, Any]:
    """Encola una acción para esta máquina. Lanza `DemasiadoPronto` si se repite muy seguido."""
    if tipo not in ACCIONES:
        raise ValueError(f"acción desconocida: {tipo}")
    momento = ahora or datetime.now(UTC)

    previas = vendedor.get("acciones") or []
    ultima = max(
        (_utc(a.get("pedida_en")) for a in previas if a.get("tipo") == tipo),
        default=None,
    )
    if ultima is not None:
        falta = ultima + timedelta(minutes=MINUTOS_ENTRE_ACCIONES) - momento
        if falta > timedelta(0):
            raise DemasiadoPronto(int(falta.total_seconds()) + 1)

    accion = {
        "id": secrets.token_hex(8),
        "tipo": tipo,
        "datos": datos or {},
        "quien": quien,
        "pedida_en": momento,
        "vence_en": momento + timedelta(minutes=MINUTOS_VENCE_ACCION),
        "hecha_en": None,
        "resultado": None,
    }
    await base["vendedores"].update_one(
        {"maquina": vendedor["maquina"]},
        {"$push": {"acciones": {"$each": [accion], "$slice": -ACCIONES_GUARDADAS}}},
    )
    log.info("reconexion_pedida", maquina=vendedor["maquina"], tipo=tipo, quien=quien)
    return accion


def ultima_accion(
    vendedor: dict[str, Any], tipos: tuple[str, ...], *, desde: datetime
) -> dict[str, Any] | None:
    """La acción más reciente de esos tipos pedida después de `desde`."""
    candidatas = [
        a
        for a in vendedor.get("acciones") or []
        if a.get("tipo") in tipos and (_utc(a.get("pedida_en")) or desde) >= desde
    ]
    return max(candidatas, key=lambda a: _utc(a["pedida_en"]), default=None)


# ---------------------------------------------------------------------------
# Lo que ve el vendedor (D71)
# ---------------------------------------------------------------------------


def _combinar(estados: list[str]) -> str:
    """Rojo si alguna está caída; verde si alguna anda y ninguna cayó; si no, no se sabe."""
    if CAIDA in estados:
        return CAIDA
    if OK in estados:
        return OK
    return DESCONOCIDO


def semaforo_whatsapp(vendedor: dict[str, Any], config: dict[str, Any]) -> str:
    """WhatsApp para el vendedor: el de su Chrome, y el del motor si esa ruta se usa."""
    estados = [estado_de(vendedor, "whatsapp")]
    if (config.get("modo_borrador") or "playwright") != "extension":
        estados.append(estado_de(vendedor, "whatsapp_motor"))
    return _combinar(estados)


def semaforo_claude(vendedor: dict[str, Any]) -> str:
    """Claude para el vendedor: sólo la extensión. Claude Code lo resuelve el token (D73)."""
    return estado_de(vendedor, "claude_extension")


# ---------------------------------------------------------------------------
# El token de Claude (D73)
# ---------------------------------------------------------------------------


def hash_corto(token: str) -> str:
    """Lo que la máquina reporta para decir qué token usa. Nunca el valor."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()[:16]


def token_valido(token: str) -> bool:
    """Lo que devuelve `claude setup-token`: `sk-ant-oat01-…`, sin espacios."""
    limpio = token.strip()
    return limpio.startswith("sk-ant-") and 40 <= len(limpio) <= 400 and " " not in limpio


async def leer_token(base) -> dict[str, Any] | None:
    """El token cargado, o `None`. **Nunca va al panel**: el panel ve `resumen_token`."""
    documento = await base["configuracion"].find_one({"_id": ID_SECRETOS})
    token = (documento or {}).get("claude_token")
    return token if token and token.get("valor") else None


async def cargar_token(base, token: str, *, ahora: datetime | None = None) -> dict[str, Any]:
    if not token_valido(token):
        raise ValueError("no parece un token de `claude setup-token` (empieza con sk-ant-)")
    limpio = token.strip()
    documento = {
        "valor": limpio,
        "hash": hash_corto(limpio),
        "cargado_en": ahora or datetime.now(UTC),
    }
    await base["configuracion"].update_one(
        {"_id": ID_SECRETOS}, {"$set": {"claude_token": documento}}, upsert=True
    )
    log.warning("token_claude_cargado", hash=documento["hash"])
    return documento


async def borrar_token(base) -> None:
    await base["configuracion"].update_one(
        {"_id": ID_SECRETOS}, {"$unset": {"claude_token": ""}}, upsert=True
    )
    log.warning("token_claude_borrado")


def resumen_token(token: dict[str, Any] | None, maquinas: list[dict[str, Any]]) -> dict[str, Any]:
    """Lo que el panel puede saber del token: si hay, desde cuándo, y quién lo tiene."""
    activas = [m for m in maquinas if m.get("activo")]
    if not token:
        return {
            "cargado": False,
            "cargado_en": None,
            "vence_aprox": None,
            "maquinas_al_dia": 0,
            "maquinas_activas": len(activas),
        }
    cargado_en = _utc(token.get("cargado_en"))
    return {
        "cargado": True,
        "cargado_en": cargado_en,
        "vence_aprox": cargado_en + timedelta(days=DIAS_TOKEN) if cargado_en else None,
        "maquinas_al_dia": sum(1 for m in activas if m.get("claude_token_hash") == token["hash"]),
        "maquinas_activas": len(activas),
    }


def token_para(vendedor: dict[str, Any], token: dict[str, Any] | None, reportado: str | None):
    """El token a mandarle a esta máquina en el latido, o `None`.

    Sólo a un agente que reporta el hash (sabe qué hacer con él) y usa otro.
    """
    if not token or reportado is None or reportado == token["hash"]:
        return None
    log.info("token_claude_repartido", maquina=vendedor.get("maquina"))
    return token["valor"]
