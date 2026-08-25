"""Los dos comandos que preparan el navegador dedicado del motor de envío (D24).

`--vincular` — abre el navegador dedicado en WhatsApp Web y espera a que
alguien escanee el QR con el teléfono del vendedor. Es lo que crea la sesión
propia del motor, una vez por máquina — y de nuevo cuando expire.

`--verificar-selectores` — comprueba los selectores de `selectores.py` contra
el WhatsApp Web real de esa sesión. Sin `--chat` mira sólo los estructurales de
la pantalla inicial; con `--chat <número>` abre **ese** chat —elegir uno de
prueba, deliberadamente— y verifica también los del chat abierto: encabezado,
campo de texto, botón de enviar, resolución del número. Escribe un punto en el
campo para que aparezca el botón y lo borra antes de salir. **No envía nada.**

Los dos se corren a mano, en la Mac, con alguien mirando. Por eso imprimen a
stdout y no sólo al log — igual que la sonda.
"""

from __future__ import annotations

import asyncio

from agente.adaptadores import conexion, selectores
from agente.adaptadores.pagina import ErrorDeSelector
from agente.adaptadores.whatsapp_web import PaginaWhatsApp
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# Escanear un QR con el teléfono en la mano toma segundos; cinco minutos cubre
# ir a buscar el teléfono. Después de eso, mejor cortar y volver a correr.
ESPERA_VINCULACION_S = 300.0

# Lo que se escribe para que aparezca el botón de enviar. Un punto: si algo
# sale mal y queda, es lo más inocuo que puede quedar en un campo.
TEXTO_DE_PRUEBA = "."


async def _radiografia(pagina) -> str:
    """Qué hay de verdad en la página, cuando un selector no encuentra nada.

    Existe porque pasó: el buscador se buscó dos veces con anclas distintas y
    ninguna respondió. Adivinar una tercera es gastar una corrida de alguien;
    esto imprime los ids reales y todos los campos de escritura con sus
    atributos, y con eso el selector nuevo se escribe con evidencia.
    """
    datos = await pagina.evaluate(
        """(selectorResultados) => {
            const describir = (el, conTexto) => {
                const attrs = {};
                for (const a of el.attributes) {
                    attrs[a.name] = (a.value || '').slice(0, 70);
                }
                const ruta = [];
                let n = el;
                while (n && n.tagName && n.tagName !== 'BODY') {
                    ruta.unshift(n.tagName.toLowerCase() + (n.id ? '#' + n.id : ''));
                    n = n.parentElement;
                }
                const salida = { ruta: ruta.slice(-6).join(' > '), attrs };
                if (conTexto) {
                    salida.texto = (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 60);
                }
                return salida;
            };
            const candidatos = Array.from(document.querySelectorAll(
                "[contenteditable='true'], input, [role='textbox'], [role='searchbox']"
            ));
            const ids = Array.from(document.querySelectorAll('[id]'))
                .map((e) => e.id)
                .filter((id) => id && id.length < 30)
                .slice(0, 25);
            const resultados = Array.from(document.querySelectorAll(selectorResultados));
            const headers = Array.from(document.querySelectorAll('header'));
            return {
                ids,
                candidatos: candidatos.slice(0, 12).map((e) => describir(e, false)),
                resultados: resultados.slice(0, 6).map((e) => describir(e, true)),
                headers: headers.slice(0, 4).map((e) => describir(e, true)),
            };
        }""",
        selectores.RESULTADO_DE_BUSQUEDA.css,
    )
    lineas = ["RADIOGRAFÍA — para reanclar el selector con evidencia:"]
    lineas.append(f"  ids presentes: {', '.join(datos.get('ids', [])) or '(ninguno)'}")

    lineas.append("  campos de escritura:")
    for c in datos.get("candidatos", []) or [{"ruta": "(ninguno)", "attrs": {}}]:
        lineas.append(f"  · {c['ruta']}")
        if c["attrs"]:
            attrs = "  ".join(f"{k}={v!r}" for k, v in sorted(c["attrs"].items()))
            lineas.append(f"      {attrs}")

    lineas.append("  lo que matchea el selector de resultados (en orden, con su texto):")
    for r in datos.get("resultados", []) or [{"ruta": "(nada)", "attrs": {}, "texto": ""}]:
        lineas.append(f"  · {r['ruta']}  →  {r.get('texto', '')!r}")
        if r["attrs"]:
            attrs = "  ".join(f"{k}={v!r}" for k, v in sorted(r["attrs"].items()))
            lineas.append(f"      {attrs}")

    lineas.append("  <header> presentes:")
    for h in datos.get("headers", []) or [{"ruta": "(ninguno)", "attrs": {}, "texto": ""}]:
        lineas.append(f"  · {h['ruta']}  →  {h.get('texto', '')!r}")
        if h["attrs"]:
            attrs = "  ".join(f"{k}={v!r}" for k, v in sorted(h["attrs"].items()))
            lineas.append(f"      {attrs}")

    return "\n".join(lineas)


