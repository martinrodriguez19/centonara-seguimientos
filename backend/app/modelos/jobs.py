"""Los payloads de cada tipo de job.

Es el equivalente del `ALLOWED_VARS` del MVP, con esquemas en vez de un `set`.

**Por la red viajan variables validadas, nunca texto de prompt.** El prompt es
fijo y vive en el disco de la máquina del vendedor; el backend sólo manda con
qué rellenarlo. Un backend comprometido no tiene que poder hacer que el agente
ejecute algo arbitrario.

Eso lo garantiza `extra="forbid"`: un campo que no está declarado acá abajo no
pasa, y el rechazo lo hace el esquema y no un `if` que alguien puede olvidarse
de escribir.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.configuracion import LARGO_CONTEXTO_EMPRESA
from app.core.contactos import NumeroInvalido, normalizar

# Cota dura sobre cuántos chats se leen de una. La tenía el MVP y se conserva:
# es lo que impide que un error de configuración dispare una lectura enorme.
MAX_CHATS = 50


class PayloadBase(BaseModel):
    """Prohíbe todo lo que no esté declarado.

    Sin esto, agregar `{"prompt": "..."}` al payload sería silenciosamente
    aceptado y quedaría a criterio del agente ignorarlo. Con esto, es un 422.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class PayloadListar(PayloadBase):
    """Leer hasta N chats: los recientes de la ventana, o el barrido histórico."""

    n_chats: Annotated[int, Field(ge=1, le=MAX_CHATS)] = 20
    run_id: Annotated[str, Field(max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
    antiguedad_min_dias: Annotated[int, Field(ge=0, le=3650)] = 0
    antiguedad_max_dias: Annotated[int, Field(ge=1, le=3650)] = 3650
    # El barrido (D27): desde el fondo del historial hacia hoy. `barrido_hasta_dias`
    # es el cursor — sólo interesan chats con antigüedad MENOR O IGUAL a eso — y
    # `ya_vistos` son los nombres de la tanda anterior, para no repetir en la
    # frontera cuando varios chats comparten antigüedad.
    estrategia: Literal["recientes", "barrido"] = "recientes"
    barrido_hasta_dias: Annotated[int, Field(ge=0, le=3650)] = 3650
    ya_vistos: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=120)]], Field(max_length=20)
    ] = []


class PayloadResolver(PayloadBase):
    """Abrir chats por nombre y leer el número real del panel de contacto.

    Sólo lectura, en el navegador dedicado. Los datos del chat (resumen,
    antigüedad) NO viajan acá: quedan en el `contexto` del job, del lado del
    backend, esperando el número para convertirse en un `REDACTAR`.
    """

    contactos: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=120)]],
        Field(min_length=1, max_length=MAX_CHATS),
    ]


class PayloadRedactar(PayloadBase):
    """Redactar un seguimiento. Sin navegador: todo el contexto va acá."""

    contacto_nombre: Annotated[str, Field(min_length=1, max_length=120)]
    resumen: Annotated[str, Field(min_length=1, max_length=400)]
    quien_hablo_ultimo: Literal["contacto", "vendedor"]
    antiguedad_dias: Annotated[int, Field(ge=0, le=3650)]
    largo_maximo: Annotated[int, Field(ge=50, le=1000)] = 600
    # Las indicaciones del dueño sobre su empresa (D33). Mandan sobre qué dice
    # el mensaje y con qué tono; las prohibiciones del prompt —no inventar
    # datos, no dejar placeholders— y la tarea no las puede cambiar.
    contexto_empresa: Annotated[str, Field(max_length=LARGO_CONTEXTO_EMPRESA)] = ""


class PayloadEnviar(PayloadBase):
    """Escribir y enviar un mensaje ya redactado y validado."""

    mensaje_id: Annotated[str, Field(max_length=64)]
    contacto_id: Annotated[str, Field(max_length=20)]
    contacto_nombre: Annotated[str, Field(min_length=1, max_length=120)]
    texto: Annotated[str, Field(min_length=1, max_length=1000)]
    # No hay un `modo="real"` por defecto en ningún lado del sistema: para que
    # algo salga de verdad hay que decirlo explícitamente.
    modo: Literal["prueba", "real"] = "prueba"

    @field_validator("contacto_id")
    @classmethod
    def en_e164(cls, valor: str) -> str:
        """El destino viaja ya normalizado, y se rechaza si no lo está.

        El agente lo va a comparar contra lo que lea del chat abierto (R1). Si
        acá entrara `011 4440-5036` y allá se leyera `+5491144405036`, la
        comparación fallaría siempre y no se enviaría nunca — o, peor, alguien
        "arreglaría" la comparación aflojándola.
        """
        try:
            return normalizar(valor)
        except NumeroInvalido as error:
            raise ValueError(f"contacto_id no es un E.164 válido: {error.motivo}") from error


class PayloadBorradores(PayloadBase):
    """El pase único: leer cada chat frío y dejar el borrador ahí mismo.

    Las listas son la forma nueva de R3: el backend decide a quién no
    escribirle y a quién sí, y eso viaja como **dato** — el prompt las obedece,
    no las calcula. `n_chats` es el tamaño de la tanda; la siguiente la encola
    el backend al procesar el reporte, con `ya_vistos` acumulado.
    """

    n_chats: Annotated[int, Field(ge=1, le=12)] = 6
    run_id: Annotated[str, Field(max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
    antiguedad_min_dias: Annotated[int, Field(ge=0, le=3650)] = 0
    antiguedad_max_dias: Annotated[int, Field(ge=1, le=3650)] = 3650
    # Nombres visitados en tandas anteriores de esta corrida: no se vuelven a abrir.
    ya_vistos: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=120)]], Field(max_length=60)
    ] = []
    # Contactos con un mensaje reciente del sistema (anti-duplicado, G5): se
    # saltean sin abrirlos.
    no_escribir: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=120)]], Field(max_length=60)
    ] = []
    # R4 cuando la lista de destinos no es "*": sólo chats cuyo número visible
    # esté acá pueden recibir borrador. Vacía = sin restricción (la lista era
    # "*"); una lista vacía de destinos no llega a encolar este job.
    solo_numeros: Annotated[list[Annotated[str, Field(max_length=25)]], Field(max_length=60)] = []
    largo_maximo: Annotated[int, Field(ge=50, le=1000)] = 600
    contexto_empresa: Annotated[str, Field(max_length=LARGO_CONTEXTO_EMPRESA)] = ""


class PayloadDiagnostico(PayloadBase):
    """Correr los chequeos y reportar. No lleva nada."""


POR_TIPO: dict[str, type[PayloadBase]] = {
    "LISTAR": PayloadListar,
    "RESOLVER": PayloadResolver,
    "REDACTAR": PayloadRedactar,
    "ENVIAR": PayloadEnviar,
    "BORRADORES": PayloadBorradores,
    "DIAGNOSTICO": PayloadDiagnostico,
}


def validar_payload(tipo: str, payload: dict) -> PayloadBase:
    """Valida un payload contra el esquema de su tipo.

    Se llama **al encolar**, no al entregar: un payload inválido tiene que
    romper cuando alguien lo escribió, no media hora después en la máquina de un
    vendedor.
    """
    esquema = POR_TIPO.get(tipo)
    if esquema is None:
        raise ValueError(f"tipo de job desconocido: {tipo}")
    return esquema.model_validate(payload)
