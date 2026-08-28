"""Qué pasa en WhatsApp Web **mientras** se busca un contacto.

El verificador de selectores saca su radiografía cuando la búsqueda ya falló y
la espera expiró: para entonces la lista puede haber vuelto a su estado normal,
y lo que se ve no es lo que el agente vio. Esta herramienta mira segundo a
segundo desde que se escribe el término, que es donde está la diferencia entre
«WhatsApp no encontró nada» y «el agente miró el lugar equivocado».

No escribe ningún mensaje ni abre ningún chat: escribe en el buscador y observa.

    uv run --directory agente python herramientas/probar_busqueda.py "Aubete"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agente.adaptadores import conexion, selectores
from agente.config import obtener_configuracion

SEGUNDOS = 15


async def main() -> int:
    if len(sys.argv) < 2:
        print('Falta qué buscar. Ejemplo: ... probar_busqueda.py "Aubete"')
        return 2
    termino = sys.argv[1]

    from playwright.async_api import async_playwright

    config = obtener_configuracion()
    playwright = await async_playwright().start()
    try:
        pagina = await conexion.conectar_perfil(
            playwright,
            carpeta=conexion.carpeta_dedicada(config.navegador_dir),
            chrome_bin=config.chrome_bin,
        )
        await pagina.goto(selectores.URL, wait_until="domcontentloaded")
        print("Esperando a que cargue la lista de chats...")
        await pagina.wait_for_selector(selectores.LISTA_DE_CHATS.css, timeout=60_000)
        await asyncio.sleep(3)

        cuantos = await pagina.locator(selectores.RESULTADO_DE_BUSQUEDA.css).count()
        print(f"Antes de buscar, la lista muestra {cuantos} elementos.\n")

        buscador = pagina.locator(selectores.BUSCADOR.css).first
        await buscador.click(timeout=15_000)
        await pagina.keyboard.press("ControlOrMeta+A")
        await pagina.keyboard.press("Delete")
        await buscador.press_sequentially(termino, delay=20)
        print(f"Escrito: {termino!r}. Mirando qué pasa cada segundo:\n")

        for segundo in range(1, SEGUNDOS + 1):
            await asyncio.sleep(1)
            filas = pagina.locator(selectores.RESULTADO_DE_BUSQUEDA.css)
            total = await filas.count()
            textos = []
            for i in range(min(total, 3)):
                try:
                    crudo = (await filas.nth(i).inner_text(timeout=1_000)) or ""
                except Exception:
                    crudo = "(no se pudo leer)"
                textos.append(" ".join(crudo.split())[:60])
            print(f"  {segundo:2d}s  elementos={total:<3}  {' | '.join(textos)}")

        valor = await buscador.input_value(timeout=5_000)
        print(f"\nEl buscador quedó con: {valor!r}")
        print(
            "\nCómo leerlo:\n"
            "  · Si el número BAJA y aparece el contacto  -> la búsqueda anda y el\n"
            "    agente esperaba poco: hay que darle más tiempo.\n"
            "  · Si el número NO cambia nunca             -> WhatsApp no ejecutó la\n"
            "    búsqueda: el texto entra pero no dispara el filtrado.\n"
            "  · Si baja a 0 y se queda en 0              -> buscó y no encontró: ese\n"
            "    chat no está en ESTA sesión."
        )
        return 0
    finally:
        await playwright.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
