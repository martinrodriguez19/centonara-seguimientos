"""Un WhatsApp Web de mentira, en HTML, para correrle el adaptador real encima.

**Qué prueba esto y qué no.** Prueba que `whatsapp_web.py` hace lo que dice
—busca, abre, lee el header, resuelve el número, escribe, envía, confirma— contra
un DOM con la estructura que los selectores esperan, usando un Chromium de
verdad. **No prueba que WhatsApp Web se vea así hoy**: eso sólo se sabe corriendo
`--verificar-selectores` contra una sesión real, que es lo que respalda la fecha
de `selectores.VERIFICADO`. Cuando esa pasada encuentra un cambio, esta página
se actualiza para imitar la estructura nueva — pasó con el buscador, que dejó
de ser un `contenteditable`, y con el subtítulo del grupo, que perdió el
atributo `title` (por eso acá los participantes van en el TEXTO).

Que la distinción esté clara importa: alguien podría mirar estos tests en verde y
concluir que el envío funciona. Lo que funciona es la lógica.

La página imita lo mínimo para que la secuencia de doce pasos tenga sentido:
buscar filtra, hacer click abre, el campo acepta texto, y enviar agrega el
mensaje al hilo. Y desde las cascadas, también los escenarios que las disparan:
la barra de filtros de Business (`con_filtro_de_etiqueta`), el teléfono que no
está en el span esperado (`telefono_fuera_del_span`) y la apertura por teclado.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ChatFalso:
    """Un chat de la lista."""

    id: str
    #  Lo que muestra el encabezado: un nombre si está agendado, o el número.
    header: str
    #  El teléfono que aparece en el panel de contacto. `None` = no se puede leer.
    telefono_en_panel: str | None = None
    es_grupo: bool = False
    #  Lo que el vendedor dejó escrito sin mandar.
    borrador: str = ""
    salientes: list[str] = field(default_factory=list)
    #  El teléfono está en el drawer pero NO en el span que el selector espera
    #  (el escenario del escalón B3: barrer el texto del panel entero).
    telefono_fuera_del_span: bool = False


def html(
    chats: list[ChatFalso],
    *,
    con_sesion: bool = True,
    sin_campo_de_texto: bool = False,
    con_filtro_de_etiqueta: bool = False,
) -> str:
    """La página. `sin_campo_de_texto` simula que WhatsApp cambió el DOM.

    `con_filtro_de_etiqueta` simula WhatsApp Business con una etiqueta activa:
    la búsqueda no devuelve NADA hasta que se clickea el botón «Todos» — el
    escenario del escalón A4 y de la máquina que más avanzó el 28/08.
    """
    datos = json.dumps(
        [
            {
                "id": c.id,
                "header": c.header,
                "telefono": c.telefono_en_panel,
                "grupo": c.es_grupo,
                "borrador": c.borrador,
                "salientes": c.salientes,
                "fueraDelSpan": c.telefono_fuera_del_span,
            }
            for c in chats
        ]
    )

    if not con_sesion:
        return """<!doctype html><html><body>
          <canvas aria-label="Scan this QR code to link a device"></canvas>
        </body></html>"""

    campo = (
        "" if sin_campo_de_texto else '<div contenteditable="true" data-tab="10" id="campo"></div>'
    )
    filtros = (
        '<div id="filtros"><button id="all-filter">Todos</button>'
        '<button id="label_item_1">Clientes</button></div>'
        if con_filtro_de_etiqueta
        else ""
    )

    return f"""<!doctype html>
<html><body>
  <!-- El panel lateral, como lo mostró la radiografía del 25/8/2026: el
       buscador es un <input> común (ya no un contenteditable), con el
       data-tab="3" de siempre, arriba de la lista. La barra de filtros sólo
       existe en la variante Business (radiografía del 28/08). -->
  <div id="side">
    {filtros}
    <input type="text" role="textbox" data-tab="3" id="buscador">
    <div id="pane-side">
      <div id="resultados"></div>
    </div>
  </div>

  <!-- El chat abierto. -->
  <div id="main" style="display:none">
    <header data-testid="conversation-header">
      <span dir="auto" title="" id="titulo"
            data-testid="conversation-info-header-chat-title"></span>
      <div role="button"><span dir="auto" id="subtitulo"></span></div>
    </header>
    <div id="hilo"></div>
    <footer>
      {campo}
      <button data-testid="send" id="enviar">enviar</button>
    </footer>
  </div>

  <!-- El panel de datos del contacto, que se abre al clickear el título. -->
  <div data-testid="chat-info-drawer" id="panel" style="display:none">
    <span dir="auto" id="panel-telefono"></span>
    <div id="panel-notas"></div>
  </div>

