"""Todos los selectores de WhatsApp Web. **Ninguno fuera de acá.**

Es una regla del proyecto y no una preferencia de estilo. WhatsApp Web cambia su
DOM sin avisar y sin versionar: el día que cambie, arreglarlo tiene que ser
editar un archivo y no salir a buscar cadenas desparramadas por el código.

Cada entrada dice **qué busca** y **por qué ese selector y no otro**. Un selector
sin explicación es imposible de arreglar por alguien que no lo escribió.

---

## ESTADO: VERIFICADOS CONTRA WHATSAPP WEB REAL

**Última verificación completa: 25/8/2026**, con `--verificar-selectores
--chat` sobre una sesión real de WhatsApp Business (Chrome 152, macOS, la
primera Mac instalada). Las siete piezas respondieron: lista, buscador,
apertura del chat, encabezado, número en el panel, campo y botón de enviar.

Lo que esa calibración encontró y quedó documentado selector por selector: el
buscador pasó de `contenteditable` a un `<input>` común, el título perdió su
atributo `title`, el teléfono vive en el `drawer-right` — y el panel abierto
se come los clicks, por eso `resolver_numero` lo cierra con Escape.

Un selector que deje de matchear hace que el motor aborte con `SELECTOR_ROTO`,
que **frena la corrida entera**. Es lo correcto: preferible frenar que escribir
a ciegas. El día que WhatsApp cambie de nuevo, el camino es el mismo que esta
vez: `--verificar-selectores --chat <número de prueba>`, leer la radiografía,
reanclar acá, y actualizar la fecha de `VERIFICADO`.

---

## Por qué se prefiere `data-testid`

WhatsApp Web genera sus clases CSS de forma automática y cambian entre
despliegues; los `data-testid` sobreviven mucho más. Donde no hay uno, se usa
`aria-*` o el rol, que están atados a la accesibilidad y por eso son más
estables que una clase.

Nunca una clase generada. Nunca una posición (`nth-child`): el orden de los
elementos cambia con el estado de la conversación.
"""

from __future__ import annotations

from dataclasses import dataclass

# La fecha que importa. `None` = nunca se verificó contra WhatsApp Web real.
# Se completa a mano, después de una pasada entera en verde de
# `--verificar-selectores --chat` en una Mac real: es el acto deliberado que
# levanta el guard del despachador para el modo real.
VERIFICADO: str | None = "2026-08-25"

URL = "https://web.whatsapp.com/"


@dataclass(frozen=True)
class Selector:
    """Un selector, con el motivo por el que es ese."""

    css: str
    #  Qué se espera encontrar. Sale en el error cuando no aparece.
    que_busca: str
    #  Si falta, ¿el DOM cambió, o simplemente no aplica a este chat?
    #  `True` = su ausencia significa que WhatsApp cambió.
    estructural: bool = True

    def __str__(self) -> str:
        return self.css


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------

QR = Selector(
    #  `div[data-ref] canvas`: el canvas del QR vive desde siempre en un div
    #  con el token de vinculación en `data-ref`, y no depende del idioma.
    "canvas[aria-label*='scan' i], div[data-testid='qrcode'], div[data-ref] canvas",
    "el código QR de vinculación",
    #  Que no esté es lo normal: significa que la sesión está iniciada.
    estructural=False,
)

LISTA_DE_CHATS = Selector(
    "div[id='pane-side']",
    "el panel lateral con la lista de chats",
)

# ---------------------------------------------------------------------------
# Buscar y abrir un chat
# ---------------------------------------------------------------------------

# ⚠️ Ya no es un `div[contenteditable]`: la radiografía del 25/8/2026 (primera
# verificación real) mostró que WhatsApp lo volvió un `<input type='text'>`
# común — con el `data-tab='3'` de siempre, `role='textbox'`, y un id generado
# que no sirve de ancla. Por eso el selector viejo, que exigía el tag, no
# encontraba nada. El contenteditable queda de última opción por si vuelven.
BUSCADOR = Selector(
    "div[id='side'] input[data-tab='3'], div[id='side'] input[role='textbox'], "
    "div[id='side'] div[contenteditable='true']",
    "el campo de búsqueda de chats",
)

RESULTADO_DE_BUSQUEDA = Selector(
    #  En las versiones nuevas la lista es una grilla y cada chat un `row`.
    "div[id='pane-side'] div[role='listitem'], div[id='pane-side'] div[role='row']",
    "un resultado en la lista de búsqueda",
    #  Que no haya resultados es un dato del mundo: ese contacto no existe.
    estructural=False,
)

