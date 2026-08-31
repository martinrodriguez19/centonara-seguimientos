"""El motor de envío. Es el código más peligroso del proyecto.

Escribe en el WhatsApp de una persona, en nombre de otra, a un cliente real.
Todo lo demás del sistema se puede equivocar y como mucho no pasa nada; acá un
error llega a alguien.

**La secuencia y su orden no se negocian.** Cada paso está antes del siguiente
por un motivo, y moverlos convierte una garantía en una intención:

    0. El destino está en la lista permitida        (R4)
    1. Abrir WhatsApp Web — navegar PRIMERO, preguntar por la sesión después
    2. Abrir el chat — en cascada, del escalón de siempre al más caro
    3. No es un grupo
    4. LEER el header del chat abierto
    5. RESOLVER el número a E.164
    6. COMPARAR — si no coincide, abortar            (R1) ⚠️
    7. El campo de escritura está vacío
    8. Escribir el texto EXACTO
    9. En modo prueba: dejar el borrador y salir SIN enviar (D30)
   10. Enviar
   11. Confirmar que apareció en el hilo

**Falla cerrado, siempre** (R2). Si algo no se puede leer, no se puede resolver
o no coincide: se aborta y se reporta. Nunca se escribe "por las dudas". Un
`except: pass` en este archivo es un incidente, no un atajo.

Escribí esto pensando en que alguien lo va a leer buscando el error que hace que
un mensaje comercial llegue al chat equivocado. Porque alguien lo va a leer así.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from agente.adaptadores.cascada import en_cascada
from agente.adaptadores.pagina import ErrorDeSelector, Pagina, PaginaNoCargo
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# Cuántas veces pasó cada contacto por este proceso. Es el gate del escalón
# caro (A8, la URL directa que recarga la página): los baratos corren desde la
# primera pasada; el caro recién a partir de la segunda. Vive en memoria a
# propósito — el job no trae el número de intento, y los tres reintentos del
# backend vuelven al mismo proceso, que es lo único que hace falta contar.
_pasadas_por_contacto: dict[str, int] = {}


@dataclass(frozen=True)
class Resultado:
    ok: bool
    codigo: str | None = None
    detalle: dict[str, Any] = field(default_factory=dict)
    #  Qué se escribió. En modo borradores es la evidencia de lo que quedó.
    texto_escrito: str = ""
    #  True cuando el texto quedó como borrador de WhatsApp, sin enviarse (D30).
    borrador: bool = False

    def a_reporte(self) -> dict[str, Any]:
        """Lo que se le manda al backend.

        `borrador` viaja siempre: sin él, el backend marcaría un borrador
        dejado como ENVIADO — lo auditaría como enviado, lo contaría en el tope
        diario y no se podría enviar de verdad nunca.
        """
        return {
            "ok": self.ok,
            "codigo": self.codigo,
            "detalle": self.detalle,
            "raw": self.texto_escrito,
            "borrador": self.borrador,
        }


def _normalizar_para_comparar(numero: str) -> str:
    """Sólo los dígitos.

    El backend manda E.164 (`+5491144405036`) y WhatsApp puede mostrar
    `+54 9 11 4440-5036`. Comparar los dígitos evita que un espacio decida si un
    mensaje sale o no — y **no afloja la comparación**: dos teléfonos distintos
    siguen teniendo dígitos distintos.
    """
    return "".join(c for c in numero if c.isdigit())


async def enviar(
    pagina: Pagina,
    *,
    contacto_id: str,
    contacto_nombre: str,
    texto: str,
    modo: str = "prueba",
    destinos_permitidos: list[str] | None = None,
) -> Resultado:
    """Manda un mensaje, o aborta explicando por qué no."""
    # ---- 0. ¿A esta persona le podemos escribir? (R4) -----------------------
    #
    # El backend ya lo verificó al encolar. Se verifica otra vez acá, y no por
    # desconfianza: entre que el job se encoló y que el agente lo tomó pudieron
    # pasar minutos, y la lista pudo cambiar en el medio.
    if not _destino_permitido(destinos_permitidos, contacto_id):
        return Resultado(False, "DESTINO_NO_PERMITIDO", {"contacto_id": contacto_id})

    # El registro de las cascadas: qué escalón resolvió cada cosa. Viaja en el
    # `detalle` del reporte —en éxito y en fallo— y queda persistido en el
    # documento del job: es lo que después permite ver en producción cuál
    # escalón funcionó de verdad, y promoverlo a primera opción.
    cascadas: dict[str, Any] = {}
    pasada = _pasadas_por_contacto[contacto_id] = _pasadas_por_contacto.get(contacto_id, 0) + 1

    try:
        resultado = await _secuencia(
            pagina,
            contacto_id=contacto_id,
            contacto_nombre=contacto_nombre,
            texto=texto,
            modo=modo,
            cascadas=cascadas,
            pasada=pasada,
        )
    except PaginaNoCargo as error:
        # La página no terminó de cargar: red lenta, Chrome recién abierto.
        # Transitorio — se reporta como TIMEOUT (reintentable, con su propio
        # tope), no como SELECTOR_ROTO, que frenaría la corrida entera.
        log.warning("pagina_no_cargo", error=str(error))
        resultado = Resultado(False, "TIMEOUT", {"motivo": str(error)})
    except ErrorDeSelector as error:
        # El DOM cambió. No es este envío el que falló: van a fallar todos.
        log.error("selector_roto", error=str(error))
        resultado = Resultado(False, "SELECTOR_ROTO", {"error": str(error)})
    except Exception as error:
        # Nada se traga en silencio, y nada sigue de largo. Lo que no sabemos
        # manejar termina el envío sin escribir.
        log.error("envio_reventó", error=str(error), tipo=type(error).__name__)
        resultado = Resultado(
            False,
            "ERROR_INESPERADO",
            {"excepcion": type(error).__name__, "mensaje": str(error)[:500]},
        )

    if cascadas:
        resultado = replace(resultado, detalle={**resultado.detalle, "cascadas": cascadas})
    return resultado


def _destino_permitido(permitidos: list[str] | None, contacto_id: str) -> bool:
    """Lista vacía o ausente significa **a nadie**, igual que en el backend."""
    lista = permitidos or []
    return "*" in lista or contacto_id in lista


async def _secuencia(
    pagina: Pagina,
    *,
    contacto_id: str,
    contacto_nombre: str,
    texto: str,
    modo: str,
    cascadas: dict[str, Any],
    pasada: int = 1,
) -> Resultado:
    # ---- 1. WhatsApp Web abierto y con sesión -------------------------------
    #
    # ⚠️ NAVEGAR PRIMERO, preguntar después. La página del navegador dedicado
    # nace en about:blank, y ahí no hay ni QR ni lista de chats: preguntar por
    # la sesión antes de abrir devolvía SESION_CAIDA con la sesión sana — y como
    # se abortaba sin navegar, los tres reintentos morían igual (27/08).
    await pagina.abrir_whatsapp()
    if not await pagina.sesion_iniciada():
        return Resultado(False, "SESION_CAIDA", {"detalle": "pide escanear el código"})

    # ---- 2. El chat, en cascada (A) -----------------------------------------
    #
    # Se busca por NOMBRE, no por número (D34): los contactos reales están
    # agendados por nombre y buscar el E.164 devolvía cero resultados. Qué chat
    # se abre nunca fue la garantía de identidad — la garantía es el paso 6.
    #
    # Los dos primeros escalones son literalmente lo que ya se hacía; los demás
    # (`CHAT_NO_ABRE` del 28/08) corren sólo cuando el anterior devolvió «no
    # pude», del más barato al más caro. Ninguno saltea los pasos 3 a 7:
    # una cascada que insiste más en abrir chats sube el riesgo de abrir el
    # equivocado, y la comparación de identidad es justo lo que lo contiene.
    termino = contacto_nombre.strip() or contacto_id
    #  El motivo de cada escalón que dijo «no pude», a mano para el reporte:
    #  "la búsqueda no trajo nada" y "hubo filas pero ninguna abrió" son fallas
    #  distintas, y sin esto diagnosticarlas exige ir a los logs de la Mac.
    motivos: dict[str, str] = {}

    def anotando(nombre: str, buscar):
        async def correr():
            abrio = await buscar()
            if not abrio and (motivo := getattr(pagina, "motivo_no_abrio", None)):
                motivos[nombre] = motivo
            return abrio

        return correr

    estrategias = [("A1_nombre", lambda: pagina.buscar_contacto(termino))]
    if termino != contacto_id:
        #  El nombre no trajo nada (renombrado, emoji): el número, por si acaso.
        estrategias.append(("A2_numero", lambda: pagina.buscar_contacto(contacto_id)))
    estrategias += [
        ("A3_fila_verificada", lambda: pagina.buscar_verificado(termino, contacto_id)),
        ("A4_sin_filtros", lambda: pagina.buscar_limpiando_filtros(termino)),
        ("A5_tipeo_alternativo", lambda: pagina.buscar_tipeando_distinto(termino)),
        ("A6_teclado", lambda: pagina.buscar_con_teclado(termino)),
        ("A7_otra_ancla", lambda: pagina.buscar_con_otra_ancla(termino)),
    ]
    if pasada >= 2:
        #  El escalón CARO: recarga la página. Se reserva para la segunda
        #  pasada del contacto — la primera agota los baratos, que cuestan
        #  segundos; si el backend reintenta, ya vale la pena pagar el reload.
        estrategias.append(("A8_url_directa", lambda: pagina.abrir_por_url(contacto_id)))

    abierto = await en_cascada(
        "abrir_chat",
        [(nombre, anotando(nombre, buscar)) for nombre, buscar in estrategias],
        registro=cascadas,
    )
    if not abierto:
        detalle: dict[str, Any] = {"contacto_id": contacto_id, "buscado": termino}
        #  El titular es el de la ruta principal (A1), que es la que se venía
        #  reportando; el resto queda al lado, escalón por escalón.
        if motivos:
            detalle["motivo"] = next(iter(motivos.values()))
            detalle["motivos"] = motivos
        return Resultado(False, "CHAT_NO_ABRE", detalle)

    # ---- 3. Un grupo nunca ---------------------------------------------------
    #
    # Va antes de leer el número porque un grupo no tiene uno, y porque el error
    # que se quiere evitar es distinto: mandarle un seguimiento comercial a
    # veinte personas a la vez.
    if await pagina.es_grupo():
        return Resultado(False, "CONTACTO_NO_COINCIDE", {"motivo": "es un grupo"})

    # ---- 4. El header --------------------------------------------------------
    header = await pagina.leer_header()
    if header is None:
        return Resultado(False, "NUMERO_NO_RESOLUBLE", {"motivo": "no se pudo leer el header"})

    # ---- 5. El número --------------------------------------------------------
    encontrado = await pagina.resolver_numero()
    #  La cascada B corre adentro de `resolver_numero`; qué escalón leyó el
    #  número viaja en el reporte igual que los de apertura.
    if escalon := getattr(pagina, "ultimo_escalon_numero", None):
        cascadas["leer_numero"] = {"gano": escalon}
    if encontrado is None:
        return Resultado(
            False,
            "NUMERO_NO_RESOLUBLE",
            {"motivo": "el chat no muestra un teléfono", "header": header},
        )

    # ---- 6. ⚠️ LA COMPARACIÓN ------------------------------------------------
    #
    # Es el paso que impide el peor error posible del sistema. No hay atajo, no
    # hay "ya lo verificamos antes", y no hay caso en que se escriba igual.
    esperado = _normalizar_para_comparar(contacto_id)
    real = _normalizar_para_comparar(encontrado)
    if not esperado or esperado != real:
        log.error(
            "contacto_no_coincide",
            esperado=contacto_id,
            encontrado=encontrado,
            header=header,
        )
        return Resultado(
            False,
            "CONTACTO_NO_COINCIDE",
            {"esperado": contacto_id, "encontrado": encontrado, "header": header},
        )

    # ---- 7. El campo está vacío ---------------------------------------------
    #
    # Si hay algo escrito, el vendedor está usando ese chat en este momento.
    # Escribir encima le pisaría lo que estaba redactando.
    if await pagina.campo_tiene_texto():
        return Resultado(False, "CAMPO_NO_VACIO", {"contacto_id": contacto_id})

    # ---- 8. Escribir, literal ------------------------------------------------
    await pagina.escribir(texto)

    # ---- 9. Modo prueba: dejar el borrador y salir SIN enviar (D30) ----------
    #
    # El texto queda escrito en el campo y se cierra el chat: WhatsApp Web lo
    # guarda como borrador de esa conversación, y el vendedor lo manda con un
    # click. No es una trampa — es el producto: el vendedor sabe que el sistema
    # deja borradores, y el circuito es "el sistema deja, el vendedor manda".
    if modo != "real":
        await pagina.cerrar_chat()
        log.info("borrador_dejado", contacto=contacto_nombre, largo=len(texto))
        return Resultado(True, texto_escrito=texto, borrador=True)

    # ---- 10. Enviar ----------------------------------------------------------
    await pagina.apretar_enviar()

    # ---- 11. Confirmar -------------------------------------------------------
    #
    # "Apreté enviar" y "el mensaje salió" no son lo mismo. Sin confirmación no
    # se da por enviado: se reporta que no sabemos, que es la verdad.
    if not await pagina.confirmar_en_hilo(texto):
        log.warning("envio_sin_confirmar", contacto=contacto_nombre)
        return Resultado(
            False,
            "SIN_CONFIRMAR",
            {"contacto_id": contacto_id, "advertencia": "puede haber salido"},
            texto_escrito=texto,
        )

    log.info("mensaje_enviado", contacto=contacto_nombre, largo=len(texto))
    return Resultado(True, texto_escrito=texto)