async def _radiografia_encabezado(pagina) -> str:
    """La anatomía del encabezado visible, cuando el título no se deja leer."""
    datos = await pagina.evaluate(
        """(cssHeader) => {
            const headers = Array.from(document.querySelectorAll(cssHeader));
            const h = headers.find((e) => e.offsetParent !== null) || headers[0];
            if (!h) return null;
            return Array.from(h.querySelectorAll('*')).slice(0, 30).map((el) => {
                const attrs = {};
                for (const a of el.attributes) attrs[a.name] = (a.value || '').slice(0, 50);
                return {
                    tag: el.tagName.toLowerCase(),
                    attrs,
                    texto: el.childElementCount === 0
                        ? (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 40)
                        : '',
                };
            });
        }""",
        selectores.HEADER.css,
    )
    if not datos:
        return "RADIOGRAFÍA del encabezado: no hay ninguno visible."
    lineas = ["RADIOGRAFÍA del encabezado — para reanclar el título:"]
    for el in datos:
        attrs = "  ".join(f"{k}={v!r}" for k, v in sorted(el["attrs"].items()))
        texto = f"  →  {el['texto']!r}" if el["texto"] else ""
        lineas.append(f"  · <{el['tag']}> {attrs}{texto}")
    return "\n".join(lineas)


async def _radiografia_telefono(pagina) -> str:
    """Dónde vive el teléfono en el DOM: todo elemento cuyo texto parezca uno."""
    datos = await pagina.evaluate(
        """() => {
            const patron = /\\+\\d[\\d\\s\\-().]{6,}\\d/;
            const hojas = Array.from(document.querySelectorAll('span, div'))
                .filter((el) => el.childElementCount === 0
                    && patron.test(el.innerText || ''));
            return hojas.slice(0, 8).map((el) => {
                const attrs = {};
                for (const a of el.attributes) attrs[a.name] = (a.value || '').slice(0, 50);
                const ruta = [];
                let n = el;
                while (n && n.tagName && n.tagName !== 'BODY') {
                    ruta.unshift(n.tagName.toLowerCase() + (n.id ? '#' + n.id : ''));
                    n = n.parentElement;
                }
                return {
                    ruta: ruta.slice(-7).join(' > '),
                    attrs,
                    texto: (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 40),
                };
            });
        }"""
    )
    if not datos:
        return (
            "RADIOGRAFÍA del teléfono: ningún elemento a la vista tiene un texto "
            "con forma de número. ¿Se abrió el panel del contacto?"
        )
    lineas = ["RADIOGRAFÍA del teléfono — para reanclar el panel de contacto:"]
    for el in datos:
        attrs = "  ".join(f"{k}={v!r}" for k, v in sorted(el["attrs"].items()))
        lineas.append(f"  · {el['ruta']}  →  {el['texto']!r}")
        if attrs:
            lineas.append(f"      {attrs}")
    return "\n".join(lineas)


async def _abrir(config):
    """El navegador dedicado, en WhatsApp Web, con Playwright ya arrancado."""
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    try:
        pagina = await conexion.conectar_perfil(
            playwright,
            carpeta=conexion.carpeta_dedicada(config.navegador_dir),
            chrome_bin=config.chrome_bin,
        )
    except Exception:
        await playwright.stop()
        raise
    await pagina.goto(selectores.URL, wait_until="domcontentloaded")
    return playwright, pagina


async def vincular(config, *, espera_s: float = ESPERA_VINCULACION_S) -> bool:
    """Deja al navegador dedicado con sesión de WhatsApp. `True` si quedó."""
    print("Abriendo el navegador del motor de envío...")
    playwright, pagina = await _abrir(config)
    whatsapp = PaginaWhatsApp(pagina)

    try:
        # La página tarda en decidirse entre el QR y la lista de chats.
        await asyncio.sleep(5)

        if await whatsapp.sesion_iniciada():
            print("Ya había una sesión iniciada. No hay nada que vincular.")
            return True

        print()
        print("En la ventana que se abrió va a aparecer un código QR.")
        print("Escanealo con el teléfono del vendedor:")
        print("  WhatsApp → Configuración → Dispositivos vinculados → Vincular")
        print()
        print(f"Espero hasta {espera_s / 60:.0f} minutos...")

        limite = asyncio.get_running_loop().time() + espera_s
        while asyncio.get_running_loop().time() < limite:
            if await whatsapp.sesion_iniciada():
                # Un respiro para que WhatsApp persista la sesión en la carpeta
                # antes de cerrarle el navegador.
                await asyncio.sleep(5)
                print()
                print("Listo: la sesión quedó vinculada y guardada.")
                print("El motor de envío la va a usar cada vez que tenga que escribir.")
                log.info("navegador_dedicado_vinculado")
                return True
            await asyncio.sleep(2)

        print()
        print("No se escaneó a tiempo. Volvé a correr --vincular cuando tengas")
        print("el teléfono a mano.")
        return False
    finally:
        await pagina.context.close()
        await playwright.stop()