# Anclas ALTERNATIVAS para los resultados (escalón A7 de la cascada). No
# reemplazan a `RESULTADO_DE_BUSQUEDA`: se prueban sólo cuando la ruta de
# siempre no abrió nada, y el log dice cuál devolvió filas — que es justo el
# dato que el diagnóstico del 28/08 no pudo cerrar (¿el selector apunta a la
# lista general en vez de a los resultados?).
RESULTADOS_ALTERNATIVOS = Selector(
    "div[aria-label*='resultado' i] div[role='listitem'], "
    "div[aria-label*='result' i] div[role='listitem'], "
    "div[data-testid='search-results'] div[role='listitem'], "
    "div[data-testid='cell-frame-container']",
    "un resultado de búsqueda, por sus anclas alternativas",
    estructural=False,
)

# La barra de filtros de WhatsApp **Business** (escalón A4). La radiografía del
# 28/08 mostró `all-filter`, `additional-filters` y catorce `label_item_*`: si
# hay un filtro o etiqueta activos, la búsqueda queda acotada a ese subconjunto
# y un contacto que existe no aparece. Este botón vuelve a "Todos".
FILTRO_TODOS = Selector(
    "button[id='all-filter'], div[id='all-filter'], "
    "button[data-testid='all-filter'], "
    "button[aria-label*='todos' i], button[aria-label*='all' i]",
    "el filtro 'Todos' de la barra de WhatsApp Business",
    #  En el WhatsApp común no existe, y eso es lo normal.
    estructural=False,
)

# La URL que abre un chat por número, sin tocar el buscador ni la lista
# (escalón A8). Recarga la página — por eso es el escalón caro — y con un
# número que no está en WhatsApp muestra un cartel de error que hay que
# detectar antes de dar el chat por abierto.
URL_ENVIAR_POR_NUMERO = URL + "send?phone={numero}"

AVISO_DE_URL_INVALIDA = Selector(
    "div[role='dialog']",
    "el cartel de 'el número no está en WhatsApp' tras abrir por URL",
    estructural=False,
)

# Varias versiones ponen el identificador del contacto (`..._549xx@c.us`) en un
# atributo de la fila de la lista. Cuando está, es la lectura de número más
# barata (escalón B5) y no abre ningún panel. Que falte es lo normal.
ATRIBUTO_DE_ID_EN_LA_FILA = Selector(
    "[data-id]",
    "el identificador del contacto en el atributo de la fila",
    estructural=False,
)

# ---------------------------------------------------------------------------
# El chat abierto
# ---------------------------------------------------------------------------

HEADER = Selector(
    "header[data-testid='conversation-header'], div[id='main'] header",
    "el encabezado del chat abierto",
)

# ⚠️ El `[title]` murió: la radiografía del 25/8/2026 mostró que el nombre vive
# en un span con data-testid propio, sin atributo title, dentro de un div
# clickeable (`conversation-info-header`, role=button) que abre el panel del
# contacto. El selector viejo queda de segunda opción.
TITULO_DEL_HEADER = Selector(
    "span[data-testid='conversation-info-header-chat-title'], "
    "div[id='main'] header span[dir='auto'][title]",
    "el nombre o número que muestra el encabezado",
)

# Otra vía para abrir el panel del contacto (escalón B4): el header entero es
# un botón con `data-testid` propio, y sobrevive aunque el span del título —
# que es lo que clickea la vía de siempre — cambie de ancla.
BOTON_DE_INFO_DEL_HEADER = Selector(
    "div[data-testid='conversation-info-header'], "
    "div[id='main'] header div[role='button'][title*='info' i], "
    "div[id='main'] header [aria-label*='info' i]",
    "el botón del encabezado que abre el panel del contacto",
    estructural=False,
)

# El panel que se abre al hacer click en el header. Es de donde sale el teléfono
# cuando el contacto está agendado y el header muestra el nombre. La radiografía
# lo mostró como `drawer-right`; los demás quedan de respaldo.
PANEL_DE_CONTACTO = Selector(
    "div[data-testid='drawer-right'], div[data-testid='chat-info-drawer'], "
    "section[aria-label*='perfil' i], div[id='app'] section",
    "el panel de datos del contacto",
)

# El span del número ya no lleva `dir='auto'`: se recorren los spans del panel
# y el que tenga UN número con forma de teléfono, es. La radiografía mostró el
# formateado ('+54 9 11 2323-1151') a la vista en el drawer.
TELEFONO_EN_EL_PANEL = Selector(
    "div[data-testid='drawer-right'] span, "
    "div[data-testid='chat-info-drawer'] span[dir='auto'], section span[dir='auto']",
    "el teléfono dentro del panel de contacto",
    estructural=False,
)

# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

