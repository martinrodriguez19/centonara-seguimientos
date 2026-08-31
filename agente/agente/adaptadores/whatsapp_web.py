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
import unicodedata

from agente.adaptadores import selectores
from agente.adaptadores.pagina import ErrorDeSelector, PaginaNoCargo
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
# Cuánto tiene que quedarse quieta la lista de resultados para darla por
# filtrada, cuando ninguna fila matchea lo buscado (pasa al buscar por número:
# la fila muestra el nombre agendado). Sin esto, el primer wait se satisfacía
# con las filas VIEJAS de la lista de chats —el selector matchea el mismo
# contenedor— y se clickeaban resultados de antes de que WhatsApp filtrara.
QUIETUD_DE_RESULTADOS_MS = 700

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
        """Navega si hace falta y deja la página decidida: lista de chats o QR.

        **Si la lista ya está a la vista, no navega.** Una corrida manda varios
        mensajes seguidos y esto se llama antes de cada uno: recargar WhatsApp
        Web cada vez tarda, tira abajo el estado de la interfaz, y multiplica
        las chances de agarrar la página a medio cargar.

        ⚠️ El navegador dedicado entrega la página **sin navegar** (about:blank):
        éste es el único lugar que la lleva a WhatsApp Web. Preguntar por la
        sesión antes de esto devolvía `SESION_CAIDA` con la sesión sana — la
        causa principal de la corrida fallida del 27/08.

        Tres salidas, cada una con su consecuencia:
          - la lista apareció → listo;
          - el QR apareció → retorna igual, y `sesion_iniciada()` lo va a decir
            (`SESION_CAIDA`, reintentable — quizá alguien vincula);
          - ninguno en `ESPERA_MS` → `PaginaNoCargo` (transitorio, reintenta
            como `TIMEOUT`). **No** `ErrorDeSelector`: eso frenaría la corrida
            entera por una página lenta.
        """
        if await self._page.query_selector(selectores.LISTA_DE_CHATS.css) is None:
            await self._page.goto(selectores.URL, wait_until="domcontentloaded")

        try:
            await self._esperar_qr_o_lista(self._espera)
        except Exception as error:
            raise PaginaNoCargo(
                f"ni {selectores.LISTA_DE_CHATS.que_busca} ni {selectores.QR.que_busca} "
                "aparecieron: la página no terminó de cargar"
            ) from error

    async def sesion_iniciada(self) -> bool:
        """`False` si la página pide escanear el código.

        Espera a que la página se decida en vez de mirar una foto instantánea:
        durante un "Conectando…" o un reload no hay ni QR ni lista por un
        momento, y responder `False` ahí era un `SESION_CAIDA` espurio.

        Con la lista presente, la ausencia del QR es la señal de que hay sesión.
        """
        try:
            await self._esperar_qr_o_lista(min(self._espera, ESPERA_BUSQUEDA_MS))
        except Exception:
            return False
        if await self._page.query_selector(selectores.QR.css) is not None:
            return False
        return await self._page.query_selector(selectores.LISTA_DE_CHATS.css) is not None

    async def _esperar_qr_o_lista(self, timeout_ms: float) -> None:
        """Hasta que la página muestre la lista de chats o el QR, lo que llegue."""
        combinado = f"{selectores.LISTA_DE_CHATS.css}, {selectores.QR.css}"
        await self._page.wait_for_selector(combinado, timeout=timeout_ms, state="attached")

    # -- Abrir el chat ---------------------------------------------------------

    async def buscar_contacto(self, identificador: str) -> bool:
        """Busca y abre el chat. `False` si no aparece ninguno.

        `False` NO es un error de selector: que un contacto no esté en la lista
        es un dato del mundo, y el motor lo reporta como `CHAT_NO_ABRE`.

        `motivo_no_abrio` queda cargado cuando devuelve `False`, para que el
        reporte distinga "la búsqueda no trajo resultados" de "hubo filas pero
        ninguna abrió el chat que decía ser" — antes los dos eran el mismo
        `CHAT_NO_ABRE` genérico y diagnosticarlo exigía ir a los logs de la Mac.

        Es el **primer escalón** de la cascada de apertura: los demás
        (`buscar_verificado`, `buscar_limpiando_filtros`, ...) reusan estas
        mismas piezas y corren sólo cuando éste devolvió `False`.
        """
        self.motivo_no_abrio: str | None = None
        await self._tipear_en_buscador(identificador)

        if not await self._esperar_filtrado(identificador):
            log.info("contacto_sin_resultados", identificador=identificador)
            self.motivo_no_abrio = "sin_resultados"
            return False

        filas = self._page.locator(selectores.RESULTADO_DE_BUSQUEDA.css)
        return await self._abrir_desde_filas(filas)

    async def _tipear_en_buscador(self, identificador: str) -> None:
        """Limpia el buscador y tipea el término, tecla por tecla.

        Se limpia antes de escribir: si quedó una búsqueda anterior, los
        resultados serían de otro contacto y se abriría el chat equivocado.
        """
        #  Y se limpia también lo leído de la fila anterior (B5): un valor viejo
        #  acá sería un número de OTRO contacto esperando a que alguien lo lea.
        self.numero_de_la_fila: str | None = None
        buscador = await self._exigir(selectores.BUSCADOR)
        await buscador.click(timeout=self._espera)
        await self._page.keyboard.press(SELECCIONAR_TODO)
        await self._page.keyboard.press("Delete")
        await buscador.press_sequentially(identificador, delay=20)

    async def _esperar_filtrado(self, identificador: str) -> bool:
        """¿La lista terminó de filtrarse? `False` si no dio señales a tiempo.

        ⚠️ El selector de resultados matchea el MISMO contenedor que la lista
        de chats de siempre: un "apareció una fila" se satisface al instante
        con las filas viejas, antes de que WhatsApp filtre — y el loop de
        apertura clickeaba chats que no tenían nada que ver con lo buscado. La
        señal de que la búsqueda terminó es una fila que DIGA lo buscado; y si
        ninguna lo dice (buscar por número muestra el nombre agendado), que la
        lista haya dejado de cambiar por un momento.
        """
        await self._page.evaluate("() => { window.__resultados_de_busqueda = undefined; }")
        try:
            await self._page.wait_for_function(
                """([css, termino, quietudMs]) => {
                    const norm = (s) => (s || '')
                        .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                        .toLowerCase().trim();
                    const filas = Array.from(document.querySelectorAll(css));
                    if (filas.length === 0) return false;
                    const buscado = norm(termino);
                    if (buscado && filas.some(f => norm(f.innerText).includes(buscado))) {
                        return true;
                    }
                    const foto = filas.map(f => f.innerText).join('\\u0000');
                    const ahora = Date.now();
                    const estado = window.__resultados_de_busqueda
                        || (window.__resultados_de_busqueda = {});
                    if (estado.foto !== foto) {
                        estado.foto = foto;
                        estado.desde = ahora;
                        return false;
                    }
                    return ahora - estado.desde >= quietudMs;
                }""",
                arg=[selectores.RESULTADO_DE_BUSQUEDA.css, identificador, QUIETUD_DE_RESULTADOS_MS],
                timeout=ESPERA_BUSQUEDA_MS,
            )
        except Exception:
            return False
        return True

    async def _abrir_desde_filas(self, filas, *, exigir_que_contenga: str | None = None) -> bool:
        """Clickea filas hasta que una abra su chat. `False` si ninguna.

        ⚠️ Locators y no handles, y cada fila protegida. WhatsApp redibuja la
        lista de resultados mientras se la mira: un handle agarrado hace medio
        segundo puede estar "not attached to the DOM" al clickearlo — mató al
        primer RESOLVER real, en el segundo contacto del lote. El locator se
        re-resuelve en el momento del click, y si la fila igual desapareció,
        se prueba la siguiente en vez de reventar el job entero.

        ⚠️ La primera fila no siempre es un chat: la lista nueva es una grilla
        y las primeras filas pueden ser títulos de sección ("Chats",
        "Contactos") que no abren nada — pasó en la primera verificación real.

        Y "apareció un encabezado" no alcanza como señal de que abrió: en el
        segundo mensaje de una corrida ya hay un chat abierto de antes, y su
        encabezado viejo haría pasar por buena a una fila muerta. La señal es
        que el encabezado visible DIGA lo que decía la fila clickeada. Cuál
        chat es, lo sigue decidiendo la comparación de identidad (R1).

        `exigir_que_contenga` es el escalón A3: la fila tiene que CONTENER lo
        buscado —dígito a dígito si lo buscado es un número, que formateado con
        espacios y guiones hoy nunca matchea— o no se la clickea. Sin filas que
        lo contengan, la respuesta es "no está", no un click a ciegas.
        """
        cantidad = min(await filas.count(), 6)
        if cantidad == 0:
            self.motivo_no_abrio = "sin_resultados"
            return False

        alguna_verificada = False
        for i in range(cantidad):
            fila = filas.nth(i)
            #  La primera candidata espera más (S2.5): con red lenta, 3 s para
            #  leer y clickear producía `CHAT_NO_ABRE` de chats que existían.
            #  Las siguientes mantienen la espera corta para no pagar seis
            #  timeouts largos en el caso patológico.
            espera_fila = ESPERA_BUSQUEDA_MS if i == 0 else ESPERA_CORTA_MS
            try:
                texto_fila = ((await fila.inner_text(timeout=espera_fila)) or "").strip()
                if not texto_fila:
                    continue
                if exigir_que_contenga is not None:
                    if not _contiene_lo_buscado(texto_fila, exigir_que_contenga):
                        continue
                    alguna_verificada = True
                #  B5: varias versiones llevan el identificador del contacto en
                #  un atributo de la fila. Se lee ANTES de clickear —después la
                #  fila puede no existir— y `resolver_numero` lo usa de último
                #  escalón. Que falte es lo normal; no decide nada acá.
                self.numero_de_la_fila = await self._numero_del_atributo(fila)
                await fila.click(timeout=espera_fila)
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
        if exigir_que_contenga is not None and not alguna_verificada:
            log.info("ninguna_fila_contiene_lo_buscado", filas=cantidad)
            self.motivo_no_abrio = "ninguna_fila_contiene_lo_buscado"
        else:
            log.info("resultados_sin_chat", filas=cantidad)
            self.motivo_no_abrio = "resultados_sin_chat"
        return False

    async def _numero_del_atributo(self, fila) -> str | None:
        """El identificador `...@c.us` que algunas versiones ponen en la fila."""
        try:
            data_id = await fila.get_attribute("data-id", timeout=500)
            if not data_id:
                hijo = fila.locator(selectores.ATRIBUTO_DE_ID_EN_LA_FILA.css).first
                if await hijo.count():
                    data_id = await hijo.get_attribute("data-id", timeout=500)
        except Exception:
            return None
        encontrado = _ID_DE_CHAT.search(data_id or "")
        return f"+{encontrado.group(1)}" if encontrado else None

    # -- Los escalones alternativos de apertura (cascada A) -------------------
    #
    # Corren sólo cuando `buscar_contacto` devolvió `False`, en el orden que
    # arma `jobs/enviar.py`. Ninguno saltea lo que sigue después de abrir: la
    # comparación de identidad por número y el campo vacío corren igual, para
    # cualquier escalón. Abrir el chat nunca fue la garantía — la garantía es
    # el paso 6 del motor.

    async def buscar_verificado(self, termino: str, numero: str | None = None) -> bool:
        """A3: igual que buscar, pero sólo clickea filas que CONTENGAN lo buscado.

        Con `numero`, una fila también vale si sus dígitos contienen los del
        número (la fila muestra `+54 9 11 4440-5036` y se busca
        `+5491144405036`; comparar el texto crudo no matchea nunca).
        Si ninguna fila contiene nada de eso, devuelve «no está» en vez de
        clickear a ciegas: es el escalón que cierra el riesgo de abrir el chat
        equivocado.
        """
        self.motivo_no_abrio = None
        await self._tipear_en_buscador(termino)
        #  Que la espera venza no corta: la exigencia de contención de abajo ya
        #  protege contra clickear la lista sin filtrar.
        await self._esperar_filtrado(termino)

        filas = self._page.locator(selectores.RESULTADO_DE_BUSQUEDA.css)
        if await self._abrir_desde_filas(filas, exigir_que_contenga=termino):
            return True
        if numero and numero != termino:
            return await self._abrir_desde_filas(filas, exigir_que_contenga=numero)
        return False

    async def buscar_limpiando_filtros(self, termino: str) -> bool:
        """A4: WhatsApp **Business** con un filtro o etiqueta activos.

        La radiografía del 28/08 mostró `all-filter`, `additional-filters` y
        catorce `label_item_*`: con un filtro puesto, la búsqueda queda acotada
        a ese subconjunto y el contacto no aparece. Se clickea «Todos» y se
        reintenta la búsqueda de siempre. En el WhatsApp común el botón no
        existe y este escalón dice «no pude» sin tocar nada.
        """
        boton = self._page.locator(selectores.FILTRO_TODOS.css).first
        try:
            if await boton.count() == 0:
                log.info("sin_barra_de_filtros")
                return False
            await boton.click(timeout=ESPERA_CORTA_MS)
        except Exception:
            log.info("filtro_todos_no_clickeable")
            return False
        return await self.buscar_contacto(termino)

    async def buscar_tipeando_distinto(self, termino: str) -> bool:
        """A5: el texto entra al buscador pero no dispara el filtrado.

        Es exactamente el síntoma de la radiografía del 28/08: el `value` del
        campo era correcto y la lista no se movía. En vez de
        `press_sequentially`, `fill()` seguido de un `input`/`keyup`
        despachados a mano — otra vía para que la aplicación se entere de que
        el campo cambió.
        """
        self.motivo_no_abrio = None
        self.numero_de_la_fila = None
        buscador = await self._exigir(selectores.BUSCADOR)
        await buscador.click(timeout=self._espera)
        await self._page.keyboard.press(SELECCIONAR_TODO)
        await self._page.keyboard.press("Delete")
        try:
            await buscador.fill(termino, timeout=ESPERA_CORTA_MS)
        except Exception:
            #  Un contenteditable puede rechazar fill(): se escribe por teclado
            #  y quedan igual los eventos despachados a mano, que son el punto.
            await buscador.press_sequentially(termino, delay=20)
        await buscador.evaluate(
            """(el) => {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
            }"""
        )

        if not await self._esperar_filtrado(termino):
            self.motivo_no_abrio = "sin_resultados"
            return False
        filas = self._page.locator(selectores.RESULTADO_DE_BUSQUEDA.css)
        return await self._abrir_desde_filas(filas)

    async def buscar_con_teclado(self, termino: str) -> bool:
        """A6: abrir el primer resultado con ArrowDown + Enter.

        No depende ni del selector de la lista ni del click: si el ancla de los
        resultados es el problema, esto lo esquiva por completo. Qué chat abrió
        lo decide después la comparación de identidad, como siempre.
        """
        self.motivo_no_abrio = None
        await self._tipear_en_buscador(termino)
        await self._esperar_filtrado(termino)
        await self._page.keyboard.press("ArrowDown")
        await self._page.keyboard.press("Enter")
        try:
            await self._page.wait_for_selector(
                selectores.HEADER.css, timeout=ESPERA_BUSQUEDA_MS, state="visible"
            )
        except Exception:
            self.motivo_no_abrio = "teclado_no_abrio"
            return False
        return True

    async def buscar_con_otra_ancla(self, termino: str) -> bool:
        """A7: las filas por sus anclas alternativas.

        Cubre la hipótesis «el selector de resultados apunta a la lista general
        en vez de a los resultados». Loguea cuántas filas devolvió cada ancla —
        ese dato solo ya cierra la pregunta abierta del diagnóstico del 28/08.
        """
        self.motivo_no_abrio = None
        await self._tipear_en_buscador(termino)
        await self._esperar_filtrado(termino)

        conteos = await selectores.sondear(self._page, selectores.RESULTADOS_ALTERNATIVOS)
        log.info("anclas_alternativas_sondeadas", conteos=conteos)

        filas = self._page.locator(selectores.RESULTADOS_ALTERNATIVOS.css)
        return await self._abrir_desde_filas(filas)

    async def abrir_por_url(self, numero: str) -> bool:
        """A8: la URL `send?phone=`, sin buscador y sin lista.

        El escalón más robusto y el más caro: recarga la página (lento) y con
        un número que no está en WhatsApp muestra un cartel de error que hay
        que detectar antes de dar el chat por abierto. `jobs/enviar.py` lo
        habilita recién en la segunda pasada del contacto.
        """
        self.motivo_no_abrio = None
        self.numero_de_la_fila = None
        digitos = "".join(c for c in numero if c.isdigit())
        if not digitos:
            self.motivo_no_abrio = "sin_numero_para_url"
            return False

        await self._page.goto(
            selectores.URL_ENVIAR_POR_NUMERO.format(numero=digitos),
            wait_until="domcontentloaded",
        )
        combinado = f"{selectores.HEADER.css}, {selectores.AVISO_DE_URL_INVALIDA.css}"
        try:
            await self._page.wait_for_selector(combinado, timeout=self._espera, state="visible")
        except Exception:
            self.motivo_no_abrio = "url_no_abrio"
            return False

        aviso = await self._page.query_selector(selectores.AVISO_DE_URL_INVALIDA.css)
        if aviso is not None:
            #  «El número no está en WhatsApp» (u otro diálogo). Se cierra y se
            #  reporta que no: dar esto por abierto sería escribir en el vacío.
            log.info("url_directa_con_aviso", numero_digitos=len(digitos))
            await self._page.keyboard.press("Escape")
            self.motivo_no_abrio = "numero_sin_whatsapp"
            return False
        return True

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

        En cascada (B), de más barato a más caro:

        B1. El header ya muestra un número — el contacto no está agendado.
        B2. Abrir el panel del contacto y leer el span con forma de teléfono.
        B3. Si el span no matchea, barrer el TEXTO entero del panel con la
            expresión de teléfono y quedarse con el ÚNICO candidato — con más
            de uno, `None`, igual que hoy: falla cerrado.
        B4. Si el panel no abre por el título, el botón de info del header.
        B5. El identificador que la fila clickeada llevaba en su atributo — la
            lectura más barata cuando está, y no abre ningún panel.

        `ultimo_escalon_numero` queda cargado con el que resolvió, para que el
        reporte lo lleve a Mongo.

        ⚠️ Si ninguno da un número reconocible, devuelve `None` y no intenta
        deducirlo del nombre ni de la búsqueda. Lo que sigue es la comparación
        de identidad (R1): un número aproximado acá es un mensaje a otra
        persona.
        """
        self.ultimo_escalon_numero: str | None = None

        # ---- B1: el header -------------------------------------------------
        header = await self.leer_header()
        if header and (numero := _numero_en(header)):
            self.ultimo_escalon_numero = "B1_header"
            return numero

        #  Abrir el panel es la única forma de ver el teléfono de un contacto
        #  agendado. Es de sólo lectura: no toca la conversación.
        abierto = await self._abrir_panel_de_contacto()
        if not abierto:
            return await self._numero_de_la_fila_clickeada()

        try:
            # ---- B2: el span con forma de teléfono -------------------------
            telefonos = self._page.locator(selectores.TELEFONO_EN_EL_PANEL.css)
            for i in range(min(await telefonos.count(), 40)):
                try:
                    texto = (await telefonos.nth(i).inner_text(timeout=1_000) or "").strip()
                except Exception:
                    #  Ese span se redibujó: se sigue con el próximo.
                    continue
                if numero := _numero_en(texto):
                    self.ultimo_escalon_numero = "B2_span_del_panel"
                    return numero

            # ---- B3: el barrido del drawer entero --------------------------
            #
            # El selector del span no matcheó nada con forma de teléfono. Antes
            # de rendirse, todo el texto del panel: si hay UN candidato, es. Con
            # más de uno hay ambigüedad sobre a quién le escribiríamos, y la
            # respuesta correcta es no saber (R2).
            if numero := await self._numero_en_todo_el_panel():
                self.ultimo_escalon_numero = "B3_barrido_del_panel"
                return numero
            return await self._numero_de_la_fila_clickeada()
        finally:
            # ⚠️ El panel abierto TAPA el campo de texto y se come los clicks:
            # sin esto, el `escribir()` siguiente muere esperando un click que
            # nunca entra. Lo encontró la verificación en la primera Mac —
            # Playwright reintentando 30 segundos contra el drawer.
            await self._page.keyboard.press("Escape")

    async def _abrir_panel_de_contacto(self) -> bool:
        """El drawer del contacto: por el título (hoy) o el botón de info (B4)."""
        try:
            titulo = self._page.locator(selectores.TITULO_DEL_HEADER.css).first
            if await titulo.count():
                await titulo.click(timeout=ESPERA_CORTA_MS)
                await self._page.wait_for_selector(
                    selectores.PANEL_DE_CONTACTO.css, timeout=ESPERA_CORTA_MS
                )
                return True
        except Exception:
            pass

        # B4: el click sobre el nombre depende de un `data-testid` que puede
        # haber cambiado; el header entero como botón es otra ancla.
        try:
            boton = self._page.locator(selectores.BOTON_DE_INFO_DEL_HEADER.css).first
            if await boton.count() == 0:
                log.info("panel_de_contacto_no_abrio")
                return False
            await boton.click(timeout=ESPERA_CORTA_MS)
            await self._page.wait_for_selector(
                selectores.PANEL_DE_CONTACTO.css, timeout=ESPERA_CORTA_MS
            )
            log.info("panel_abierto_por_boton_de_info")
            return True
        except Exception:
            log.info("panel_de_contacto_no_abrio")
            return False

    async def _numero_en_todo_el_panel(self) -> str | None:
        """B3: la expresión de teléfono sobre el texto completo del drawer."""
        try:
            panel = self._page.locator(selectores.PANEL_DE_CONTACTO.css).first
            if await panel.count() == 0:
                return None
            texto = (await panel.inner_text(timeout=ESPERA_CORTA_MS)) or ""
        except Exception:
            return None
        candidatos = {c.strip() for c in _TELEFONO.findall(texto)}
        if len(candidatos) != 1:
            return None
        return candidatos.pop()

    async def _numero_de_la_fila_clickeada(self) -> str | None:
        """B5: el identificador que traía la fila de la lista, si lo traía.

        Lo cargó `_abrir_desde_filas` ANTES de clickear, así que es de la fila
        que abrió este chat — no una deducción. Cuando está, es la lectura más
        barata; cuando no, `None` y el motor falla cerrado como siempre.
        """
        numero = getattr(self, "numero_de_la_fila", None)
        if numero:
            self.ultimo_escalon_numero = "B5_atributo_de_la_fila"
        return numero

    async def es_grupo(self) -> bool:
        """Un grupo nunca recibe un seguimiento comercial.

        Dos señales, en cascada: la marca de siempre (que depende de un
        atributo `title` que la verificación del 25/08 declaró muerto en el
        header, así que probablemente hoy no detecta nada), y el TEXTO del
        subtítulo — en un grupo es la lista de participantes separados por
        coma. Se exige la coma y que no parezca una línea de estado («últ. vez
        hoy a las 12:30» lleva dos puntos, nunca coma).
        """
        if await self._page.query_selector(selectores.MARCA_DE_GRUPO.css) is not None:
            return True
        try:
            subtitulo = self._page.locator(selectores.SUBTITULO_DEL_HEADER.css).first
            if await subtitulo.count() == 0:
                return False
            texto = ((await subtitulo.inner_text(timeout=1_000)) or "").strip()
        except Exception:
            return False
        return "," in texto and ":" not in texto

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
            # Cascada C: antes de reventar, cuánto devolvió cada opción del
            # selector por separado. La próxima vez que WhatsApp mueva el DOM,
            # el log dice qué ancla sobrevivió en vez de obligar a otra
            # radiografía a mano.
            try:
                conteos = await selectores.sondear(self._page, selector)
                log.info("selector_sondeado", que_busca=selector.que_busca, conteos=conteos)
            except Exception:
                #  El diagnóstico nunca tapa el error real.
                pass
            raise ErrorDeSelector(f"no apareció {selector.que_busca}: {selector.css}") from error
        return loc


# ---------------------------------------------------------------------------
# Leer un número de un texto
# ---------------------------------------------------------------------------

# Un teléfono como lo muestra WhatsApp: `+54 9 11 4440-5036`. Se pide el `+`
# porque sin él cualquier número de una conversación —un precio, una cantidad—
# pasaría por teléfono.
_TELEFONO = re.compile(r"\+\d[\d\s\-().]{6,}\d")

# El identificador que algunas versiones ponen en el atributo de la fila:
# `false_5491144405036@c.us`, `5491144405036@c.us`. El sufijo `@c.us` es de
# contactos; los grupos llevan `@g.us` y NO se matchean a propósito.
_ID_DE_CHAT = re.compile(r"(\d{6,})@c\.us")


def _contiene_lo_buscado(texto_fila: str, buscado: str) -> bool:
    """¿La fila contiene lo que se buscó? (escalón A3)

    Texto contra texto, sin acentos ni mayúsculas. Cuando lo buscado es un
    número, dígito a dígito: la fila muestra `+54 9 11 4440-5036` y se busca
    `+5491144405036` — comparar los strings crudos no matchea nunca.
    """
    digitos_buscados = "".join(c for c in buscado if c.isdigit())
    if digitos_buscados and len(digitos_buscados) >= 6:
        digitos_fila = "".join(c for c in texto_fila if c.isdigit())
        if digitos_buscados in digitos_fila:
            return True
    return _normalizar_texto(buscado) in _normalizar_texto(texto_fila)


def _normalizar_texto(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower().strip()


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
