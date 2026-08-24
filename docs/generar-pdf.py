"""El SOP a PDF, para imprimir o mandarle a alguien.

Se corre así, desde la raíz del repositorio:

    uv run --project agente --with markdown python docs/generar-pdf.py

Usa el Chromium que ya trae Playwright para el motor de envío, así que no hay
que instalar nada más.

El PDF **no se versiona**. Un PDF en el repositorio queda viejo apenas alguien
toca el `.md`, y este proyecto ya arrastra un SOP anterior que sigue circulando
diciendo cosas que dejaron de ser ciertas. Por eso cada página lleva la fecha y
el commit: para que un papel viejo se delate solo.
"""

import asyncio
import pathlib
import sys

import markdown

RAIZ = pathlib.Path(r"C:\Users\Usuario\Desktop\centonara-seguimientos")
ORIGEN = RAIZ / "docs" / "SOP-instalar-mac.md"
SALIDA = RAIZ / "docs" / "SOP-instalar-mac.pdf"

ESTILO = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }

:root {
  --tinta: #1a1a1a;
  --suave: #5b5b5b;
  --linea: #e0e0e0;
  --fondo-codigo: #f6f6f4;
  --acento: #8a5a00;
}

* { box-sizing: border-box; }

body {
  font-family: -apple-system, "Segoe UI", Inter, system-ui, sans-serif;
  font-size: 10.5pt;
  line-height: 1.55;
  color: var(--tinta);
  margin: 0;
}

/* Cada parte arranca en página nueva: se imprime y se reparte por partes. */
h1 { font-size: 19pt; margin: 0 0 .6em; letter-spacing: -.02em; }
h1 + * { margin-top: 0; }
h1:not(:first-of-type) { page-break-before: always; padding-top: .2em; }

h2 {
  font-size: 13pt;
  margin: 1.6em 0 .5em;
  padding-bottom: .25em;
  border-bottom: 1px solid var(--linea);
  page-break-after: avoid;
}
h3 { font-size: 11pt; margin: 1.2em 0 .4em; page-break-after: avoid; }

p, ul, ol, table { margin: .55em 0; }
li { margin: .25em 0; }

/* Un bloque de comandos no se parte a la mitad de la página. */
pre {
  background: var(--fondo-codigo);
  border: 1px solid var(--linea);
  border-radius: 5px;
  padding: .7em .9em;
  overflow-x: auto;
  page-break-inside: avoid;
  font-size: 9pt;
  line-height: 1.45;
}
code {
  font-family: "SF Mono", Consolas, "Cascadia Mono", monospace;
  font-size: .92em;
}
:not(pre) > code {
  background: var(--fondo-codigo);
  border: 1px solid var(--linea);
  border-radius: 3px;
  padding: .08em .32em;
}

table { border-collapse: collapse; width: 100%; font-size: 9.5pt; page-break-inside: avoid; }
th, td { border: 1px solid var(--linea); padding: .42em .6em; text-align: left; vertical-align: top; }
th { background: var(--fondo-codigo); font-weight: 600; }

/* Una tabla sin encabezados —las hay, y a proposito— no tiene por que mostrar
   una banda gris vacia arriba. */
thead:not(:has(th:not(:empty))) { display: none; }

blockquote {
  margin: .9em 0;
  padding: .5em .9em;
  border-left: 3px solid var(--acento);
  background: #fdf9f0;
  color: #3a3a3a;
  page-break-inside: avoid;
}
blockquote p { margin: .35em 0; }

hr { border: 0; border-top: 1px solid var(--linea); margin: 1.6em 0; }

strong { font-weight: 600; }
a { color: inherit; text-decoration: none; }

.pie {
  margin-top: 2.5em;
  padding-top: .8em;
  border-top: 1px solid var(--linea);
  font-size: 8.5pt;
  color: var(--suave);
}
"""


def sello() -> str:
    """De cuándo es este PDF, y de qué commit.

    Un PDF impreso no tiene forma de saber que quedó viejo. Este proyecto ya
    arrastra un SOP anterior que sigue circulando y dice cosas que dejaron de
    ser ciertas; que el papel diga su fecha y su commit es lo mínimo para que
    alguien pueda darse cuenta.
    """
    import subprocess
    from datetime import date

    try:
        commit = subprocess.run(
            ["git", "-C", str(RAIZ), "log", "-1", "--format=%h %ad", "--date=short"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
    except Exception:
        commit = "sin datos de git"
    return f"Generado el {date.today():%d/%m/%Y} desde el commit {commit}"


def construir_html() -> str:
    texto = ORIGEN.read_text(encoding="utf-8")
    cuerpo = markdown.markdown(
        texto,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Instalar el agente en la Mac de un vendedor</title>
<style>{ESTILO}</style></head>
<body>
{cuerpo}
<p class="pie">
  Sistema de Seguimiento Comercial · <code>docs/SOP-instalar-mac.md</code><br>
  {sello()}<br>
  <strong>La versión que manda es la del repositorio, no este PDF.</strong> Si la fecha de arriba
  quedó vieja, volvé a generarlo: <code>docs/generar-pdf.py</code>
</p>
</body></html>"""


async def main() -> None:
    from playwright.async_api import async_playwright

    html = construir_html()
    tmp = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("sop.html")
    tmp.write_text(html, encoding="utf-8")

    async with async_playwright() as p:
        navegador = await p.chromium.launch()
        pagina = await navegador.new_page()
        await pagina.goto(tmp.resolve().as_uri(), wait_until="networkidle")
        await pagina.pdf(
            path=str(SALIDA),
            format="A4",
            print_background=True,
            margin={"top": "18mm", "bottom": "20mm", "left": "16mm", "right": "16mm"},
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=(
                '<div style="width:100%;font-size:8pt;color:#888;'
                'padding:0 16mm;display:flex;justify-content:space-between">'
                f"<span>Instalar el agente en la Mac de un vendedor · {sello()}</span>"
                '<span class="pageNumber"></span></div>'
            ),
        )
        await navegador.close()

    print(f"PDF: {SALIDA}  ({SALIDA.stat().st_size // 1024} KB)")


asyncio.run(main())
