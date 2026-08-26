"""Máquinas: alta, baja, y el token con el que su agente se autentica.

**La cantidad de máquinas es variable.** Se dan de alta y de baja desde el
panel, como en el n8n del MVP. Nada acá adentro puede asumir un número fijo.

Sobre el token, porque la decisión parece floja y no lo es: se guarda hasheado
con SHA-256, no con Argon2id como decía el plan viejo.

Argon2 y bcrypt existen para secretos que elige un humano, que tienen poca
entropía y se pueden adivinar probando. Este token son 32 bytes de
`secrets.token_urlsafe`: nadie lo va a adivinar por fuerza bruta, y un KDF lento
sólo agregaría una dependencia y latencia a una consulta que corre cada 10
segundos por máquina. SHA-256 es la herramienta correcta para un secreto de alta
entropía.

Lo que sí importa y se conserva: **el token en claro no se guarda en ningún
lado.** Se muestra una vez al darlo de alta y después no se puede recuperar.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.logging import obtener_logger

log = obtener_logger(__name__)

# Prefijo para que se reconozca de un vistazo en un archivo de configuración o
# en un pegado de soporte, y para poder buscarlo si alguna vez se filtra.
PREFIJO = "sgc_"

# 32 bytes de entropía. Es el número que hace innecesario un KDF lento.
BYTES_DE_TOKEN = 32


class MaquinaDuplicada(Exception):
    """Ya existe una máquina con ese identificador."""

    def __init__(self, maquina: str) -> None:
        self.maquina = maquina
        super().__init__(f"ya existe una máquina llamada '{maquina}'")


class MaquinaDesconocida(Exception):
    def __init__(self, maquina: str) -> None:
        self.maquina = maquina
        super().__init__(f"no existe la máquina '{maquina}'")


@dataclass(frozen=True)
class AltaDeMaquina:
    """El resultado de dar de alta. El token **sólo existe acá**."""

    maquina: str
    token: str


def generar_token() -> str:
    return PREFIJO + secrets.token_urlsafe(BYTES_DE_TOKEN)


def hashear(token: str) -> str:
    """SHA-256 del token. Determinístico, para poder buscar por el hash."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def dar_de_alta(
    base,
    *,
    maquina: str,
    nombre: str,
    telefono_linea: str | None = None,
    tope_diario: int = 20,
    ahora: datetime | None = None,
) -> AltaDeMaquina:
    """Crea una máquina y devuelve su token, una sola vez.

    Nace **inactiva**: instalar no es activar. Se instala, se verifica que
    aparece online, y se activa después — de a una, según el calendario de alta.
    """
    momento = ahora or datetime.now(UTC)
    token = generar_token()

    try:
        await base["vendedores"].insert_one(
            {
                "maquina": maquina,
                "nombre": nombre,
                "telefono_linea": telefono_linea,
                "token_hash": hashear(token),
                "activo": False,
                "pausado_hasta": None,
                "tope_diario": tope_diario,
                "acepto_condiciones_en": None,
                "ultimo_latido": None,
                "diagnostico": {},
                "version_agente": None,
                "creado_en": momento,
            }
        )
    except DuplicateKeyError as error:
        raise MaquinaDuplicada(maquina) from error

    log.info("maquina_dada_de_alta", maquina=maquina)
    return AltaDeMaquina(maquina=maquina, token=token)


async def rotar_token(base, maquina: str) -> AltaDeMaquina:
    """Token nuevo. El anterior deja de servir en la petición siguiente.

    Rotar es regenerar: no hay período de gracia con dos tokens válidos. Con
    pocas máquinas de una misma oficina, la complejidad de una rotación
    escalonada no compra nada.
    """
    token = generar_token()
    resultado = await base["vendedores"].update_one(
        {"maquina": maquina}, {"$set": {"token_hash": hashear(token)}}
    )
    if resultado.matched_count == 0:
        raise MaquinaDesconocida(maquina)

    log.info("token_rotado", maquina=maquina)
    return AltaDeMaquina(maquina=maquina, token=token)


