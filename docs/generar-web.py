"""El `.md` de los comandos a una página web, para mandar por un enlace.

Se corre así, desde la raíz del repositorio:

    uv run --project agente python docs/generar-web.py

Sale `docs/COMANDOS-MAQUINAS.html`, que se publica como Artifact y queda con un
enlace para reenviar. **Es la forma que mejor funciona en un teléfono**: cada
comando tiene un botón que lo copia entero al portapapeles, así que no depende
de que alguien pueda seleccionar texto adentro de un PDF.

Los tres formatos salen del MISMO `.md` (`generar-pdf.py`, `generar-docx.py` y
éste), por lo mismo de siempre: un papel viejo circulando que dice cosas que
dejaron de ser ciertas ya costó caro en este proyecto. Cada uno lleva la fecha
y el commit del que salió.

Sin dependencias: la página se arma acá, con la biblioteca estándar.
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# En qué app se pega, y qué prompt se muestra, según el lenguaje del bloque del
# `.md`. Es un dato del sistema operativo, no decoración: el prompt es lo que
# le dice a alguien si tiene que abrir la Terminal o PowerShell.
CONSOLAS = {
    "bash": ("Terminal", "$"),
    "powershell": ("PowerShell", "PS>"),
}


@dataclass
class Item:
    """Un "para qué sirve" y lo que va abajo: comandos, o una explicación.

    Son varios y no uno: "Verificar que quedó bien" lleva tres, y cada uno
    tiene que quedar en su propio bloque con su propio botón — juntarlos sería
    darle a alguien tres comandos pegados que no se pueden correr de una.
    """

    titulo: str
    comandos: list[str] = field(default_factory=list)
    lenguaje: str = ""
    texto: str = ""


@dataclass
class Seccion:
    """Una computadora."""

    titulo: str
    nota: str = ""
    items: list[Item] = field(default_factory=list)

    @property
    def consola(self) -> tuple[str, str] | None:
        for item in self.items:
            if item.lenguaje in CONSOLAS:
                return CONSOLAS[item.lenguaje]
        return None

    @property
    def cuantos_comandos(self) -> int:
        return sum(len(i.comandos) for i in self.items)


def sello() -> str:
    try:
        commit = subprocess.run(
            ["git", "-C", str(RAIZ), "log", "-1", "--format=%h %ad", "--date=short"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except Exception:
        commit = "sin datos de git"
    return f"Generado el {date.today():%d/%m/%Y} desde el commit {commit}"


# ---------------------------------------------------------------------------
# Leer el .md
# ---------------------------------------------------------------------------


def leer(origen: pathlib.Path) -> tuple[str, list[str], list[Seccion]]:
    titulo, intro = "", []
    secciones: list[Seccion] = []
    dentro = False
    lenguaje = ""
    bloque: list[str] = []
    parrafo: list[str] = []

    def volcar_parrafo() -> None:
        if not parrafo:
            return
        texto = " ".join(parrafo)
        parrafo.clear()
        if not secciones:
            intro.append(texto)
        elif secciones[-1].items:
            secciones[-1].items[-1].texto = texto
        else:
            secciones[-1].nota = texto

    for linea in origen.read_text(encoding="utf-8").splitlines():
        if linea.startswith("```"):
            if dentro:
                comando = " ".join(l.strip() for l in bloque if l.strip())
                if secciones and secciones[-1].items:
                    secciones[-1].items[-1].comandos.append(comando)
                    secciones[-1].items[-1].lenguaje = lenguaje
                bloque.clear()
            else:
                volcar_parrafo()
                lenguaje = linea[3:].strip()
            dentro = not dentro
            continue
        if dentro:
            bloque.append(linea)
            continue

        if not linea.strip() or linea.startswith("---"):
            volcar_parrafo()
        elif linea.startswith(">"):
            #  Un `>` solo separa dos párrafos de la cita; no es texto.
            resto = linea[1:].strip()
            if resto:
                parrafo.append(resto)
            else:
                volcar_parrafo()
        elif linea.startswith("# "):
            volcar_parrafo()
            if not titulo:
                titulo = linea[2:].strip()
            else:
                secciones.append(Seccion(linea[2:].strip()))
        elif linea.startswith("## "):
            volcar_parrafo()
            if secciones:
                secciones[-1].items.append(Item(linea[3:].strip()))
        else:
            parrafo.append(linea.strip())

    volcar_parrafo()
    return titulo, intro, secciones


_INLINE = re.compile(r"\*\*(.+?)\*\*|`(.+?)`")


def con_formato(texto: str) -> str:
    """`**negrita**` y `` `código` ``, que es todo lo que usa el .md."""

    def reemplazo(encontrado: re.Match[str]) -> str:
        negrita, codigo = encontrado.groups()
        if negrita:
            return f"<strong>{html.escape(negrita)}</strong>"
        return f"<code class='linea'>{html.escape(codigo)}</code>"

    partes, ultimo = [], 0
    for encontrado in _INLINE.finditer(texto):
        partes.append(html.escape(texto[ultimo : encontrado.start()]))
        partes.append(reemplazo(encontrado))
        ultimo = encontrado.end()
    partes.append(html.escape(texto[ultimo:]))
    return "".join(partes)


def id_de(texto: str) -> str:
    limpio = re.sub(r"[^a-z0-9]+", "-", texto.lower().replace("í", "i").replace("ó", "o"))
    return limpio.strip("-")[:40]


# ---------------------------------------------------------------------------
# Escribir la página
# ---------------------------------------------------------------------------

ESTILO = """
:root {
  --papel: #EDF0F4;
  --superficie: #FFFFFF;
  --consola: #F5F8FA;
  --tinta: #131A24;
  --suave: #56626F;
  --linea: #D7DFE8;
  --acento: #0B5D8A;
  --acento-tenue: #E2EDF5;
  --ok: #12735A;
  --cobre: #A2511F;
  --sombra: 0 1px 2px rgba(19, 26, 36, .06), 0 8px 24px -16px rgba(19, 26, 36, .3);
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --papel: #0E141B;
    --superficie: #161E28;
    --consola: #101821;
    --tinta: #E7ECF2;
    --suave: #97A3B2;
    --linea: #2A3644;
    --acento: #63B3E0;
    --acento-tenue: #142330;
    --ok: #4FC0A0;
    --cobre: #E08C52;
    --sombra: 0 1px 2px rgba(0, 0, 0, .4), 0 8px 24px -16px rgba(0, 0, 0, .8);
  }
}

