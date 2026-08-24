"""WhatsApp Web de verdad, sobre Playwright.

Implementa el protocolo `Pagina` que consume `jobs/enviar.py`. Todo lo que
decide **si** un mensaje sale vive allá; acá sólo vive **cómo** se lee y se
toca la página. La separación importa: el motor está probado contra una página
falsa con los casos que no se pueden montar en un WhatsApp real —dos contactos
con el mismo nombre, un grupo, un número ilegible— y ese trabajo no se repite
acá.

Tres reglas que este archivo no cruza:

1. **Ningún selector literal.** Todos viven en `selectores.py`. Si acá aparece
   un `div[...]`, es un hallazgo.
2. **Cuando algo no se puede leer, se devuelve `None` o se lanza.** Nunca un
   valor aproximado. Lo que sigue río abajo es una comparación de identidad, y
   comparar contra un dato inventado da falsos positivos — que en este sistema
   significa escribirle a otra persona.
3. **`ErrorDeSelector` se distingue de "no está".** Que un chat no exista es un
   dato del mundo y devuelve `False`. Que el campo de escritura no aparezca es
   que WhatsApp cambió, y eso frena la corrida entera.

---

## ⚠️ Los selectores no están verificados contra WhatsApp Web

Ver la cabecera de `selectores.py`. La lógica de este adaptador sí está probada,
contra una página de prueba con la misma estructura. Hasta que alguien corra
`verificar_selectores()` contra una sesión real, este módulo puede abortar todo
con `SELECTOR_ROTO` — que es el comportamiento correcto, y también significa que
no manda nada.

## Cómo se obtiene la página

No lo decide este archivo: recibe una `Page` ya creada. La discusión de si
conviene CDP sobre el Chrome del vendedor o un perfil dedicado —F4.2, que hay
que resolver **con evidencia** y midiendo en macOS— vive en `conexion.py`, y por
eso no contamina la parte que sí se puede terminar.
"""

from __future__ import annotations

import re

from agente.adaptadores import selectores
from agente.adaptadores.pagina import ErrorDeSelector
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# Cuánto se espera a que aparezca algo antes de decir que el DOM cambió.
# Generoso: WhatsApp Web tarda, y un timeout corto convierte una red lenta en un
# `SELECTOR_ROTO` que frena la corrida sin motivo.
ESPERA_MS = 15_000
ESPERA_CORTA_MS = 3_000

# ⚠️ Seleccionar todo NO es `Control+A` en macOS: es `Cmd+A`. Y macOS es donde
# esto va a correr.
#
# Lo agarró el CI, que prueba el agente en los tres sistemas. Las consecuencias
# de equivocarse acá no son cosméticas:
#
#   - El buscador no se limpia, así que la búsqueda anterior sigue puesta y se
#     abre el chat del contacto anterior. En una corrida eso es el segundo
#     mensaje entrando al chat del primero.
#   - `limpiar_campo()` no borra nada, así que el modo prueba **deja el texto
#     escrito en el chat del vendedor**: abre la conversación, ve un mensaje
#     redactado, y lo manda sin saber de dónde salió. Es exactamente la trampa
#     que el modo prueba existe para no dejar.
#
# `ControlOrMeta` lo resuelve Playwright según el sistema.
SELECCIONAR_TODO = "ControlOrMeta+A"