async def dar_de_baja(base, maquina: str) -> None:
    """Borra la máquina. Es también cómo se revoca su token."""
    resultado = await base["vendedores"].delete_one({"maquina": maquina})
    if resultado.deleted_count == 0:
        raise MaquinaDesconocida(maquina)
    log.info("maquina_dada_de_baja", maquina=maquina)


async def autenticar(base, token: str | None) -> dict[str, Any] | None:
    """La máquina dueña de ese token, o `None`.

    Busca por el hash, que está indexado: no recorre las máquinas comparando.

    Devuelve `None` en vez de lanzar, y el llamador decide el código de estado.
    Un token vacío o mal formado no es un caso especial: no coincide con nada,
    igual que uno inventado.
    """
    if not token:
        return None
    return await base["vendedores"].find_one({"token_hash": hashear(token)})


async def registrar_latido(
    base,
    maquina: str,
    *,
    diagnostico: dict[str, str] | None = None,
    version_agente: str | None = None,
    ahora: datetime | None = None,
) -> None:
    """Anota que la máquina está viva y con qué diagnóstico.

    La consulta de la cola **también** es un latido, pero esto se llama aparte
    para que una máquina sin trabajo siga apareciendo online. Sin eso, el panel
    mostraría en rojo a una Mac perfectamente sana que simplemente no tiene nada
    que hacer.
    """
    cambios: dict[str, Any] = {"ultimo_latido": ahora or datetime.now(UTC)}
    if diagnostico is not None:
        cambios["diagnostico"] = diagnostico
    if version_agente is not None:
        cambios["version_agente"] = version_agente

    await base["vendedores"].update_one({"maquina": maquina}, {"$set": cambios})


async def registrar_barrido(
    base,
    maquina: str,
    *,
    hasta_dias: int | None,
    tanda: list[str],
    completado: bool,
    ahora: datetime | None = None,
) -> None:
    """El cursor del barrido histórico de esta máquina (D27).

    `hasta_dias` es la antigüedad del chat MÁS NUEVO de la tanda que se acaba
    de procesar: la próxima corrida pide "los más viejos con hasta esos días",
    y así el barrido avanza del fondo del historial hacia hoy sin volver a
    empezar. `tanda` son los nombres recién vistos, para desempatar en la
    frontera. `completado` = la tanda vino incompleta: el barrido llegó al
    presente, y el panel lo puede decir.
    """
    momento = ahora or datetime.now(UTC)
    cambios: dict[str, Any] = {
        "barrido.ultima_tanda": [str(n)[:120] for n in tanda][:20],
        "barrido.actualizado_en": momento,
        "barrido.completado_en": momento if completado else None,
    }
    if hasta_dias is not None:
        cambios["barrido.hasta_dias"] = max(0, int(hasta_dias))

    await base["vendedores"].update_one({"maquina": maquina}, {"$set": cambios})
    log.info(
        "barrido_registrado",
        maquina=maquina,
        hasta_dias=hasta_dias,
        tanda=len(tanda),
        completado=completado,
    )


def esta_pausada(vendedor: dict[str, Any], *, ahora: datetime | None = None) -> bool:
    """¿Esta máquina está pausada ahora mismo?

    Dos formas de estarlo: `activo: False` (nunca se activó, o se apagó desde el
    panel) y `pausado_hasta` en el futuro (el vendedor apretó "pausar por hoy"
    en su barra de menú).

    Las dos existen porque son de personas distintas: la primera es del dueño,
    la segunda del vendedor sobre su propia máquina.
    """
    if not vendedor.get("activo"):
        return True
    hasta = vendedor.get("pausado_hasta")
    return hasta is not None and hasta > (ahora or datetime.now(UTC))


def puede_enviar(vendedor: dict[str, Any]) -> bool:
    """¿Se le pueden encolar envíos a esta máquina?

    Requiere consentimiento registrado. Salen mensajes en su nombre, desde su
    línea, que él puede no haber leído: tiene que constar que lo sabe.

    Es lo único de la lista de reglas que no protege al cliente final sino al
    vendedor, y es la más barata de cumplir — es una conversación.
    """
    return vendedor.get("acepto_condiciones_en") is not None
