"""Los endpoints que consume el panel.

Contrato en `docs/02-ARQUITECTURA.md` §4.2.

Quien usa esto es una o dos personas no técnicas de una empresa que vende
materiales. El dueño entra al mediodía, mira, aprieta y se va. Eso condiciona
las respuestas: lo que devuelven ya viene masticado —"online" en vez de una
marca de tiempo para restar, "qué chequeo falló" en vez de un diccionario— para
que la pantalla no tenga que decidir nada.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import db
from app.config import Configuracion, obtener_configuracion
from app.core import (
    alertas,
    auditoria,
    configuracion,
    contactos,
    corridas,
    mensajes,
    metricas,
    sesion,
    validacion,
    vendedores,
)
from app.logging import obtener_logger

log = obtener_logger(__name__)

router = APIRouter(prefix="/api", tags=["panel"])

# Cuánto puede pasar sin latido antes de mostrar una máquina como caída.
# El agente late cada 30 s: dos ventanas de margen para no pintar de rojo una
# Mac por un latido que se perdió.
SEGUNDOS_SIN_LATIDO = 90


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Ingreso(Estricto):
    clave: Annotated[str, Field(max_length=200)]


async def sesion_valida(
    config: Annotated[Configuracion, Depends(obtener_configuracion)],
    sesion_cookie: Annotated[str | None, Cookie(alias=sesion.NOMBRE_COOKIE)] = None,
) -> bool:
    if sesion.verificar(config.sesion_secret, sesion_cookie) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sesión inválida o vencida")
    return True


Autenticado = Annotated[bool, Depends(sesion_valida)]


@router.post("/sesion")
async def ingresar(
    cuerpo: Ingreso,
    respuesta: Response,
    config: Annotated[Configuracion, Depends(obtener_configuracion)],
) -> dict[str, Any]:
    """Login. Una contraseña, una cookie firmada."""
    if not sesion.clave_correcta(config.panel_password, cuerpo.clave):
        log.warning("ingreso_rechazado")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "contraseña incorrecta")

    respuesta.set_cookie(
        sesion.NOMBRE_COOKIE,
        sesion.emitir(config.sesion_secret),
        max_age=sesion.DURACION_SEGUNDOS,
        # `httponly`: el JavaScript de la página no la puede leer, así que un
        # script inyectado no se la lleva.
        httponly=True,
        # `samesite=lax`: no viaja en peticiones que arranquen desde otro sitio.
        samesite="lax",
        # En local va por http y la cookie tiene que llegar igual.
        secure=config.entorno == "produccion",
    )
    return {"ok": True}


@router.delete("/sesion")
async def salir(respuesta: Response) -> dict[str, Any]:
    respuesta.delete_cookie(sesion.NOMBRE_COOKIE)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Estado — la pantalla principal
# ---------------------------------------------------------------------------


def _resumir_maquina(vendedor: dict[str, Any], ahora: datetime) -> dict[str, Any]:
    """Una máquina, como la necesita la pantalla.

    El campo que importa es `chequeos_fallando`: el panel tiene que poder decir
    **qué** falta, no "error". Es la diferencia entre esto y el HTTP 502 mudo
    del MVP.
    """
    latido = vendedor.get("ultimo_latido")
    online = latido is not None and (ahora - latido) < timedelta(seconds=SEGUNDOS_SIN_LATIDO)
    diagnostico = vendedor.get("diagnostico") or {}
    fallando = sorted(n for n, estado in diagnostico.items() if estado == "falla")

    return {
        "maquina": vendedor["maquina"],
        "nombre": vendedor.get("nombre", ""),
        "activo": bool(vendedor.get("activo")),
        "pausada": vendedores.esta_pausada(vendedor, ahora=ahora),
        "online": online,
        "ultimo_latido": latido,
        "puede_enviar": vendedores.puede_enviar(vendedor),
        "chequeos_fallando": fallando,
        "diagnostico": diagnostico,
        "version_agente": vendedor.get("version_agente"),
        "tope_diario": vendedor.get("tope_diario", 20),
    }


@router.get("/estado")
async def estado(_: Autenticado) -> dict[str, Any]:
    """Todo lo que la pantalla principal necesita, en una sola llamada."""
    base = db.obtener_base()
    ahora = datetime.now(UTC)

    maquinas = [
        _resumir_maquina(v, ahora)
        for v in await base["vendedores"].find({}).sort("maquina", 1).to_list(None)
    ]
    config = await configuracion.obtener(base)

    desde_medianoche = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    enviados_hoy = await auditoria.contar(
        base, que=auditoria.Que.MENSAJE_ENVIADO, desde=desde_medianoche
    )

    permitidos = config.get("destinos_permitidos") or []
    return {
        "maquinas": maquinas,
        "corrida_en_curso": await corridas.en_curso(base),
        # También la terminada: cuando la generación acaba, la pantalla tiene
        # que ofrecer revisar los borradores en vez de quedarse como si nada
        # hubiera pasado.
        "ultima_corrida": await corridas.ultima_corrida(base),
        "pausa_global": bool(config.get("pausa_global")),
        "enviados_hoy": enviados_hoy,
        # Lo que decide si el sistema puede alcanzar a alguien real (R4). La
        # pantalla lo usa para la banda de "modo prueba": mientras la lista no
        # esté abierta, esto NO es producción por más que el servidor lo sea.
        "destinos_abiertos": configuracion.TODOS in permitidos,
        "destinos_permitidos": len(permitidos),
    }


# ---------------------------------------------------------------------------
# Máquinas
# ---------------------------------------------------------------------------


class AltaMaquina(Estricto):
    maquina: Annotated[str, Field(min_length=2, max_length=40, pattern=r"^[a-z0-9][a-z0-9-]*$")]
    nombre: Annotated[str, Field(min_length=1, max_length=80)]
    telefono_linea: Annotated[str | None, Field(max_length=25)] = None
    tope_diario: Annotated[int, Field(ge=1, le=100)] = 20


class CambioMaquina(Estricto):
    activo: bool | None = None
    tope_diario: Annotated[int | None, Field(ge=1, le=100)] = None
    pausado_hasta: datetime | None = None
    acepto_condiciones: bool | None = None


@router.post("/vendedores", status_code=status.HTTP_201_CREATED)
async def alta_maquina(cuerpo: AltaMaquina, _: Autenticado) -> dict[str, Any]:
    """Da de alta una máquina y devuelve su token **una sola vez**.

    Después de esto el token no se puede recuperar de ningún lado: se guarda
    hasheado. Si se pierde, se rota.
    """
    base = db.obtener_base()
    try:
        alta = await vendedores.dar_de_alta(
            base,
            maquina=cuerpo.maquina,
            nombre=cuerpo.nombre,
            telefono_linea=cuerpo.telefono_linea,
            tope_diario=cuerpo.tope_diario,
        )
    except vendedores.MaquinaDuplicada as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    await auditoria.registrar(
        base, que=auditoria.Que.MAQUINA_ALTA, quien="panel", detalle={"maquina": cuerpo.maquina}
    )
    return {
        "maquina": alta.maquina,
        "token": alta.token,
        "aviso": "Guardalo ahora: no se va a volver a mostrar.",
    }


@router.post("/vendedores/{maquina}/token")
async def rotar_token(maquina: str, _: Autenticado) -> dict[str, Any]:
    try:
        alta = await vendedores.rotar_token(db.obtener_base(), maquina)
    except vendedores.MaquinaDesconocida as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    return {"maquina": alta.maquina, "token": alta.token, "aviso": "El anterior dejó de servir."}


@router.patch("/vendedores/{maquina}")
async def editar_maquina(maquina: str, cuerpo: CambioMaquina, _: Autenticado) -> dict[str, Any]:
    base = db.obtener_base()
    cambios: dict[str, Any] = {}

    if cuerpo.activo is not None:
        cambios["activo"] = cuerpo.activo
    if cuerpo.tope_diario is not None:
        cambios["tope_diario"] = cuerpo.tope_diario
    if cuerpo.pausado_hasta is not None:
        cambios["pausado_hasta"] = cuerpo.pausado_hasta
    if cuerpo.acepto_condiciones is not None:
        # Se registra cuándo, no un booleano: el día que alguien pregunte "¿desde
        # cuándo sabe?", la respuesta tiene que ser una fecha.
        cambios["acepto_condiciones_en"] = datetime.now(UTC) if cuerpo.acepto_condiciones else None

    if not cambios:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no hay nada que cambiar")

    resultado = await base["vendedores"].update_one({"maquina": maquina}, {"$set": cambios})
    if resultado.matched_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no existe la máquina '{maquina}'")

    if cuerpo.acepto_condiciones:
        await auditoria.registrar(
            base,
            que=auditoria.Que.CONSENTIMIENTO_REGISTRADO,
            quien="panel",
            detalle={"maquina": maquina},
        )
    return {"ok": True, "cambios": sorted(cambios)}


@router.delete("/vendedores/{maquina}")
async def baja_maquina(maquina: str, _: Autenticado) -> dict[str, Any]:
    """Borra la máquina. Es también cómo se revoca su token."""
    base = db.obtener_base()
    try:
        await vendedores.dar_de_baja(base, maquina)
    except vendedores.MaquinaDesconocida as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    await auditoria.registrar(
        base, que=auditoria.Que.MAQUINA_BAJA, quien="panel", detalle={"maquina": maquina}
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# El botón
# ---------------------------------------------------------------------------


class NuevaCorrida(Estricto):
    tipo: corridas.TipoCorrida = corridas.TipoCorrida.DIAGNOSTICO
    n_chats: Annotated[int | None, Field(ge=1, le=50)] = None


@router.post("/corridas", status_code=status.HTTP_202_ACCEPTED)
async def disparar_corrida(cuerpo: NuevaCorrida, _: Autenticado) -> dict[str, Any]:
    """El botón. Devuelve al instante y encola."""
    base = db.obtener_base()
    try:
        disparo = await corridas.disparar(
            base, quien="panel", tipo=cuerpo.tipo, n_chats=cuerpo.n_chats
        )
    except corridas.NoHayMaquinas as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except corridas.Pausado as error:
        raise HTTPException(status.HTTP_423_LOCKED, str(error)) from error

    return {"id": str(disparo.corrida_id), "maquinas": disparo.maquinas, "jobs": disparo.jobs}


@router.post("/corridas/{corrida_id}/cancelar")
async def cancelar_corrida(corrida_id: str, _: Autenticado) -> dict[str, Any]:
    """Corta la corrida: lo pendiente se marca fallido y el botón se libera.

    Lo ya hecho queda hecho; los borradores generados siguen en revisión.
    """
    try:
        cortados = await corridas.cancelar(db.obtener_base(), _a_id(corrida_id), quien="panel")
    except corridas.CorridaDesconocida as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    return {"ok": True, "jobs_cortados": cortados}


@router.get("/corridas")
async def listar_corridas(_: Autenticado, limite: int = 50) -> dict[str, Any]:
    """Las últimas corridas, para la pantalla que las lista.

    Es lo único que el panel necesitaba y no existía. `GET /estado` trae la
    última y nada más, así que "¿qué corridas hubo esta semana?" no tenía
    respuesta — y es la primera pregunta que va a hacer el dueño cuando el
    sistema lleve un mes andando.

    El tope duro es 200: el panel las muestra en una tabla que alguien recorre
    con la vista, y un límite que el cliente elige sin techo es una consulta que
    algún día trae la colección entera.
    """
    return {"corridas": await corridas.recientes(db.obtener_base(), limite=min(limite, 200))}


@router.get("/corridas/{corrida_id}")
async def ver_corrida(corrida_id: str, _: Autenticado) -> dict[str, Any]:
    try:
        identificador = ObjectId(corrida_id)
    except InvalidId:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe esa corrida") from None

    detalle = await corridas.progreso(db.obtener_base(), identificador)
    if detalle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe esa corrida")
    return detalle


# ---------------------------------------------------------------------------
# Revisar los borradores, y el segundo botón
# ---------------------------------------------------------------------------


@router.post("/corridas/{corrida_id}/validar")
async def validar_corrida(corrida_id: str, _: Autenticado) -> dict[str, Any]:
    """Pasa los borradores por los guardrails y el triage.

    Lo dispara el panel cuando la generación termina. Devuelve cuántos quedaron
    en cada grupo y la proporción retenida, que es el número con el que se
    calibra el triage.
    """
    resultado = await validacion.validar_corrida(db.obtener_base(), _a_id(corrida_id))
    return {
        "en_espera": len(resultado.en_espera),
        "retenidos": len(resultado.retenidos),
        "rechazados": len(resultado.rechazados),
        "proporcion_retenida": round(resultado.proporcion_retenida, 3),
    }


@router.get("/corridas/{corrida_id}/mensajes")
async def mensajes_de_la_corrida(corrida_id: str, _: Autenticado) -> dict[str, Any]:
    """Los borradores, para la pantalla de revisión.

    Los retenidos van primero: son los que requieren una decisión. Y cada uno
    lleva sus señales, porque el panel tiene que decir POR QUÉ se retuvo, no
    sólo que se retuvo.
    """
    base = db.obtener_base()
    todos = await mensajes.de_la_corrida(base, _a_id(corrida_id))

    orden = {"RETENIDO": 0, "EN_ESPERA": 1, "BORRADOR": 2, "ENVIANDO": 3, "ENVIADO": 4}
    todos.sort(key=lambda m: (orden.get(m["estado"], 9), m["creado_en"]))

    return {
        "mensajes": [
            {
                "id": str(m["_id"]),
                "maquina": m["maquina"],
                "contacto_nombre": m.get("contacto_nombre", ""),
                "contacto_id": m["contacto_id"],
                "resumen": m.get("resumen_ultimo", ""),
                "texto": m["texto"],
                "estado": m["estado"],
                "motivo": m.get("motivo"),
                "senales": m.get("senales", []),
                "editado_por": m.get("editado_por"),
            }
            for m in todos
        ],
        "conteo": await mensajes.contar_por_estado(base, _a_id(corrida_id)),
    }


class TextoEditado(Estricto):
    texto: Annotated[str, Field(min_length=1, max_length=1000)]


@router.patch("/mensajes/{mensaje_id}")
async def editar_mensaje(mensaje_id: str, cuerpo: TextoEditado, _: Autenticado) -> dict[str, Any]:
    """Edita el texto de un borrador, y lo **revalida**.

    Un humano también puede empeorar un mensaje: si escribe `{nombre}` a mano se
    rechaza igual que si lo hubiera escrito el modelo. El sistema no tiene forma
    de saber cuál de los dos lo escribió, ni debería.

    Si el texto editado viola algo, se devuelve `422` con el detalle y **no se
    guarda**: lo que corresponde es que la persona lo corrija, no perder lo que
    acaba de escribir.
    """
    base = db.obtener_base()
    identificador = _a_id(mensaje_id)

    try:
        await mensajes.editar_texto(base, identificador, cuerpo.texto, quien="panel")
    except mensajes.MensajeDesconocido as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except mensajes.NoSePuedeEditar as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    violaciones = await validacion.revalidar_editado(base, identificador)
    if violaciones:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"problemas": [str(v) for v in violaciones]},
        )
    return {"ok": True}


@router.post("/mensajes/{mensaje_id}/veto")
async def vetar(mensaje_id: str, _: Autenticado) -> dict[str, Any]:
    """Frena un mensaje. Terminal: no se resucita, se genera uno nuevo."""
    from app.core.estados import Estado, Motivo

    await _mover(mensaje_id, Estado.DESCARTADO, motivo=Motivo.VETADO)
    return {"ok": True}


@router.post("/mensajes/{mensaje_id}/liberar")
async def liberar(mensaje_id: str, _: Autenticado) -> dict[str, Any]:
    """Libera un retenido: alguien lo miró y decidió que sale."""
    from app.core.estados import Estado

    await _mover(mensaje_id, Estado.EN_ESPERA)
    await auditoria.registrar(
        db.obtener_base(),
        que=auditoria.Que.MENSAJE_LIBERADO,
        quien="panel",
        mensaje_id=_a_id(mensaje_id),
    )
    return {"ok": True}


class Envio(Estricto):
    # `prueba` por defecto: para que algo salga de verdad hay que decirlo.
    modo: Literal["prueba", "real"] = "prueba"


@router.post("/corridas/{corrida_id}/enviar", status_code=status.HTTP_202_ACCEPTED)
async def enviar(corrida_id: str, cuerpo: Envio, _: Autenticado) -> dict[str, Any]:
    """**El segundo botón.** Encola los envíos de lo que quedó listo.

    Nada llega acá por inacción: la corrida generó borradores y se detuvo, y
    esto es lo que pasa cuando una persona mira y decide.
    """
    try:
        encolado = await corridas.preparar_envios(
            db.obtener_base(), _a_id(corrida_id), quien="panel", modo=cuerpo.modo
        )
    except corridas.Pausado as error:
        raise HTTPException(status.HTTP_423_LOCKED, str(error)) from error
    except corridas.FueraDeVentana as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    return {"mensajes": encolado.mensajes, "jobs": len(encolado.jobs), "modo": cuerpo.modo}


async def _mover(mensaje_id: str, estado, *, motivo=None) -> None:
    from app.core.estados import TransicionInvalida

    try:
        await mensajes.mover(
            db.obtener_base(), _a_id(mensaje_id), estado, motivo=motivo, quien="panel"
        )
    except mensajes.MensajeDesconocido as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except (TransicionInvalida, mensajes.CarreraDeEstados) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


def _a_id(crudo: str) -> ObjectId:
    try:
        return ObjectId(crudo)
    except InvalidId:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe") from None


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


class Pausa(Estricto):
    pausado: bool


@router.post("/sistema/pausa")
async def kill_switch(cuerpo: Pausa, _: Autenticado) -> dict[str, Any]:
    """Frena o suelta todo el sistema.

    El efecto es inmediato sin empujar nada: los agentes preguntan cada diez
    segundos y a partir del próximo reciben `423`.
    """
    base = db.obtener_base()
    await configuracion.pausar(base, pausado=cuerpo.pausado, quien="panel")
    await auditoria.registrar(
        base, que=auditoria.Que.KILL_SWITCH, quien="panel", detalle={"pausado": cuerpo.pausado}
    )
    return {"pausado": cuerpo.pausado}


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------


@router.get("/configuracion")
async def ver_configuracion(_: Autenticado) -> dict[str, Any]:
    config = await configuracion.obtener(db.obtener_base())
    config.pop("_id", None)
    return config


class CambioConfiguracion(Estricto):
    n_chats_por_defecto: Annotated[int | None, Field(ge=1, le=50)] = None
    # La ventana de antigüedad: desde y hasta cuántos días de silencio vale la
    # pena un seguimiento. Que min <= max se verifica en el endpoint, contra lo
    # que va a quedar guardado: acá puede venir un solo extremo.
    antiguedad_min_dias: Annotated[int | None, Field(ge=0, le=3650)] = None
    antiguedad_max_dias: Annotated[int | None, Field(ge=1, le=3650)] = None
    tope_diario_maquina: Annotated[int | None, Field(ge=1, le=100)] = None
    tope_por_corrida: Annotated[int | None, Field(ge=1, le=200)] = None
    largo_maximo: Annotated[int | None, Field(ge=50, le=1000)] = None
    dias_anti_duplicado: Annotated[int | None, Field(ge=1, le=90)] = None
    palabras_conflicto: list[Annotated[str, Field(max_length=60)]] | None = None
    palabras_comerciales: list[Annotated[str, Field(max_length=60)]] | None = None
    destinos_permitidos: list[Annotated[str, Field(max_length=25)]] | None = None

    @field_validator("destinos_permitidos")
    @classmethod
    def _a_e164(cls, numeros: list[str] | None) -> list[str] | None:
        """Guarda los destinos en E.164, que es como los compara R4.

        `destino_permitido()` hace `contacto_id in permitidos`: una comparacion
        de cadenas, exacta. El agente trae el numero ya normalizado, asi que un
        `+54 9 11 2323-1151` guardado tal como lo escribio una persona **no
        coincide con nada**, y ese contacto no recibe nunca un mensaje.

        Falla del lado seguro, pero calladita: la pantalla muestra tres numeros
        habilitados y el sistema entiende uno. Normalizar al guardar hace que lo
        que se ve sea lo que se compara.

        `*` pasa derecho: no es un numero, es la marca de lista abierta (R4).
        """
        if numeros is None:
            return None

        limpios: list[str] = []
        for crudo in numeros:
            if crudo.strip() == configuracion.TODOS:
                limpios.append(configuracion.TODOS)
                continue
            try:
                limpios.append(contactos.normalizar(crudo))
            except contactos.NumeroInvalido as error:
                raise ValueError(f"{crudo!r}: {error}") from error

        # Sin repetidos: dos formas del mismo numero colapsan al normalizar, y
        # una lista con duplicados hace dudar de cuantos destinos hay de verdad.
        return list(dict.fromkeys(limpios))


@router.patch("/configuracion")
async def cambiar_configuracion(cuerpo: CambioConfiguracion, _: Autenticado) -> dict[str, Any]:
    """Cambia topes, palabras o destinos permitidos.

    **Cambiar `destinos_permitidos` se audita aparte**, con la lista vieja y la
    nueva. Es la regla R4: es lo que decide si el sistema puede alcanzar a un
    cliente real, y abrirla tiene que dejar rastro de quién y cuándo.
    """
    base = db.obtener_base()
    cambios = cuerpo.model_dump(exclude_none=True)
    if not cambios:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no hay nada que cambiar")

    antes = await configuracion.obtener(base)

    # La ventana se valida contra lo que va a QUEDAR, no contra lo que vino: un
    # PATCH puede traer un solo extremo y el otro ya estar guardado.
    minimo = cambios.get("antiguedad_min_dias", antes.get("antiguedad_min_dias", 0))
    maximo = cambios.get("antiguedad_max_dias", antes.get("antiguedad_max_dias", 3650))
    if minimo > maximo:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"la ventana de antigüedad quedaría al revés: mínimo {minimo} > máximo {maximo}",
        )

    config = await configuracion.actualizar(base, cambios)

    if "destinos_permitidos" in cambios:
        await auditoria.registrar(
            base,
            que=auditoria.Que.DESTINOS_CAMBIADOS,
            quien="panel",
            detalle={
                "antes": antes.get("destinos_permitidos", []),
                "despues": cambios["destinos_permitidos"],
                "abierto_a_todos": configuracion.TODOS in cambios["destinos_permitidos"],
            },
        )
        log.warning("destinos_cambiados", cantidad=len(cambios["destinos_permitidos"]))
    else:
        await auditoria.registrar(
            base,
            que=auditoria.Que.CONFIGURACION_CAMBIADA,
            quien="panel",
            detalle={"campos": sorted(cambios)},
        )

    config.pop("_id", None)
    return config


# ---------------------------------------------------------------------------
# Alertas y métricas
# ---------------------------------------------------------------------------


@router.get("/alertas")
async def ver_alertas(_: Autenticado) -> dict[str, Any]:
    """Lo que está mal ahora mismo. No se guarda: se calcula al preguntar.

    Una alerta guardada hay que acordarse de borrarla cuando el problema se
    resuelve, y la que nadie borró es la que enseña a ignorarlas todas.
    """
    encontradas = await alertas.revisar(db.obtener_base())
    return {
        "alertas": [a.a_dict() for a in encontradas],
        "urgentes": sum(1 for a in encontradas if a.nivel is alertas.Nivel.URGENTE),
    }


@router.get("/metricas")
async def ver_metricas(_: Autenticado, dias: int = 30) -> dict[str, Any]:
    """Los números del período. El que importa es la tasa de edición."""
    return await metricas.del_periodo(db.obtener_base(), dias=min(dias, 365))


@router.get("/corridas/{corrida_id}/metricas")
async def metricas_de_la_corrida(corrida_id: str, _: Autenticado) -> dict[str, Any]:
    base = db.obtener_base()
    identificador = _a_id(corrida_id)
    await metricas.sincronizar_costo(base, identificador)
    return await metricas.de_la_corrida(base, identificador)


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------


@router.get("/historial")
async def historial(_: Autenticado, limite: int = 100) -> dict[str, Any]:
    """Lo último que pasó. Es la pantalla que se abre cuando alguien se queja."""
    eventos = await auditoria.recientes(db.obtener_base(), limite=min(limite, 500))
    for evento in eventos:
        evento["_id"] = str(evento["_id"])
        for campo in ("mensaje_id", "corrida_id"):
            if evento.get(campo) is not None:
                evento[campo] = str(evento[campo])
    return {"eventos": eventos}