async def verificar_selectores(config, *, chat: str = "") -> bool:
    """Los selectores, contra WhatsApp Web de verdad. `True` si todos responden."""
    print("Abriendo el navegador del motor de envío...")
    playwright, pagina = await _abrir(config)
    whatsapp = PaginaWhatsApp(pagina)
    todo_ok = True

    def marca(ok: bool, nombre: str, detalle: str) -> None:
        nonlocal todo_ok
        todo_ok = todo_ok and ok
        print(f"[{'OK ' if ok else 'MAL'}] {nombre:18} {detalle}")

    try:
        await asyncio.sleep(5)
        if not await whatsapp.sesion_iniciada():
            print()
            print("[MAL] sesión: WhatsApp está pidiendo el QR.")
            print("      Corré primero:  --vincular")
            return False

        print()
        revision = await selectores.verificar(pagina)
        for encontrado in revision.encontrados:
            marca(True, "estructural", encontrado)
        for faltante in revision.faltantes:
            marca(False, "estructural", faltante)

        if revision.faltantes:
            print()
            print(await _radiografia(pagina))
            return False

        if not chat:
            print()
            print("Los del chat abierto (encabezado, campo, botón de enviar) sólo se")
            print("pueden verificar abriendo uno. Volvé a correr con un número de")
            print("PRUEBA:  --verificar-selectores --chat +549XXXXXXXXXX")
            return todo_ok

        print()
        print(f"Abriendo el chat de prueba {chat}...")
        try:
            if not await whatsapp.buscar_contacto(chat):
                marca(
                    False,
                    "buscador",
                    f"la búsqueda de {chat} no abrió ningún chat (¿existe esa "
                    "conversación en esta sesión?)",
                )
                print()
                print(await _radiografia(pagina))
                return False
            marca(True, "buscador", "encontró el chat y lo abrió")

            titulo = await whatsapp.leer_header()
            marca(titulo is not None, "encabezado", titulo or "no se pudo leer el título")
            if titulo is None:
                print()
                print(await _radiografia_encabezado(pagina))

            numero = await whatsapp.resolver_numero()
            marca(
                numero is not None,
                "numero",
                numero or "no se pudo resolver el número del chat (clave para R1)",
            )
            if numero is None:
                # Para que la radiografía tenga algo que mirar: se intenta abrir
                # el panel del contacto clickeando el encabezado, que es el
                # mismo gesto que hace una persona.
                try:
                    await pagina.click(selectores.HEADER.css)
                    await asyncio.sleep(2)
                except Exception:
                    pass
                print()
                print(await _radiografia_telefono(pagina))

            # El panel del contacto —lo haya abierto resolver_numero o la
            # radiografía— tapa el campo de texto y se come los clicks. Escape
            # lo cierra; si no había nada abierto, no hace nada.
            await pagina.keyboard.press("Escape")
            await asyncio.sleep(1)

            es_grupo = await whatsapp.es_grupo()
            marca(
                not es_grupo,
                "grupo",
                "no es un grupo" if not es_grupo else "lo detectó como grupo",
            )

            # El botón de enviar recién aparece con texto en el campo. Se
            # escribe un punto y se borra: nada se envía.
            await whatsapp.escribir(TEXTO_DE_PRUEBA)
            try:
                boton = await pagina.query_selector(selectores.BOTON_ENVIAR.css)
                marca(boton is not None, "boton_enviar", selectores.BOTON_ENVIAR.que_busca)
            finally:
                await whatsapp.limpiar_campo()
            marca(True, "campo_texto", "se pudo escribir y borrar")
        except ErrorDeSelector as error:
            marca(False, "selector", str(error))
            print()
            print(await _radiografia(pagina))
            return False
        except Exception as error:
            # Un timeout de Playwright con traceback no le sirve a nadie: se
            # marca, se radiografía, y el texto completo queda en el log.
            log.error("verificacion_inesperado", error=str(error)[:500])
            marca(False, "inesperado", f"{type(error).__name__}: {str(error)[:160]}")
            print()
            print(await _radiografia(pagina))
            return False

        return todo_ok
    finally:
        await pagina.context.close()
        await playwright.stop()
        print()
        if todo_ok and chat:
            print("Todos los selectores responden contra WhatsApp Web real.")
            print("Falta el acto deliberado: fijar la fecha en")
            print("  agente/adaptadores/selectores.py  →  VERIFICADO")
            print("y con eso el despachador deja pasar envíos en modo real.")
        elif todo_ok:
            print("Los estructurales responden. Falta la pasada con --chat.")
