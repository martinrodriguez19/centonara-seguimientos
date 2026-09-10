"""Un `.md` de docs/ a Word (`.docx`), para mandar por WhatsApp o mail.

Se corre así, desde la raíz del repositorio:

    uv run --project agente --with python-docx python docs/generar-docx.py \
        --origen docs/COMANDOS-MAQUINAS.md --titulo "Comandos por computadora"

**Por qué Word y no PDF para esto.** En un PDF, un comando que no entra en el
ancho de la hoja se ve en dos líneas y se **copia** con un salto de línea
adentro: pegado en una Terminal, se ejecuta a la mitad. Es exactamente el
problema que ya costó un 404 con la URL larga del instalador. En Word el corte
es visual y el texto sigue siendo una sola línea: se copia entero. Por eso el
documento que se reparte para copiar y pegar es éste, y el PDF
(`generar-pdf.py`) es el que se imprime.

Lee el mismo `.md` que el PDF, así los dos no se despegan. Entiende lo justo:
`# ` y `## `, bloques cercados con ``` , párrafos, `> ` y `---`.

El `.docx` **no se versiona**, por lo mismo que el PDF: queda viejo apenas
alguien toca el `.md`. Cada archivo lleva la fecha y el commit del que salió,
para que una copia vieja se delate sola.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
from datetime import date

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

RAIZ = pathlib.Path(__file__).resolve().parent.parent

TINTA = RGBColor(0x1A, 0x1A, 0x1A)
SUAVE = RGBColor(0x5B, 0x5B, 0x5B)
FONDO_CODIGO = "F2F2F0"
LINEA = "D9D9D9"
# Consolas está en Windows y en macOS reciente; Courier New es el respaldo que
# existe en todas partes. Si falta la primera, Word usa la segunda solo.
MONOESPACIADA = "Consolas"


def sello() -> str:
    """De cuándo es este archivo, y de qué commit."""
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


def _sombrear(parrafo, color: str) -> None:
    sombra = OxmlElement("w:shd")
    sombra.set(qn("w:val"), "clear")
    sombra.set(qn("w:fill"), color)
    parrafo._p.get_or_add_pPr().append(sombra)


def _recuadrar(parrafo, color: str) -> None:
    bordes = OxmlElement("w:pBdr")
    for lado in ("top", "left", "bottom", "right"):
        borde = OxmlElement(f"w:{lado}")
        borde.set(qn("w:val"), "single")
        borde.set(qn("w:sz"), "6")
        borde.set(qn("w:space"), "6")
        borde.set(qn("w:color"), color)
        bordes.append(borde)
    parrafo._p.get_or_add_pPr().append(bordes)


def _sin_autoajuste(documento: Document) -> None:
    """Que Word no "arregle" nada de lo que se pegue o se edite después.

    No cambia lo que ya está escrito —el archivo se genera, no se tipea— pero
    evita que alguien que abra el documento y toque una línea se lleve las
    comillas rectas convertidas en tipográficas. Un comando con `"` curvo no
    corre.
    """
    ajustes = documento.settings.element
    for etiqueta in ("w:noPunctuationKerning", "w:doNotAutofitConstrainedTables"):
        if ajustes.find(qn(etiqueta)) is None:
            ajustes.append(OxmlElement(etiqueta))


class Escritor:
    def __init__(self, titulo: str) -> None:
        self.doc = Document()
        _sin_autoajuste(self.doc)
        self._preparar_estilos()
        self._preparar_pagina(titulo)
        self.primera_seccion = True

    def _preparar_estilos(self) -> None:
        normal = self.doc.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(10.5)
        normal.font.color.rgb = TINTA
        normal.paragraph_format.space_after = Pt(6)

    def _preparar_pagina(self, titulo: str) -> None:
        seccion = self.doc.sections[0]
        for lado in ("left_margin", "right_margin"):
            setattr(seccion, lado, Pt(48))
        seccion.top_margin = Pt(48)
        seccion.bottom_margin = Pt(48)

        pie = seccion.footer.paragraphs[0]
        trazo = pie.add_run(f"{titulo} · {sello()}")
        trazo.font.size = Pt(7.5)
        trazo.font.color.rgb = SUAVE

    # -- piezas ------------------------------------------------------------
    def titulo_principal(self, texto: str) -> None:
        parrafo = self.doc.add_paragraph()
        trazo = parrafo.add_run(texto)
        trazo.bold = True
        trazo.font.size = Pt(17)
        parrafo.paragraph_format.space_after = Pt(10)

    def seccion(self, texto: str) -> None:
        """Un `# `: la computadora. Cada una arranca en hoja nueva."""
        parrafo = self.doc.add_paragraph()
        if not self.primera_seccion:
            parrafo.add_run().add_break(WD_BREAK.PAGE)
        self.primera_seccion = False
        trazo = parrafo.add_run(texto)
        trazo.bold = True
        trazo.font.size = Pt(14)
        trazo.font.color.rgb = TINTA
        parrafo.paragraph_format.space_before = Pt(4)
        parrafo.paragraph_format.space_after = Pt(2)
        _sombrear(parrafo, FONDO_CODIGO)
        parrafo.paragraph_format.keep_with_next = True

    def para_que_sirve(self, texto: str) -> None:
        """Un `## `: para qué sirve el comando que viene abajo."""
        parrafo = self.doc.add_paragraph()
        trazo = parrafo.add_run(texto)
        trazo.bold = True
        trazo.font.size = Pt(10.5)
        parrafo.paragraph_format.space_before = Pt(12)
        parrafo.paragraph_format.space_after = Pt(3)
        parrafo.paragraph_format.keep_with_next = True

    def comando(self, texto: str) -> None:
        """El comando, en una sola línea de verdad.

        ⚠️ Sin saltos propios: si no entra en el ancho, Word lo acomoda solo y
        al copiarlo sigue siendo una línea. Meter un `\\n` acá para que "se vea
        mejor" rompería justamente lo que este documento tiene que hacer.
        """
        parrafo = self.doc.add_paragraph()
        trazo = parrafo.add_run(texto)
        trazo.font.name = MONOESPACIADA
        trazo.font.size = Pt(9)
        parrafo.paragraph_format.space_before = Pt(2)
        parrafo.paragraph_format.space_after = Pt(8)
        parrafo.paragraph_format.left_indent = Pt(6)
        parrafo.paragraph_format.keep_together = True
        _sombrear(parrafo, FONDO_CODIGO)
        _recuadrar(parrafo, LINEA)

    def parrafo(self, texto: str, *, nota: bool = False) -> None:
        parrafo = self.doc.add_paragraph()
        # `**negrita**` y `` `código` `` en línea, que es todo lo que usa el .md.
        for trozo, clase in _partir_en_trozos(texto):
            trazo = parrafo.add_run(trozo)
            if clase == "negrita":
                trazo.bold = True
            elif clase == "codigo":
                trazo.font.name = MONOESPACIADA
                trazo.font.size = Pt(9.5)
            if nota:
                trazo.font.color.rgb = SUAVE
                if clase != "codigo":
                    trazo.font.size = Pt(9.5)
        if nota:
            parrafo.paragraph_format.left_indent = Pt(6)
            _recuadrar(parrafo, LINEA)

    def guardar(self, destino: pathlib.Path) -> None:
        self.doc.save(str(destino))


_TROZOS = re.compile(r"\*\*(.+?)\*\*|`(.+?)`")


def _partir_en_trozos(texto: str) -> list[tuple[str, str]]:
    partes: list[tuple[str, str]] = []
    ultimo = 0
    for encontrado in _TROZOS.finditer(texto):
        if encontrado.start() > ultimo:
            partes.append((texto[ultimo : encontrado.start()], "llano"))
        negrita, codigo = encontrado.groups()
        partes.append((negrita, "negrita") if negrita else (codigo, "codigo"))
        ultimo = encontrado.end()
    if ultimo < len(texto):
        partes.append((texto[ultimo:], "llano"))
    return partes or [(texto, "llano")]


def convertir(origen: pathlib.Path, destino: pathlib.Path, titulo: str) -> None:
    escritor = Escritor(titulo)
    lineas = origen.read_text(encoding="utf-8").splitlines()

    dentro_de_comando = False
    comando: list[str] = []
    parrafo: list[str] = []
    primer_titulo = True

    def cerrar_parrafo(nota: bool = False) -> None:
        if parrafo:
            escritor.parrafo(" ".join(parrafo), nota=nota)
            parrafo.clear()

    for linea in lineas:
        if linea.startswith("```"):
            if dentro_de_comando:
                #  Las líneas del bloque se unen con espacio: un comando de
                #  este documento es siempre uno solo. Los que en el .md están
                #  en bloques separados quedan separados acá también.
                escritor.comando(" ".join(l.strip() for l in comando if l.strip()))
                comando.clear()
            else:
                cerrar_parrafo()
            dentro_de_comando = not dentro_de_comando
            continue

        if dentro_de_comando:
            comando.append(linea)
            continue

        if not linea.strip() or linea.startswith("---"):
            cerrar_parrafo()
            continue

        if linea.startswith("> "):
            parrafo.append(linea[2:].strip())
            continue

        if linea.startswith("# "):
            cerrar_parrafo(nota=True)
            if primer_titulo:
                escritor.titulo_principal(linea[2:].strip())
                primer_titulo = False
            else:
                escritor.seccion(linea[2:].strip())
            continue

        if linea.startswith("## "):
            cerrar_parrafo()
            escritor.para_que_sirve(linea[3:].strip())
            continue

        parrafo.append(linea.strip())

    cerrar_parrafo()
    escritor.guardar(destino)


def main() -> None:
    parser = argparse.ArgumentParser(description="Un .md de docs/ a Word (.docx).")
    parser.add_argument(
        "--origen", type=pathlib.Path, default=RAIZ / "docs" / "COMANDOS-MAQUINAS.md"
    )
    parser.add_argument("--titulo", default="Comandos por computadora")
    args = parser.parse_args()

    origen = args.origen.resolve()
    destino = origen.with_suffix(".docx")
    convertir(origen, destino, args.titulo)
    print(f"Word: {destino}  ({destino.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