:root[data-theme="dark"] {
  --papel: #0E141B;
  --superficie: #161E28;
  --consola: #101821;
  --tinta: #E7ECF2;
  --suave: #97A3B2;
  --linea: #2A3644;
  --acento: #63B3E0;
  --acento-tenue: #142330;
  --ok: #4FC0A0;
  --cobre: #E08C52;
  --sombra: 0 1px 2px rgba(0, 0, 0, .4), 0 8px 24px -16px rgba(0, 0, 0, .8);
}

* { box-sizing: border-box; }

body {
  background: var(--papel);
  color: var(--tinta);
  font-family: "IBM Plex Sans", -apple-system, "Segoe UI", system-ui, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  -webkit-text-size-adjust: 100%;
}

.hoja {
  max-width: 47rem;
  margin: 0 auto;
  padding-inline: 16px;
  padding-block: 28px 56px;
}

/* --- encabezado --- */
.tapa { display: flex; flex-direction: column; gap: 10px; }

h1 {
  font-family: Archivo, "IBM Plex Sans", system-ui, sans-serif;
  font-weight: 700;
  font-size: clamp(1.5rem, 5.5vw, 2.05rem);
  line-height: 1.15;
  letter-spacing: -.022em;
  text-wrap: balance;
  margin: 0;
}

.entrada { color: var(--suave); margin: 0; max-width: 40rem; }
.entrada strong { color: var(--tinta); font-weight: 600; }

/* --- ir a cada computadora --- */
.saltos {
  position: sticky;
  top: 0;
  z-index: 5;
  margin: 22px -16px 0;
  padding: 10px 16px;
  background: var(--papel);
  border-bottom: 1px solid var(--linea);
  overflow-x: auto;
  scrollbar-width: none;
}
.saltos::-webkit-scrollbar { display: none; }
.saltos ul { display: flex; gap: 8px; list-style: none; margin: 0; padding: 0; width: max-content; }

.salto {
  display: inline-block;
  padding: 6px 12px;
  border: 1px solid var(--linea);
  border-radius: 999px;
  background: var(--superficie);
  color: var(--suave);
  font-size: .82rem;
  font-weight: 500;
  text-decoration: none;
  white-space: nowrap;
}
.salto:hover, .salto:focus-visible { color: var(--acento); border-color: var(--acento); }

/* --- una computadora --- */
.maquina { margin-top: 40px; scroll-margin-top: 68px; }