# Un grupo se detecta por el subtítulo con la lista de participantes. No hay un
# `data-testid` propio, así que se mira lo que sí está.
MARCA_DE_GRUPO = Selector(
    "div[id='main'] header div[role='button'] span[title*=','], "
    "div[data-testid='group-info-drawer']",
    "la señal de que el chat es un grupo",
    estructural=False,
)

# ⚠️ La primera opción de `MARCA_DE_GRUPO` depende del atributo `title`, que la
# verificación del 25/08 declaró muerto en el header. Escalón nuevo: el
# subtítulo del header, cuyo TEXTO en un grupo es la lista de participantes
# separados por coma. Se lee por texto y no por `title`, en `es_grupo()`.
SUBTITULO_DEL_HEADER = Selector(
    "div[id='main'] header div[role='button'] span[dir='auto'], "
    "div[id='main'] header span[data-testid='conversation-info-header-subtitle']",
    "el subtítulo del encabezado (participantes si es un grupo)",
    estructural=False,
)

# ---------------------------------------------------------------------------
# Escribir y enviar
# ---------------------------------------------------------------------------

CAMPO_DE_TEXTO = Selector(
    "div[id='main'] div[contenteditable='true'][data-tab='10'], footer div[contenteditable='true']",
    "el campo donde se escribe el mensaje",
)

BOTON_ENVIAR = Selector(
    #  `data-icon*='send'` cubre las variantes nuevas del ícono (por ejemplo
    #  `wds-ic-send-filled`); los `aria-label` cubren el botón en sí, en los
    #  dos idiomas que puede tener una Mac de un vendedor.
    "button[data-testid='send'], span[data-icon*='send' i], "
    "button[aria-label*='enviar' i], button[aria-label*='send' i]",
    "el botón de enviar",
)

MENSAJES_SALIENTES = Selector(
    "div[id='main'] div.message-out span.selectable-text, "
    "div[id='main'] div[data-testid='msg-container'] span.selectable-text",
    "los mensajes que salieron de esta línea",
    estructural=False,
)


# ---------------------------------------------------------------------------
# Verificación
# ---------------------------------------------------------------------------

# Los que tienen que estar con WhatsApp Web abierto y con sesión, sin haber
# abierto ningún chat todavía. Es lo que se puede comprobar sin tocar nada.
ESTRUCTURALES_AL_ABRIR = (LISTA_DE_CHATS, BUSCADOR)


@dataclass(frozen=True)
class Revision:
    """Qué encontró la verificación."""

    ok: bool
    encontrados: list[str]
    faltantes: list[str]
    verificado: str | None = VERIFICADO

    def como_texto(self) -> str:
        if self.ok:
            return f"selectores: {len(self.encontrados)} de {len(self.encontrados)} responden"
        return "selectores que NO responden: " + ", ".join(self.faltantes)


async def verificar(pagina) -> Revision:
    """¿Los selectores estructurales siguen encontrando algo?

    Se corre **antes de cada corrida**, no durante. Enterarse de que el DOM
    cambió cuando ya se escribieron diez mensajes es tarde; enterarse antes
    cuesta un segundo y frena la corrida sin haber tocado ningún chat.

    Sólo mira los que tienen que estar con la lista de chats a la vista. Los del
    chat abierto no se pueden comprobar sin abrir uno, y abrir uno para
    verificar sería tocar la conversación de alguien.
    """
    encontrados: list[str] = []
    faltantes: list[str] = []

    for selector in ESTRUCTURALES_AL_ABRIR:
        if await pagina.query_selector(selector.css) is not None:
            encontrados.append(selector.que_busca)
        else:
            faltantes.append(f"{selector.que_busca} ({selector.css})")

    return Revision(ok=not faltantes, encontrados=encontrados, faltantes=faltantes)


async def sondear(pagina, selector: Selector) -> dict[str, int]:
    """Cuántos elementos devuelve cada opción del selector, **de a una**.

    Hoy cada `Selector` trae varias opciones separadas por coma y el navegador
    se queda con la primera que matchea — pero nadie sabe cuál fue. Esto las
    prueba en orden y devuelve `{opcion: cantidad}`, para loguear qué ancla
    sobrevivió la próxima vez que WhatsApp mueva el DOM, en vez de obligar a
    otra radiografía a mano.

    Es diagnóstico puro: no clickea, no espera, no cambia nada. En el camino
    feliz no se llama.
    """
    conteos: dict[str, int] = {}
    for opcion in (parte.strip() for parte in selector.css.split(",")):
        if not opcion:
            continue
        try:
            conteos[opcion] = len(await pagina.query_selector_all(opcion))
        except Exception:
            #  Una opción con sintaxis que este navegador no traga: 0 y se sigue.
            conteos[opcion] = 0
    return conteos