<script>
const CHATS = {datos};
let abierto = null;
// Con una etiqueta activa, la búsqueda queda acotada a ese subconjunto — acá,
// al conjunto vacío, que es el peor caso y el que reproduce el 28/08.
let filtroActivo = {json.dumps(con_filtro_de_etiqueta)};

const $ = (id) => document.getElementById(id);

// Buscar filtra la lista, igual que la aplicación real.
$('buscador').addEventListener('input', () => {{
  const q = ($('buscador').value || '').trim().toLowerCase();
  const cont = $('resultados');
  cont.innerHTML = '';
  if (!q || filtroActivo) return;
  // La primera fila es un título de sección que no abre nada, como en la
  // aplicación real: la grilla mete "Chats" / "Contactos" antes de los
  // resultados, y clickearla no hace nada. El adaptador tiene que saltearla.
  const titulo = document.createElement('div');
  titulo.setAttribute('role', 'listitem');
  titulo.textContent = 'Chats';
  cont.appendChild(titulo);
  CHATS.filter(c => c.id.toLowerCase().includes(q) || c.header.toLowerCase().includes(q))
       .forEach(c => {{
    const fila = document.createElement('div');
    fila.setAttribute('role', 'listitem');
    fila.textContent = c.header;
    fila.onclick = () => abrir(c);
    cont.appendChild(fila);
  }});
}});

// Abrir con el teclado: Enter abre el primer resultado real, como WhatsApp.
$('buscador').addEventListener('keydown', (e) => {{
  if (e.key !== 'Enter') return;
  const filas = Array.from(document.querySelectorAll('#resultados [role=listitem]'));
  const primera = filas.find(f => f.onclick);
  if (primera) primera.onclick();
}});

// El botón «Todos» de Business: saca la etiqueta y re-filtra.
const todos = $('all-filter');
if (todos) todos.addEventListener('click', () => {{
  filtroActivo = false;
  $('buscador').dispatchEvent(new Event('input'));
}});

function abrir(c) {{
  abierto = c;
  $('main').style.display = 'block';
  $('titulo').setAttribute('title', c.header);
  $('titulo').textContent = c.header;

  // Un grupo se reconoce por el subtítulo con los participantes. El `title`
  // del span murió (radiografía del 25/08): los nombres van en el TEXTO.
  $('subtitulo').textContent = c.grupo ? 'Vos, Juan, Marta' : 'en línea';

  if ($('campo')) $('campo').innerText = c.borrador || '';
  $('panel').style.display = 'none';
  // B3: a veces el teléfono está en el drawer pero no en el span esperado.
  $('panel-telefono').textContent = c.fueraDelSpan ? '' : (c.telefono || '');
  $('panel-notas').textContent = c.fueraDelSpan ? ('Teléfono: ' + (c.telefono || '')) : '';

  const hilo = $('hilo');
  hilo.innerHTML = '';
  (c.salientes || []).forEach(t => agregarSaliente(t));
}}

// Click en el título abre el panel de contacto.
$('titulo').addEventListener('click', () => {{
  if (abierto) $('panel').style.display = 'block';
}});

function agregarSaliente(texto) {{
  const div = document.createElement('div');
  div.className = 'message-out';
  const span = document.createElement('span');
  span.className = 'selectable-text';
  span.textContent = texto;
  div.appendChild(span);
  $('hilo').appendChild(div);
}}

$('enviar').addEventListener('click', () => {{
  const campo = $('campo');
  if (!campo) return;
  const texto = (campo.innerText || '').trim();
  if (!texto) return;
  agregarSaliente(texto);
  campo.innerText = '';
}});
</script>
</body></html>"""
