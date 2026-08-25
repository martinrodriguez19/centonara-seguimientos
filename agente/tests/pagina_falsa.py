"""Un WhatsApp Web de mentira, en HTML, para correrle el adaptador real encima.

**Qué prueba esto y qué no.** Prueba que `whatsapp_web.py` hace lo que dice
—busca, abre, lee el header, resuelve el número, escribe, envía, confirma— contra
un DOM con la estructura que los selectores esperan, usando un Chromium de
verdad. **No prueba que WhatsApp Web se vea así hoy**: eso sólo se sabe corriendo
`verificar_selectores()` contra una sesión real, y hasta que eso pase la fecha de
`selectores.VERIFICADO` sigue en `None`.

Que la distinción esté clara importa: alguien podría mirar estos tests en verde y
concluir que el envío funciona. Lo que funciona es la lógica.

La página imita lo mínimo para que la secuencia de doce pasos tenga sentido:
buscar filtra, hacer click abre, el campo acepta texto, y enviar agrega el
mensaje al hilo.
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


def html(
    chats: list[ChatFalso],
    *,
    con_sesion: bool = True,
    sin_campo_de_texto: bool = False,
) -> str:
    """La página. `sin_campo_de_texto` simula que WhatsApp cambió el DOM."""
    datos = json.dumps(
        [
            {
                "id": c.id,
                "header": c.header,
                "telefono": c.telefono_en_panel,
                "grupo": c.es_grupo,
                "borrador": c.borrador,
                "salientes": c.salientes,
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

    return f"""<!doctype html>
<html><body>
  <!-- El panel lateral, como lo mostró la radiografía del 25/8/2026: el
       buscador es un <input> común (ya no un contenteditable), con el
       data-tab="3" de siempre, arriba de la lista. -->
  <div id="side">
    <input type="text" role="textbox" data-tab="3" id="buscador">
    <div id="pane-side">
      <div id="resultados"></div>
    </div>
  </div>

  <!-- El chat abierto. -->
  <div id="main" style="display:none">
    <header data-testid="conversation-header">
      <span dir="auto" title="" id="titulo"></span>
      <div role="button"><span id="subtitulo" title=""></span></div>
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
  </div>

<script>
const CHATS = {datos};
let abierto = null;

const $ = (id) => document.getElementById(id);

// Buscar filtra la lista, igual que la aplicación real.
$('buscador').addEventListener('input', () => {{
  const q = ($('buscador').value || '').trim().toLowerCase();
  const cont = $('resultados');
  cont.innerHTML = '';
  if (!q) return;
  CHATS.filter(c => c.id.toLowerCase().includes(q) || c.header.toLowerCase().includes(q))
       .forEach(c => {{
    const fila = document.createElement('div');
    fila.setAttribute('role', 'listitem');
    fila.textContent = c.header;
    fila.onclick = () => abrir(c);
    cont.appendChild(fila);
  }});
}});

function abrir(c) {{
  abierto = c;
  $('main').style.display = 'block';
  $('titulo').setAttribute('title', c.header);
  $('titulo').textContent = c.header;

  // Un grupo se reconoce por el subtítulo con los participantes: la marca que
  // busca el selector es la coma en el `title`.
  $('subtitulo').setAttribute('title', c.grupo ? 'Vos, Juan, Marta' : '');

  if ($('campo')) $('campo').innerText = c.borrador || '';
  $('panel').style.display = 'none';
  $('panel-telefono').textContent = c.telefono || '';

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
