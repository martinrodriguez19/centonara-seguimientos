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
# La búsqueda de un contacto y la confirmación de que el chat abrió esperan
# más que una lectura suelta: 3 s contra un WhatsApp Web con red lenta producía
# `CHAT_NO_ABRE` espurios — chats que existían y no llegaban a dibujarse.
ESPERA_BUSQUEDA_MS = 8_000

# ⚠️ Seleccionar todo NO es `Control+A` en macOS: es `Cmd+A`. Y macOS es donde
# esto va a correr.
#
# Lo agarró el CI, que prueba el agente en los tres sistemas. Las consecuencias
# de equivocarse acá no son cosméticas:
#
#   - El buscador no se limpia, así que la búsqueda anterior sigue puesta y se
#     abre el chat del contacto anterior. En una corrida eso es el segundo
#     mensaje entrando al chat del primero.
#   - `limpiar_campo()` no borra nada, así que un aborto que quiso dejar el
#     campo limpio lo deja escrito.
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

        `motivo_no_abrio` queda cargado cuando devuelve `False`, para que el
        reporte distinga "la búsqueda no trajo resultados" de "hubo filas pero
        ninguna abrió el chat que decía ser" — antes los dos eran el mismo
        `CHAT_NO_ABRE` genérico y diagnosticarlo exigía ir a los logs de la Mac.
        """
        self.motivo_no_abrio: str | None = None
        buscador = await self._exigir(selectores.BUSCADOR)

        #  Se limpia antes de escribir: si quedó una búsqueda anterior, los
        #  resultados serían de otro contacto y se abriría el chat equivocado.
        await buscador.click(timeout=self._espera)
        await self._page.keyboard.press(SELECCIONAR_TODO)
        await self._page.keyboard.press("Delete")
        await buscador.press_sequentially(identificador, delay=20)

        try:
            await self._page.wait_for_selector(
                selectores.RESULTADO_DE_BUSQUEDA.css, timeout=ESPERA_BUSQUEDA_MS
            )
        except Exception:
            log.info("contacto_sin_resultados", identificador=identificador)
            self.motivo_no_abrio = "sin_resultados"
            return False

        # ⚠️ Locators y no handles, y cada fila protegida. WhatsApp redibuja la
        # lista de resultados mientras se la mira: un handle agarrado hace medio
        # segundo puede estar "not attached to the DOM" al clickearlo — mató al
        # primer RESOLVER real, en el segundo contacto del lote. El locator se
        # re-resuelve en el momento del click, y si la fila igual desapareció,
        # se prueba la siguiente en vez de reventar el job entero.
        filas = self._page.locator(selectores.RESULTADO_DE_BUSQUEDA.css)
        cantidad = min(await filas.count(), 6)
        if cantidad == 0:
            self.motivo_no_abrio = "sin_resultados"
            return False

        # ⚠️ La primera fila no siempre es un chat: la lista nueva es una grilla
        # y las primeras filas pueden ser títulos de sección ("Chats",
        # "Contactos") que no abren nada — pasó en la primera verificación real.
        #
        # Y "apareció un encabezado" no alcanza como señal de que abrió: en el
        # segundo mensaje de una corrida ya hay un chat abierto de antes, y su
        # encabezado viejo haría pasar por buena a una fila muerta. La señal es
        # que el encabezado visible DIGA lo que decía la fila clickeada. Cuál
        # chat es, lo sigue decidiendo la comparación de identidad (R1).
        for i in range(cantidad):
            fila = filas.nth(i)
            try:
                texto_fila = ((await fila.inner_text(timeout=ESPERA_CORTA_MS)) or "").strip()
                if not texto_fila:
                    continue
                await fila.click(timeout=ESPERA_CORTA_MS)
            except Exception:
                #  La fila se redibujó o desapareció entre leerla y clickearla.
                continue
            try:
                await self._page.wait_for_function(
                    """([css, fila]) => {
                        const h = document.querySelector(css);
                        if (h === null || h.offsetParent === null) return false;
                        const lineas = (h.innerText || '')
                            .split('\\n').map(s => s.trim()).filter(Boolean);
                        return lineas.some(l => fila.includes(l));
                    }""",
                    arg=[selectores.HEADER.css, texto_fila],
                    timeout=ESPERA_BUSQUEDA_MS,
                )
                return True
            except Exception:
                continue

        # Ninguna fila abrió el chat que decía ser. Es lo mismo que "no está":
        # el motor lo reporta como CHAT_NO_ABRE y no escribe nada. Si lo que en
        # verdad pasa es que el DOM cambió, los selectores del chat abierto lo
        # van a decir con nombre propio en la próxima corrida que sí abra.
        log.info("resultados_sin_chat", filas=cantidad)
        self.motivo_no_abrio = "resultados_sin_chat"
        return False

    # -- Leer quién es --------------------------------------------------------

    async def leer_header(self) -> str | None:
        """Lo que dice el encabezado. `None` si no se puede leer.

        `None` no es "está vacío": es "no sé qué dice", y con eso el motor no
        escribe nada.
        """
        loc = self._page.locator(selectores.TITULO_DEL_HEADER.css).first
        try:
            if await loc.count() == 0:
                return None
            titulo = await loc.get_attribute("title", timeout=ESPERA_CORTA_MS)
            texto = titulo or (await loc.inner_text(timeout=ESPERA_CORTA_MS))
        except Exception:
            #  Se redibujó mientras se leía. "No sé qué dice" y no un valor viejo.
            return None
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
            titulo = self._page.locator(selectores.TITULO_DEL_HEADER.css).first
            if await titulo.count() == 0:
                return None
            await titulo.click(timeout=ESPERA_CORTA_MS)
            await self._page.wait_for_selector(
                selectores.PANEL_DE_CONTACTO.css, timeout=ESPERA_CORTA_MS
            )
        except Exception:
            log.info("panel_de_contacto_no_abrio")
            return None

        try:
            telefonos = self._page.locator(selectores.TELEFONO_EN_EL_PANEL.css)
            for i in range(min(await telefonos.count(), 40)):
                try:
                    texto = (await telefonos.nth(i).inner_text(timeout=1_000) or "").strip()
                except Exception:
                    #  Ese span se redibujó: se sigue con el próximo.
                    continue
                if numero := _numero_en(texto):
                    return numero
            return None
        finally:
            # ⚠️ El panel abierto TAPA el campo de texto y se come los clicks:
            # sin esto, el `escribir()` siguiente muere esperando un click que
            # nunca entra. Lo encontró la verificación en la primera Mac —
            # Playwright reintentando 30 segundos contra el drawer.
            await self._page.keyboard.press("Escape")

    async def es_grupo(self) -> bool:
        """Un grupo nunca recibe un seguimiento comercial."""
        return await self._page.query_selector(selectores.MARCA_DE_GRUPO.css) is not None

    # -- Escribir --------------------------------------------------------------

    async def campo_tiene_texto(self) -> bool:
        """¿Hay algo escrito? Si lo hay, el vendedor está usando ese chat."""
        campo = await self._exigir(selectores.CAMPO_DE_TEXTO)
        return bool((await campo.inner_text(timeout=self._espera) or "").strip())

    async def escribir(self, texto: str) -> None:
        """Pone el texto en el campo. **Literal.**

        Tecla por tecla y no `fill`: el campo es un `contenteditable` y WhatsApp
        escucha los eventos de teclado para habilitar el botón de enviar. Un
        `fill` cambia el DOM sin que la aplicación se entere, y el botón queda
        muerto.
        """
        campo = await self._exigir(selectores.CAMPO_DE_TEXTO)
        await campo.click(timeout=self._espera)
        await campo.press_sequentially(texto, delay=10)

    async def limpiar_campo(self) -> None:
        """Borra lo escrito, sin enviar."""
        campo = await self._exigir(selectores.CAMPO_DE_TEXTO)
        await campo.click(timeout=self._espera)
        await self._page.keyboard.press(SELECCIONAR_TODO)
        await self._page.keyboard.press("Delete")

    async def cerrar_chat(self) -> None:
        """Cierra el chat abierto: Escape vuelve a la lista de chats.

        Es el paso final del modo borradores (D30): al salir del chat, WhatsApp
        Web guarda lo escrito como borrador de esa conversación. El vendedor lo
        ve marcado en su lista y lo manda con un click.
        """
        await self._page.keyboard.press("Escape")

    async def apretar_enviar(self) -> None:
        """El único método de este archivo que hace que un mensaje salga."""
        boton = await self._exigir(selectores.BOTON_ENVIAR)
        await boton.click(timeout=self._espera)

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
        """Un locator ya presente, o `ErrorDeSelector`.

        Se usa para lo estructural: si el campo de escritura no está, WhatsApp
        cambió y los envíos siguientes van a fallar igual.

        Devuelve un **locator** y no un handle, a propósito: WhatsApp redibuja
        sus elementos sin avisar, y un handle agarrado hace un instante puede
        estar "not attached to the DOM" al usarlo. El locator se re-resuelve en
        cada acción.
        """
        loc = self._page.locator(selector.css).first
        try:
            await loc.wait_for(state="attached", timeout=self._espera)
        except Exception as error:
            raise ErrorDeSelector(f"no apareció {selector.que_busca}: {selector.css}") from error
        return loc


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
