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
    """Leer hasta N chats cuya antigüedad caiga en la ventana configurada."""

    n_chats: Annotated[int, Field(ge=1, le=MAX_CHATS)] = 20
    run_id: Annotated[str, Field(max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
    antiguedad_min_dias: Annotated[int, Field(ge=0, le=3650)] = 0
    antiguedad_max_dias: Annotated[int, Field(ge=1, le=3650)] = 3650


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


class PayloadDiagnostico(PayloadBase):
    """Correr los chequeos y reportar. No lleva nada."""


POR_TIPO: dict[str, type[PayloadBase]] = {
    "LISTAR": PayloadListar,
    "RESOLVER": PayloadResolver,
    "REDACTAR": PayloadRedactar,
    "ENVIAR": PayloadEnviar,
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
