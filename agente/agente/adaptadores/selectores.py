"""Todos los selectores de WhatsApp Web. **Ninguno fuera de acá.**

Es una regla del proyecto y no una preferencia de estilo. WhatsApp Web cambia su
DOM sin avisar y sin versionar: el día que cambie, arreglarlo tiene que ser
editar un archivo y no salir a buscar cadenas desparramadas por el código.

Cada entrada dice **qué busca** y **por qué ese selector y no otro**. Un selector
sin explicación es imposible de arreglar por alguien que no lo escribió.

---

## ⚠️ ESTADO: SIN VERIFICAR CONTRA WHATSAPP WEB

**Última verificación contra WhatsApp Web real: NUNCA COMPLETA.**

Primera pasada parcial el 25/8/2026 (`--verificar-selectores`, Mac real):
`LISTA_DE_CHATS` respondió; `BUSCADOR` con `data-tab='3'` estaba muerto y se
reancló al panel lateral. El resto sigue siendo una hipótesis hasta que una
pasada con `--chat` salga entera en verde. Lo que sí está probado es la lógica
del adaptador que los usa, contra una página de prueba con esta estructura.

No es un detalle menor: un selector que no matchea hace que el motor aborte con
`SELECTOR_ROTO`, que **frena la corrida entera**. Eso es lo correcto —es
preferible frenar que escribir a ciegas— pero significa que hasta la primera
verificación real este módulo no manda nada.

Cuando se verifiquen, actualizar la fecha de arriba y la de `VERIFICADO`.

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
VERIFICADO: str | None = None

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