class PaginaWhatsApp:
    """El protocolo `Pagina`, contra una `Page` de Playwright."""

    def __init__(self, page, *, espera_ms: int = ESPERA_MS) -> None:
        self._page = page
        self._espera = espera_ms

    # -- Sesión ---------------------------------------------------------------

    async def abrir_whatsapp(self) -> None:
        """Deja la lista de chats a la vista.

        **Si ya está a la vista, no navega.** Una corrida manda varios mensajes
        seguidos y esto se llama antes de cada uno: recargar WhatsApp Web cada
        vez tarda, tira abajo el estado de la interfaz, y multiplica las chances
        de agarrar la página a medio cargar.

        La condición es la lista de chats presente y no la URL: es lo que de
        verdad importa, y no se rompe si WhatsApp cambia de ruta.
        """
        if await self._page.query_selector(selectores.LISTA_DE_CHATS.css) is None:
            await self._page.goto(selectores.URL, wait_until="domcontentloaded")

        try:
            await self._page.wait_for_selector(
                selectores.LISTA_DE_CHATS.css, timeout=self._espera, state="attached"
            )
        except Exception as error:
            raise ErrorDeSelector(f"no apareció {selectores.LISTA_DE_CHATS.que_busca}") from error

    async def sesion_iniciada(self) -> bool:
        """`False` si la página pide escanear el código.

        Se pregunta por el QR y no por la lista de chats: el QR aparece rápido y
        su ausencia, con la lista presente, es la señal de que hay sesión.
        """
        if await self._page.query_selector(selectores.QR.css) is not None:
            return False
        return await self._page.query_selector(selectores.LISTA_DE_CHATS.css) is not None

    # -- Abrir el chat ---------------------------------------------------------

    async def buscar_contacto(self, identificador: str) -> bool:
        """Busca y abre el chat. `False` si no aparece ninguno.

        `False` NO es un error de selector: que un contacto no esté en la lista
        es un dato del mundo, y el motor lo reporta como `CHAT_NO_ABRE`.
        """
        buscador = await self._exigir(selectores.BUSCADOR)

        #  Se limpia antes de escribir: si quedó una búsqueda anterior, los
        #  resultados serían de otro contacto y se abriría el chat equivocado.
        await buscador.click()
        await self._page.keyboard.press(SELECCIONAR_TODO)
        await self._page.keyboard.press("Delete")
        await buscador.type(identificador, delay=20)

        try:
            await self._page.wait_for_selector(
                selectores.RESULTADO_DE_BUSQUEDA.css, timeout=ESPERA_CORTA_MS
            )
        except Exception:
            log.info("contacto_sin_resultados", identificador=identificador)
            return False

        resultados = await self._page.query_selector_all(selectores.RESULTADO_DE_BUSQUEDA.css)
        if not resultados:
            return False

        await resultados[0].click()

        try:
            await self._page.wait_for_selector(
                selectores.HEADER.css, timeout=self._espera, state="attached"
            )
        except Exception as error:
            raise ErrorDeSelector(f"no apareció {selectores.HEADER.que_busca}") from error
        return True

    # -- Leer quién es --------------------------------------------------------

    async def leer_header(self) -> str | None:
        """Lo que dice el encabezado. `None` si no se puede leer.

        `None` no es "está vacío": es "no sé qué dice", y con eso el motor no
        escribe nada.
        """
        elemento = await self._page.query_selector(selectores.TITULO_DEL_HEADER.css)
        if elemento is None:
            return None
        titulo = await elemento.get_attribute("title")
        texto = titulo or (await elemento.inner_text())
        limpio = (texto or "").strip()
        return limpio or None

    async def resolver_numero(self) -> str | None:
        """El teléfono del chat abierto, o `None`.

        Dos caminos, en orden:

        1. El header ya muestra un número — pasa cuando el contacto no está
           agendado.
        2. Hay que abrir el panel del contacto y leerlo de ahí.

        ⚠️ Si ninguno da un número reconocible, devuelve `None` y no intenta
        deducirlo del nombre ni de la búsqueda. Lo que sigue es la comparación
        de identidad (R1): un número aproximado acá es un mensaje a otra
        persona.
        """
        header = await self.leer_header()
        if header and (numero := _numero_en(header)):
            return numero

        #  Abrir el panel es la única forma de ver el teléfono de un contacto
        #  agendado. Es de sólo lectura: no toca la conversación.
        try:
            titulo = await self._page.query_selector(selectores.TITULO_DEL_HEADER.css)
            if titulo is None:
                return None
            await titulo.click()
            await self._page.wait_for_selector(
                selectores.PANEL_DE_CONTACTO.css, timeout=ESPERA_CORTA_MS
            )
        except Exception:
            log.info("panel_de_contacto_no_abrio")
            return None

        for elemento in await self._page.query_selector_all(selectores.TELEFONO_EN_EL_PANEL.css):
            texto = (await elemento.inner_text() or "").strip()
            if numero := _numero_en(texto):
                return numero

        return None

    async def es_grupo(self) -> bool:
        """Un grupo nunca recibe un seguimiento comercial."""
        return await self._page.query_selector(selectores.MARCA_DE_GRUPO.css) is not None

    # -- Escribir --------------------------------------------------------------

    async def campo_tiene_texto(self) -> bool:
        """¿Hay algo escrito? Si lo hay, el vendedor está usando ese chat."""
        campo = await self._exigir(selectores.CAMPO_DE_TEXTO)
        return bool((await campo.inner_text() or "").strip())

    async def escribir(self, texto: str) -> None:
        """Pone el texto en el campo. **Literal.**

        `type` y no `fill`: el campo es un `contenteditable` y WhatsApp escucha
        los eventos de teclado para habilitar el botón de enviar. Un `fill`
        cambia el DOM sin que la aplicación se entere, y el botón queda muerto.
        """
        campo = await self._exigir(selectores.CAMPO_DE_TEXTO)
        await campo.click()
        await campo.type(texto, delay=10)

    async def limpiar_campo(self) -> None:
        """Borra lo escrito. Se usa al abortar en modo prueba.

        Dejar el texto sería dejar una trampa: el vendedor abre el chat, ve algo
        redactado y lo manda sin saber de dónde salió.
        """
        campo = await self._exigir(selectores.CAMPO_DE_TEXTO)
        await campo.click()
        await self._page.keyboard.press(SELECCIONAR_TODO)
        await self._page.keyboard.press("Delete")

    async def apretar_enviar(self) -> None:
        """El único método de este archivo que hace que un mensaje salga."""
        boton = await self._exigir(selectores.BOTON_ENVIAR)
        await boton.click()

    async def confirmar_en_hilo(self, texto: str, *, timeout_s: float = 15) -> bool:
        """¿Apareció en la conversación?

        `False` no es "no salió": es "no pude verificar". El motor las trata
        distinto, y por eso acá no se lanza ni se asume.
        """
        try:
            await self._page.wait_for_function(
                """([css, esperado]) => {
                    const nodos = document.querySelectorAll(css);
                    return Array.from(nodos).some(n => (n.innerText || '').includes(esperado));
                }""",
                arg=[selectores.MENSAJES_SALIENTES.css, texto],
                timeout=int(timeout_s * 1000),
            )
        except Exception:
            log.warning("no_se_pudo_confirmar_en_el_hilo", largo=len(texto))
            return False
        return True

    # -- Interno ---------------------------------------------------------------

    async def _exigir(self, selector: selectores.Selector):
        """El elemento, o `ErrorDeSelector`.

        Se usa para lo estructural: si el campo de escritura no está, WhatsApp
        cambió y los envíos siguientes van a fallar igual.
        """
        try:
            elemento = await self._page.wait_for_selector(
                selector.css, timeout=self._espera, state="attached"
            )
        except Exception as error:
            raise ErrorDeSelector(f"no apareció {selector.que_busca}: {selector.css}") from error
        if elemento is None:
            raise ErrorDeSelector(f"no apareció {selector.que_busca}: {selector.css}")
        return elemento


# ---------------------------------------------------------------------------
# Leer un número de un texto
# ---------------------------------------------------------------------------

# Un teléfono como lo muestra WhatsApp: `+54 9 11 4440-5036`. Se pide el `+`
# porque sin él cualquier número de una conversación —un precio, una cantidad—
# pasaría por teléfono.
_TELEFONO = re.compile(r"\+\d[\d\s\-().]{6,}\d")


def _numero_en(texto: str) -> str | None:
    """El teléfono que haya en el texto, o `None`.

    Devuelve el número **tal como se ve**, sin normalizar: quien compara es
    `jobs/enviar.py`, que ya sabe que hay que mirar sólo los dígitos.

    Con dos números en el mismo texto devuelve `None`, no el primero. Si hay
    ambigüedad sobre a quién le estaríamos escribiendo, la respuesta correcta es
    no saber (R2).
    """
    encontrados = _TELEFONO.findall(texto or "")
    if len(encontrados) != 1:
        return None
    return encontrados[0].strip()


async def verificar_selectores(pagina: PaginaWhatsApp) -> selectores.Revision:
    """Corre antes de cada corrida. Ver `selectores.verificar`."""
    return await selectores.verificar(pagina._page)