.maquina > header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px 12px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--tinta);
}

.maquina h2 {
  font-family: Archivo, "IBM Plex Sans", system-ui, sans-serif;
  font-weight: 600;
  font-size: clamp(1.12rem, 3.6vw, 1.35rem);
  letter-spacing: -.01em;
  margin: 0;
  flex: 1 1 auto;
}

.donde {
  font-family: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  font-size: .72rem;
  font-weight: 500;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: var(--acento);
  background: var(--acento-tenue);
  border-radius: 4px;
  padding: 3px 8px;
}

.nota { color: var(--suave); font-size: .93rem; margin: 12px 0 0; }

/* --- un comando --- */
.lista { display: flex; flex-direction: column; gap: 22px; margin-top: 22px; }

.paso h3 {
  font-size: .97rem;
  font-weight: 600;
  line-height: 1.4;
  margin: 0 0 7px;
  text-wrap: balance;
}

.paso .bloque + .bloque { margin-top: 8px; }

.bloque {
  background: var(--superficie);
  border: 1px solid var(--linea);
  border-radius: 8px;
  box-shadow: var(--sombra);
  overflow: hidden;
}

.barra {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 6px 5px 12px;
  background: var(--consola);
  border-bottom: 1px solid var(--linea);
}

.prompt {
  font-family: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  font-size: .78rem;
  color: var(--suave);
}

.copiar {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 4px 12px;
  border: 1px solid var(--linea);
  border-radius: 6px;
  background: var(--superficie);
  color: var(--acento);
  font: inherit;
  font-size: .84rem;
  font-weight: 500;
  cursor: pointer;
}
.copiar:hover { border-color: var(--acento); }
.copiar[data-hecho="si"] { color: var(--ok); border-color: var(--ok); }
.copiar svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; }

