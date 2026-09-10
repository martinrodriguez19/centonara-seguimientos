"""`BORRADORES`: el pase único — leer el chat y dejar el borrador ahí mismo.

Un solo recorrido con la extensión: el modelo abre cada conversación fría,
entiende de qué se hablaba, escribe el seguimiento en el campo de texto **sin
enviarlo** y pasa al siguiente. El chat nunca se vuelve a buscar — que es
exactamente lo que elimina la clase de errores del 28/08 (`CHAT_NO_ABRE` y
todos sus parientes): no hay segundo encuentro que pueda abrir el chat
equivocado.

Quien envía es el vendedor, a mano, chat por chat. El sistema no aprieta enviar
en esta ruta bajo ninguna circunstancia.

Igual que `listar`, lo que este módulo agrega sobre la invocación cruda es
**desconfiar de la respuesta**. Cada chat del reporte se revisa: sin nombre se
descarta y se cuenta; un `texto_borrador` vacío con `borrador_dejado: true` es
contradictorio y se degrada a "no dejado"; un teléfono no se completa nunca.
Y hay un motivo que corta todo: `texto_enviado` significa que un texto salió
enviado en vez de quedar como borrador — la tarea falló y el reporte lo dice
con nombre propio, porque es lo primero que va a mirar una persona.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agente.jobs.claude_code import TIMEOUT_BORRADORES, Invocacion, invocar
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# La misma cota que el backend (`chats_por_tanda` tiene tope 12 en el panel).
# Última barrera local antes de pedirle una tanda a un modelo.
MAX_POR_TANDA = 12

# Cuántos nombres entran en cada lista del prompt. Acotado para que un backend
# con un bug no infle el prompt hasta el timeout.
MAX_NOMBRES_EN_LISTA = 60

# `ya_vistos` entra el doble (D43): con veinte por día y contando los
# salteados, sesenta se llenaban en un día. Coincide con `pase_unico.MAX_YA_VISTOS`.
MAX_YA_VISTOS_EN_LISTA = 120

# `no_escribir` entra el doble. Es la lista que evita escribirle dos veces a la
# misma persona: recortarla acá, del lado del agente, sería deshacer en silencio
# lo que el backend calculó bien. Coincide con `pase_unico.MAX_NO_ESCRIBIR`.
MAX_NO_ESCRIBIR_EN_LISTA = 120

MOTIVOS_DE_ERROR = {
    "sesion_no_iniciada": "SESION_CAIDA",
    "browser_no_disponible": "ERROR_INESPERADO",
    #  ⚠️ El que no puede pasar desapercibido: un texto quedó ENVIADO en vez de
    #  como borrador. No se reintenta —reintentar sería arriesgar otro— y el
    #  código propio lo hace visible en el panel y en los logs.
    "texto_enviado": "TEXTO_ENVIADO",
}

QUE_SIGNIFICA = {
    "sesion_no_iniciada": "WhatsApp Web pide escanear el código QR en el Chrome de esta máquina",
    "browser_no_disponible": (
        "la extensión de Claude no está disponible en esta máquina: suele ser que Chrome "
        "está cerrado, o que se abrió con otro perfil"
    ),
    "texto_enviado": (
        "un borrador salió ENVIADO en vez de quedar escrito: revisar ese chat en el "
        "WhatsApp del vendedor antes de volver a correr"
    ),
}

#  Por qué un chat visitado quedó sin borrador. Cualquier otro valor se guarda
#  como "otro": no se pierde, pero tampoco se inventa un vocabulario nuevo.
#
#  `disconforme` y `ya_compro` (D41) son los dos que además vetan al contacto
#  para las corridas siguientes. `ya_compro` es el único que puede venir en un
#  chat CON borrador: el post-venta deja mensaje y la venta igual queda cerrada.
MOTIVOS_DE_SALTEO = {
    "campo_ocupado",
    "sin_tema",
    "fuera_de_lista",
    "disconforme",
    "ya_compro",
    #  El número visible del chat ya recibió mensaje (D43): otro nombre, la
    #  misma persona. Se ve recién al abrir, por eso no entra en las listas
    #  de nombres.
    "numero_repetido",
}

#  Por qué la tanda devolvió menos de lo pedido (D44). `tope_de_visitas` es el
#  freno normal desde que las reglas de redacción saltean más chats: una tanda
#  que abre `max_visitas` sin llenar su cupo vuelve igual, con lo que leyó.
CORTES = {"n_chats", "tope_de_visitas", "fin_de_ventana", "tiempo"}

QUIEN_HABLO = {"contacto": "contacto", "yo": "vendedor", "vendedor": "vendedor"}

# ---------------------------------------------------------------------------
# Cómo recorrer la lista: los dos bloques que rellenan `{{COMO_RECORRER}}`
# ---------------------------------------------------------------------------
#
# ⚠️ Son dos bloques dentro de UN prompt, y no dos archivos como
# `prompt-listar.txt` / `prompt-barrido.txt`. El motivo es concreto: lo único
# que cambia entre las dos estrategias es CÓMO se eligen los chats — todo lo
# demás (las tres reglas, el recorrido chat por chat, las indicaciones del
# dueño, las prohibiciones al redactar, el formato de salida) tiene que ser
# idéntico, y duplicarlo en dos archivos es garantizar que un día diverjan.
# Justo la mitad que no puede divergir es la de redacción.

RECORRIDO_RECIENTES = """2. Lo que se busca son conversaciones FRIAS: chats cuyo
   ultimo mensaje tenga entre {{ANTIGUEDAD_MIN}} y {{ANTIGUEDAD_MAX}} dias de
   antiguedad. Recorre la
   lista desde arriba hacia abajo, scrolleando lo que haga falta: los chats de
   hoy y de ayer probablemente NO califican y los que buscas estan mas abajo.

   Esta es UNA TANDA de un recorrido mas largo: el backend lleva la cuenta y te
   va a pedir la siguiente desde donde cortaste. Frena cuando pase CUALQUIERA
   de estas tres cosas:
     - dejaste {{N_CHATS}} borradores;
     - ABRISTE {{MAX_VISITAS}} chats, contando los que salteaste despues de
       abrir. Es normal que pase antes de llegar a {{N_CHATS}}: devolve lo que
       tengas y el sistema sigue desde ahi;
     - los chats que ves ya son mas viejos que {{ANTIGUEDAD_MAX}} dias.

   Lo unico que tenes que hacer bien es decir POR QUE frenaste, en dos campos:
   "fin_de_ventana":
     - true  = recorriste la ventana entera y ya no queda NINGUN chat sin
               visitar entre {{ANTIGUEDAD_MIN}} y {{ANTIGUEDAD_MAX}} dias
     - false = quedan chats por visitar, pero cortaste antes
   Llegar a {{N_CHATS}} o a {{MAX_VISITAS}} es SIEMPRE false: quedan chats y la
   proxima tanda sigue desde ahi. Marcar true por error da la ventana por
   agotada y hace que no se deje ni un borrador mas en toda la corrida. Ante la
   duda, false.
   "corte": "n_chats" | "tope_de_visitas" | "fin_de_ventana" | "tiempo",
   segun cual de las causas te freno."""

RECORRIDO_VENTANA_ASCENDENTE = """2. Lo que se busca son conversaciones FRIAS: chats cuyo
   ultimo mensaje tenga entre {{ANTIGUEDAD_MIN}} y {{ANTIGUEDAD_MAX}} dias de
   antiguedad, recorridos DEL MAS VIEJO AL MAS NUEVO. El backend lleva un
   cursor por maquina; tu tanda es esta.

   Scrollea la lista hacia abajo hasta pasar los chats de {{VENTANA_HASTA_DIAS}}
   dias de antiguedad (o hasta el fondo, si no hay tantos). Desde ahi recorre
   HACIA ARRIBA, hacia hoy: los chats MAS VIEJOS cuyo ultimo mensaje tenga
   {{VENTANA_HASTA_DIAS}} dias o menos — los que tengan MAS ya se procesaron en
   tandas anteriores, salteolos — y nunca menos de {{ANTIGUEDAD_MIN}} dias. Un
   chat con MENOS de {{ANTIGUEDAD_MIN}} dias es demasiado fresco: ahi termina
   la ventana. Devolvelos en ese orden, del mas viejo al mas nuevo.

   Frena cuando pase CUALQUIERA de estas tres cosas:
     - dejaste {{N_CHATS}} borradores;
     - ABRISTE {{MAX_VISITAS}} chats, contando los que salteaste despues de
       abrir. Es normal que pase antes de llegar a {{N_CHATS}}: devolve lo que
       tengas y el sistema sigue desde ahi;
     - llegaste a chats de menos de {{ANTIGUEDAD_MIN}} dias: la ventana se
       termino.

   Lo unico que tenes que hacer bien es decir POR QUE frenaste, en dos campos:
   "fin_de_ventana":
     - true  = llegaste al limite de {{ANTIGUEDAD_MIN}} dias y no queda NINGUN
               chat sin visitar entre {{ANTIGUEDAD_MIN}} y {{VENTANA_HASTA_DIAS}}
               dias
     - false = quedan chats por visitar, pero cortaste antes
   Llegar a {{N_CHATS}} o a {{MAX_VISITAS}} es SIEMPRE false: quedan chats y la
   proxima tanda sigue desde ahi. Marcar true por error hace que la proxima
   corrida vuelva a empezar desde el fondo de la ventana. Ante la duda, false.
   "corte": "n_chats" | "tope_de_visitas" | "fin_de_ventana" | "tiempo",
   segun cual de las causas te freno."""

RECORRIDO_BARRIDO = """2. Esta es una pasada de BARRIDO DEL HISTORIAL: la empresa esta recuperando a
   sus clientes viejos, recorriendo todos los chats desde el MAS ANTIGUO hacia
   hoy, de a tandas. El backend lleva el cursor; tu tanda es esta.

   Scrollea la lista de chats HASTA EL FONDO: los mas viejos estan al final, y
   ahi arranca tu tanda. Busca los chats MAS VIEJOS cuyo ultimo mensaje tenga
   {{HASTA_DIAS}} dias o menos de antiguedad — los que tengan MAS ya se
   procesaron en tandas anteriores, salteolos. Recorrelos DEL MAS VIEJO AL MAS
   NUEVO, y devolvelos en ese orden.

   Frena cuando hayas dejado {{N_CHATS}} borradores, o cuando hayas ABIERTO
   {{MAX_VISITAS}} chats contando los que salteaste despues de abrir. Devolver
   menos esta bien y es preferible a no devolver nada: si la tanda se hace
   larga, corta y devolve lo que ya tengas — el sistema sigue desde ahi en la
   proxima tanda. Lo unico que tenes que hacer bien es decir POR QUE devolves
   menos, en dos campos:
   "fin_de_ventana":
     - true  = ya no quedan chats mas viejos sin procesar: el barrido termino
     - false = quedan, pero cortaste antes (por tiempo, por llegar a
               {{N_CHATS}}, o por abrir {{MAX_VISITAS}})
   Marcar true por error hace que el sistema de por terminado el barrido y no
   vuelva a mirar el historial. Ante la duda, false.
   "corte": "n_chats" | "tope_de_visitas" | "fin_de_ventana" | "tiempo",
   segun cual de las causas te freno."""

# ---------------------------------------------------------------------------
# La venta cerrada (D41): con post-venta, o sin nada
# ---------------------------------------------------------------------------
#
# Lo que cambia con `mensaje_post_compra` es SOLO qué se hace con un chat donde
# la compra ya se hizo. Lo que no cambia, en ninguna de las dos variantes: no se
# le pregunta por esa venta, y el motivo `ya_compro` viaja igual — es lo que
# cierra al contacto para las corridas siguientes.

POST_VENTA_ACTIVO = """                        Dos opciones, y nada mas:
                          - si el chat es claro, dejas un mensaje de
                            POST-VENTA: preguntas si le falto algo o si quedo
                            todo bien. Ni una palabra de volver a comprar.
                          - si no esta claro, no dejas nada.
                        En los dos casos anotas motivo "ya_compro"."""

POST_VENTA_APAGADO = """                        NO dejes borrador. Anota el chat con motivo
                        "ya_compro" y segui con el proximo."""

# Con algo para ofrecer (`post_venta_ofrecer`, en palabras del dueño): el
# post-venta pregunta cómo le fue Y ofrece eso, en la misma línea. Sigue sin
# preguntar por la venta cerrada. Con la perilla vacía no se usa este bloque y
# el prompt es idéntico al de siempre.
POST_VENTA_CON_OFERTA = """                        Dos opciones, y nada mas:
                          - si el chat es claro, dejas un mensaje de
                            POST-VENTA: preguntas como le fue con lo que
                            compro y, en la misma linea, le ofreces esto que
                            dejo el dueño (con sus palabras, sin inventar
                            nada que no este ahi):
{{POST_VENTA_OFERTA}}
                            Ni una palabra de la venta ya cerrada: no le
                            preguntes si le llego, si quiere mas de eso ni
                            si quiere avanzar con eso.
                          - si no esta claro, no dejas nada.
                        En los dos casos anotas motivo "ya_compro"."""


@dataclass(frozen=True)
class Resultado:
    ok: bool
    codigo: str | None = None
    detalle: dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    stderr: str = ""
    costo_usd: float = 0.0

    def a_reporte(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "codigo": self.codigo,
            "detalle": self.detalle,
            "raw": self.raw,
            "stderr": self.stderr,
            "costo_usd": self.costo_usd,
        }


async def dejar_borradores(
    *,
    n_chats: int,
    run_id: str,
    device_id: str,
    claude_bin: str,
    carpeta: Path,
    antiguedad_min_dias: int = 0,
    antiguedad_max_dias: int = 3650,
    estrategia: str = "recientes",
    barrido_hasta_dias: int = 3650,
    orden: str = "mas_nuevos_primero",
    ventana_hasta_dias: int = 3650,
    ya_vistos: list[str] | None = None,
    no_escribir: list[str] | None = None,
    no_escribir_numeros: list[str] | None = None,
    solo_numeros: list[str] | None = None,
    contexto_empresa: str = "",
    largo_maximo: int = 600,
    max_visitas: int = 20,
    frases_prohibidas: list[str] | None = None,
    palabras_veto: list[str] | None = None,
    mensaje_post_compra: bool = True,
    post_venta_ofrecer: str = "",
    invocador=invocar,
) -> Resultado:
    """Una tanda del pase único: hasta `n_chats` borradores dejados.

    Dos estrategias, la misma que el circuito viejo (D27):

    - `recientes` — dentro de la ventana de antigüedad. Con `orden =
      "mas_nuevos_primero"` de arriba hacia abajo, como siempre; con
      `"mas_viejos_primero"` (D43) del extremo viejo de la ventana hacia hoy,
      con el cursor `ventana_hasta_dias` que el backend lleva por máquina.
    - `barrido` — desde el fondo del historial hacia hoy, los más viejos con
      antigüedad menor o igual a `barrido_hasta_dias`. El cursor lo lleva el
      backend, por máquina, y avanza con cada tanda que vuelve.

    Las listas vienen del backend ya calculadas (R3): `ya_vistos` son los
    nombres ya recorridos —de tandas anteriores de esta corrida y, en barrido,
    de la frontera de la corrida previa—, `no_escribir` los contactos con un
    mensaje reciente del sistema (anti-duplicado), y `solo_numeros` —si no está
    vacía— restringe a chats cuyo número visible esté en la lista.

    Las de redacción (D40, D41) también son datos del dueño y no del prompt:
    `palabras_veto` marca un chat como disconforme, `frases_prohibidas` es lo
    que el borrador no puede decir, `mensaje_post_compra` decide qué se hace
    con una venta cerrada, y `max_visitas` es el segundo freno de la tanda
    (D44) — chats abiertos, no borradores dejados.
    """
    if not device_id:
        # Problema #5 del MVP: con más de un Chrome conectado a la cuenta,
        # headless elige cualquiera — y puede ser el WhatsApp de otra persona.
        return Resultado(
            False, "ERROR_INESPERADO", {"motivo": "sin deviceId: no se sabe a qué Chrome ir"}
        )

    minimo = max(0, int(antiguedad_min_dias))
    maximo = max(minimo, int(antiguedad_max_dias))

    if solo_numeros:
        numeros = "\n".join(f"  - {n}" for n in solo_numeros[:MAX_NOMBRES_EN_LISTA])
        restriccion = (
            "SOLO se deja borrador en chats cuyo numero de telefono este visible "
            "con certeza Y coincida (comparando digito a digito) con uno de esta "
            "lista. Un chat sin numero visible, o con un numero que no esta, se "
            f'saltea con motivo "fuera_de_lista":\n{numeros}'
        )
    else:
        restriccion = "ninguna: cualquier chat que califique puede recibir borrador."

    #  El bloque de recorrido se sustituye ANTES que el resto: lleva adentro
    #  sus propias variables ({{N_CHATS}}, {{HASTA_DIAS}}...), que se rellenan
    #  en la misma pasada que las del cuerpo del prompt.
    if estrategia == "barrido":
        recorrido = RECORRIDO_BARRIDO
    elif orden == "mas_viejos_primero":
        recorrido = RECORRIDO_VENTANA_ASCENDENTE
    else:
        recorrido = RECORRIDO_RECIENTES
    plantilla = (carpeta / "prompts" / "prompt-borradores.txt").read_text(encoding="utf-8")
    plantilla = plantilla.replace("{{COMO_RECORRER}}", recorrido)

    #  La venta cerrada (D41): post-venta a secas, post-venta con lo que el
    #  dueño quiere ofrecer, o nada. El bloque con oferta se arma acá para que
    #  el texto del dueño entre con la sangría del prompt.
    oferta = " ".join(post_venta_ofrecer.split())[:500]
    if not mensaje_post_compra:
        post_venta = POST_VENTA_APAGADO
    elif oferta:
        post_venta = POST_VENTA_CON_OFERTA.replace(
            "{{POST_VENTA_OFERTA}}", _lista([oferta], sangria=30)
        )
    else:
        post_venta = POST_VENTA_ACTIVO

    prompt = _sustituir(
        plantilla,
        {
            "N_CHATS": str(max(1, min(int(n_chats), MAX_POR_TANDA))),
            #  Nunca menos que la tanda: un techo de visitas más chico que
            #  `n_chats` sería pedir 8 borradores y prohibir abrir 8 chats.
            "MAX_VISITAS": str(max(max(1, min(int(n_chats), MAX_POR_TANDA)), int(max_visitas))),
            "RUN_ID": run_id[:64],
            "DEVICE_ID": device_id,
            "ANTIGUEDAD_MIN": str(minimo),
            "ANTIGUEDAD_MAX": str(maximo),
            "HASTA_DIAS": str(max(0, int(barrido_hasta_dias))),
            #  El cursor de la ventana nunca pasa del máximo: si el dueño bajó
            #  la ventana después de la última tanda, manda la ventana.
            "VENTANA_HASTA_DIAS": str(max(minimo, min(int(ventana_hasta_dias), maximo))),
            "YA_VISTOS": _lista(ya_vistos, tope=MAX_YA_VISTOS_EN_LISTA),
            "NO_ESCRIBIR": _lista(no_escribir, tope=MAX_NO_ESCRIBIR_EN_LISTA),
            "NO_ESCRIBIR_NUMEROS": _lista(no_escribir_numeros, tope=MAX_NO_ESCRIBIR_EN_LISTA),
            "RESTRICCION_DESTINOS": restriccion,
            "CONTEXTO_EMPRESA": contexto_empresa.strip() or "(el dueño no dejó indicaciones)",
            "LARGO_MAXIMO": str(max(50, int(largo_maximo))),
            "FRASES_PROHIBIDAS": _lista(frases_prohibidas),
            "PALABRAS_VETO": _lista(palabras_veto, sangria=24),
            "POST_VENTA": post_venta,
        },
    )

    invocacion = await invocador(
        prompt,
        claude_bin=claude_bin,
        carpeta=carpeta,
        con_navegador=True,
        timeout=TIMEOUT_BORRADORES,
    )
    if not invocacion.ok:
        return _desde_invocacion(invocacion)

    return _interpretar(invocacion, run_id=run_id)


def _sustituir(texto: str, variables: dict[str, str]) -> str:
    """`rellenar`, pero sobre un texto ya leído.

    El prompt del pase único se arma en dos pasos —primero el bloque de
    recorrido, después las variables— porque ese bloque trae variables adentro.
    Una sola pasada, igual que `rellenar`: un valor que contenga `{{OTRA_COSA}}`
    no se vuelve a expandir.
    """
    for nombre, valor in variables.items():
        texto = texto.replace("{{" + nombre + "}}", valor)
    return texto


def _lista(nombres: list[str] | None, *, tope: int = MAX_NOMBRES_EN_LISTA, sangria: int = 2) -> str:
    limpios = [str(n).strip() for n in (nombres or []) if str(n).strip()][:tope]
    margen = " " * sangria
    return "\n".join(f"{margen}- {nombre}" for nombre in limpios) or f"{margen}(ninguno)"


def _desde_invocacion(invocacion: Invocacion) -> Resultado:
    return Resultado(
        False,
        invocacion.codigo or "ERROR_INESPERADO",
        invocacion.detalle,
        raw=invocacion.raw,
        stderr=invocacion.stderr,
        costo_usd=invocacion.costo_usd,
    )


def _interpretar(invocacion: Invocacion, *, run_id: str) -> Resultado:
    datos = invocacion.datos or {}
    comunes = {
        "raw": invocacion.raw,
        "stderr": invocacion.stderr,
        "costo_usd": invocacion.costo_usd,
    }

    devuelto = datos.get("run_id")
    if devuelto is not None and str(devuelto) != run_id:
        log.error("borradores_run_id_ajeno", esperado=run_id, recibido=str(devuelto)[:64])
        return Resultado(
            False,
            "ERROR_INESPERADO",
            {
                "motivo": "la respuesta no es de esta corrida",
                "esperado": run_id,
                "recibido": str(devuelto)[:64],
            },
            **comunes,
        )

    estado = datos.get("status")
    if estado == "error":
        motivo = str(datos.get("motivo", "otro"))
        codigo = MOTIVOS_DE_ERROR.get(motivo, "ERROR_INESPERADO")
        log.warning("borradores_reporto_error", motivo=motivo, codigo=codigo)
        return Resultado(
            False,
            codigo,
            {
                "motivo": QUE_SIGNIFICA.get(motivo, motivo),
                "codigo_del_prompt": motivo,
                "detalle": str(datos.get("detalle", ""))[:500],
                #  Lo que se alcanzó a visitar antes del error viaja igual: son
                #  borradores que YA están en los chats y el backend los tiene
                #  que registrar aunque la tanda haya muerto a la mitad.
                "chats": _revisar_todos(datos.get("chats"))[0],
            },
            **comunes,
        )

    if estado != "ok":
        return Resultado(
            False, "ERROR_INESPERADO", {"motivo": f"status inesperado: {estado!r}"}, **comunes
        )

    if not isinstance(datos.get("chats"), list):
        # ⚠️ Un "ok" sin lista NO es una tanda vacía: es una respuesta rota.
        # Dejarlo pasar haría que el backend lo lea como "no queda nada",
        # termine la corrida en verde con cero borradores, y nadie se entere.
        return Resultado(
            False,
            "ERROR_INESPERADO",
            {"motivo": "la respuesta dice ok pero no trae la lista de chats"},
            **comunes,
        )
    buenos, descartados = _revisar_todos(datos.get("chats"))

    if descartados:
        # Contados y nombrados. Un chat que se cae en silencio puede ser un
        # borrador que SÍ quedó en WhatsApp y que el panel nunca va a mostrar.
        log.warning(
            "borradores_chats_descartados", cuantos=len(descartados), motivos=descartados[:5]
        )

    dejados = sum(1 for c in buenos if c["borrador_dejado"])
    log.info("borradores_ok", visitados=len(buenos), dejados=dejados)
    return Resultado(
        True,
        detalle={
            "chats": buenos,
            "visitados": len(buenos),
            "dejados": dejados,
            "salteados": len(buenos) - dejados,
            "descartados": descartados,
            #  Sólo `True` cuando ya no quedan chats dentro de la ventana. Lo
            #  dice el modelo, no lo deduce nadie contando: una tanda corta por
            #  tiempo no es lo mismo que una ventana agotada.
            "fin_de_ventana": bool(datos.get("fin_de_ventana")),
            #  Por qué devolvió menos (D44). Se normaliza al vocabulario: un
            #  valor inventado no se pierde, se vuelve "otro".
            "corte": _corte(datos.get("corte"), fin_de_ventana=bool(datos.get("fin_de_ventana"))),
        },
        **comunes,
    )


def _corte(crudo: Any, *, fin_de_ventana: bool) -> str:
    """El motivo del freno, dentro del vocabulario conocido.

    Si el modelo no lo dijo pero marcó `fin_de_ventana`, es eso: son el mismo
    hecho contado dos veces, y el campo nuevo no puede contradecir al viejo.
    """
    valor = str(crudo or "").strip()
    if valor in CORTES:
        return valor
    return "fin_de_ventana" if fin_de_ventana else "otro"


#  Cuántas entradas del reporte se aceptan. Mucho más que la tanda a propósito:
#  además de los dejados vienen los visitados-y-salteados (campo ocupado, sin
#  tema), y truncar acá podría tirar un borrador que SÍ quedó en WhatsApp.
MAX_ENTRADAS_DEL_REPORTE = 60


def _revisar_todos(crudos: Any) -> tuple[list[dict[str, Any]], list[str]]:
    buenos: list[dict[str, Any]] = []
    descartados: list[str] = []
    if not isinstance(crudos, list):
        return buenos, descartados
    for i, crudo in enumerate(crudos[:MAX_ENTRADAS_DEL_REPORTE]):
        limpio, problema = _revisar_chat(crudo)
        if limpio is None:
            descartados.append(f"#{i}: {problema}")
            continue
        buenos.append(limpio)
    return buenos, descartados


def _revisar_chat(crudo: Any) -> tuple[dict[str, Any] | None, str]:
    """Un chat visitado, o el motivo por el que su reporte no sirve."""
    if not isinstance(crudo, dict):
        return None, f"se esperaba un objeto y vino {type(crudo).__name__}"

    nombre = str(crudo.get("contacto_nombre") or "").strip()
    if not nombre:
        return None, "sin contacto_nombre"

    quien = QUIEN_HABLO.get(str(crudo.get("ultimo_lo_mando") or "").strip().lower())
    if quien is None:
        return None, f"{nombre!r}: ultimo_lo_mando no es 'contacto' ni 'yo'"

    try:
        dias = int(crudo.get("antiguedad_dias"))
    except (TypeError, ValueError):
        return None, f"{nombre!r}: antiguedad_dias no es un entero"
    if dias < 0:
        return None, f"{nombre!r}: antiguedad_dias negativa"

    dejado = bool(crudo.get("borrador_dejado"))
    texto = str(crudo.get("texto_borrador") or "").strip()
    crudo_motivo = str(crudo.get("motivo") or "").strip()
    if dejado and not texto:
        # Contradictorio: dice que dejó y no dice qué. No se puede registrar un
        # texto que no se conoce — se degrada a "no dejado" con motivo propio,
        # y una persona revisa ese chat.
        dejado, texto, motivo = False, "", "reporte_sin_texto"
    elif dejado:
        #  Un post-venta (D41) es un borrador dejado en una venta cerrada: el
        #  motivo viaja igual, porque es lo que veta al contacto después.
        motivo = "ya_compro" if crudo_motivo == "ya_compro" else None
    else:
        motivo = crudo_motivo if crudo_motivo in MOTIVOS_DE_SALTEO else "otro"
        texto = ""

    #  El anclaje (D40): `tema` dice de qué es el borrador y `cita` es el
    #  fragmento literal del chat en el que se apoya. En nivel B van vacíos y
    #  está bien; un tema sin cita no se corrige acá — el backend lo señala.
    tema = str(crudo.get("tema") or "").strip()[:60] if dejado else ""
    cita = str(crudo.get("cita") or "").strip()[:80] if dejado else ""

    resumen = str(crudo.get("ultimo_mensaje_resumen") or "").strip()
    if dejado and not resumen:
        return None, f"{nombre!r}: dejó borrador pero no dice de qué se hablaba"

    # `null` es una respuesta válida y esperada: el prompt pide no deducirlo.
    telefono = crudo.get("contacto_telefono")
    telefono = str(telefono).strip() if telefono else None

    return {
        "contacto_nombre": nombre[:120],
        "contacto_telefono": telefono,
        "ultimo_mensaje_resumen": resumen[:400],
        "quien_hablo_ultimo": quien,
        "antiguedad_dias": min(dias, 3650),
        "borrador_dejado": dejado,
        "texto_borrador": texto[:1000],
        "tema": tema or None,
        "cita": cita or None,
        "motivo": motivo,
    }, ""