code.comando {
  display: block;
  padding: 12px;
  font-family: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  font-size: .8rem;
  line-height: 1.65;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

code.linea {
  font-family: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  font-size: .88em;
  background: var(--consola);
  border: 1px solid var(--linea);
  border-radius: 4px;
  padding: .05em .3em;
}

.explicacion { color: var(--suave); font-size: .93rem; margin: 0; }
.explicacion strong { color: var(--tinta); font-weight: 600; }

/* --- pie --- */
.pie {
  margin-top: 48px;
  padding-top: 16px;
  border-top: 1px solid var(--linea);
  color: var(--suave);
  font-size: .8rem;
}
.pie p { margin: 0 0 4px; }

:focus-visible { outline: 2px solid var(--acento); outline-offset: 2px; border-radius: 4px; }

@media (prefers-reduced-motion: no-preference) {
  .copiar { transition: color .15s, border-color .15s; }
  .salto { transition: color .15s, border-color .15s; }
  html { scroll-behavior: smooth; }
}
"""

GUION = """
const ICONO_COPIAR = document.getElementById('icono-copiar').innerHTML;
const ICONO_HECHO = document.getElementById('icono-hecho').innerHTML;
const aviso = document.getElementById('aviso');

async function alPortapapeles(texto) {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch (error) {
    // Navegadores viejos, o sin permiso: el camino de siempre.
    const caja = document.createElement('textarea');
    caja.value = texto;
    caja.setAttribute('readonly', '');
    caja.style.position = 'fixed';
    caja.style.opacity = '0';
    document.body.appendChild(caja);
    caja.select();
    let listo = false;
    try { listo = document.execCommand('copy'); } catch (e) { listo = false; }
    document.body.removeChild(caja);
    return listo;
  }
}

document.querySelectorAll('.copiar').forEach((boton) => {
  const comando = document.getElementById(boton.dataset.para).textContent;
  // El ícono se pinta ya: la página tiene que verse terminada apenas carga.
  boton.querySelector('.icono').innerHTML = ICONO_COPIAR;
  boton.addEventListener('click', async () => {
    const listo = await alPortapapeles(comando);
    boton.dataset.hecho = listo ? 'si' : 'no';
    boton.querySelector('.icono').innerHTML = listo ? ICONO_HECHO : ICONO_COPIAR;
    boton.querySelector('.texto').textContent = listo ? 'Copiado' : 'Copiá a mano';
    aviso.textContent = listo ? 'Comando copiado' : 'No se pudo copiar: seleccionalo a mano';
    clearTimeout(boton.reloj);
    boton.reloj = setTimeout(() => {
      boton.dataset.hecho = 'no';
      boton.querySelector('.icono').innerHTML = ICONO_COPIAR;
      boton.querySelector('.texto').textContent = 'Copiar';
    }, 2200);
  });
});
"""


def armar(titulo: str, intro: list[str], secciones: list[Seccion]) -> str:
    partes: list[str] = []
    partes.append('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    partes.append(
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        "family=Archivo:wght@600;700&family=IBM+Plex+Mono:wght@400;500&"
        'family=IBM+Plex+Sans:wght@400;500;600&display=swap">'
    )
    partes.append(f"<title>Comandos Centonara</title>\n<style>{ESTILO}</style>")

    partes.append(
        '<template id="icono-copiar"><svg viewBox="0 0 24 24" aria-hidden="true">'
        '<rect x="9" y="9" width="12" height="12" rx="2"/>'
        '<path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg></template>'
    )
    partes.append(
        '<template id="icono-hecho"><svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="m4 12.5 5.2 5.2L20 7"/></svg></template>'
    )

    partes.append('<div class="hoja">')
    partes.append('<header class="tapa">')
    partes.append(f"<h1>{con_formato(titulo)}</h1>")
    for parrafo in intro:
        partes.append(f'<p class="entrada">{con_formato(parrafo)}</p>')
    partes.append("</header>")

    partes.append('<nav class="saltos" aria-label="Ir a una computadora"><ul>')
    for seccion in secciones:
        partes.append(
            f'<li><a class="salto" href="#{id_de(seccion.titulo)}">'
            f"{html.escape(seccion.titulo.split(' (')[0])}</a></li>"
        )
    partes.append("</ul></nav>")

    for seccion in secciones:
        consola = seccion.consola
        partes.append(f'<section class="maquina" id="{id_de(seccion.titulo)}"><header>')
        partes.append(f"<h2>{con_formato(seccion.titulo)}</h2>")
        if consola:
            partes.append(f'<span class="donde">{html.escape(consola[0])}</span>')
        partes.append("</header>")
        if seccion.nota:
            partes.append(f'<p class="nota">{con_formato(seccion.nota)}</p>')

        partes.append('<div class="lista">')
        for numero, item in enumerate(seccion.items):
            partes.append('<article class="paso">')
            partes.append(f"<h3>{con_formato(item.titulo)}</h3>")
            prompt = CONSOLAS.get(item.lenguaje, ("", "$"))[1]
            for orden, comando in enumerate(item.comandos):
                identificador = f"{id_de(seccion.titulo)}-{numero}-{orden}"
                partes.append('<div class="bloque"><div class="barra">')
                partes.append(f'<span class="prompt">{html.escape(prompt)}</span>')
                partes.append(
                    f'<button class="copiar" type="button" data-para="{identificador}">'
                    '<span class="icono"></span><span class="texto">Copiar</span></button>'
                )
                partes.append("</div>")
                partes.append(
                    f'<code class="comando" id="{identificador}">'
                    f"{html.escape(comando)}</code></div>"
                )
            if item.texto:
                partes.append(f'<p class="explicacion">{con_formato(item.texto)}</p>')
            partes.append("</article>")
        partes.append("</div></section>")

    partes.append('<footer class="pie">')
    partes.append(f"<p>{html.escape(sello())}</p>")
    partes.append(
        "<p>La versión que manda es la del repositorio, no esta página. "
        "Si la fecha quedó vieja, se regenera con <code class='linea'>docs/generar-web.py</code>.</p>"
    )
    partes.append("</footer></div>")

    partes.append('<p id="aviso" role="status" aria-live="polite" class="visually-hidden"></p>')
    partes.append(
        "<style>.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;"
        "clip:rect(0 0 0 0);white-space:nowrap}</style>"
    )
    partes.append(f"<script>{GUION}</script>")
    return "\n".join(partes)


def main() -> None:
    parser = argparse.ArgumentParser(description="El .md de comandos a una página web.")
    parser.add_argument(
        "--origen", type=pathlib.Path, default=RAIZ / "docs" / "COMANDOS-MAQUINAS.md"
    )
    args = parser.parse_args()

    origen = args.origen.resolve()
    destino = origen.with_suffix(".html")
    titulo, intro, secciones = leer(origen)
    destino.write_text(armar(titulo, intro, secciones), encoding="utf-8")
    total = sum(s.cuantos_comandos for s in secciones)
    print(f"Web: {destino}  ({len(secciones)} computadoras, {total} comandos)")


if __name__ == "__main__":
    main()
