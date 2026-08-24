"""El adaptador real de WhatsApp Web, contra un Chromium de verdad.

Corre `whatsapp_web.py` —el mismo código que va a tocar el chat de un cliente—
sobre una página con la estructura que sus selectores esperan. Lo que se prueba
es **la lógica**: que busque y abra el chat correcto, que lea el header, que
resuelva el número o admita que no puede, que escriba literal, y que un aborto
deje el campo vacío.

⚠️ **Esto no prueba que WhatsApp Web se vea así hoy.** Los selectores siguen sin
verificar contra una sesión real (`selectores.VERIFICADO is None`). Alguien
podría mirar estos tests en verde y concluir que el envío funciona; lo que
funciona es el adaptador.

Necesitan el navegador bajado: `uv run playwright install chromium`.
"""

from __future__ import annotations

import pytest
from pagina_falsa import ChatFalso, html

from agente.adaptadores.pagina import ErrorDeSelector, Pagina
from agente.adaptadores.whatsapp_web import PaginaWhatsApp, verificar_selectores
from agente.jobs.enviar import enviar

playwright = pytest.importorskip("playwright.async_api", reason="falta playwright")

CORRALON = ChatFalso(
    id="+5491123231151",
    header="Corralón San Justo",
    telefono_en_panel="+54 9 11 2323-1151",
)
SIN_AGENDAR = ChatFalso(id="+5491136007586", header="+54 9 11 3600-7586")
GRUPO = ChatFalso(id="obra-centro", header="Obra Centro", es_grupo=True)
ILEGIBLE = ChatFalso(id="+5491139273345", header="Pinturería Sur", telefono_en_panel=None)


@pytest.fixture
async def navegador():
    """Un Chromium de verdad.

    Si no está bajado se saltea **diciendo cómo bajarlo**. Un skip mudo acá es
    peor que en otros lados: son los tests de la parte que le escribe al chat de
    una persona, y alguien podría no notar que no corrieron.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except Exception as error:  # pragma: no cover — depende de la máquina
            pytest.skip(f"falta el navegador: `uv run playwright install chromium` ({error})")
        yield browser
        await browser.close()


async def abrir(navegador, chats, **opciones) -> PaginaWhatsApp:
    """Una página con el HTML de prueba, servida como `data:`."""
    contexto = await navegador.new_context()
    page = await contexto.new_page()
    await page.set_content(html(chats, **opciones))
    return PaginaWhatsApp(page, espera_ms=3000)


# ---------------------------------------------------------------------------
# El contrato
# ---------------------------------------------------------------------------


async def test_implementa_el_protocolo(navegador) -> None:
    """Si le falta un método, el motor revienta recién en producción."""
    assert isinstance(await abrir(navegador, [CORRALON]), Pagina)


def test_ningun_selector_vive_fuera_de_selectores_py() -> None:
    """Es una regla del proyecto: el día que WhatsApp cambie, se edita un archivo."""
    import pathlib
    import re

    fuente = (
        pathlib.Path(__file__).resolve().parents[1] / "agente" / "adaptadores" / "whatsapp_web.py"
    ).read_text(encoding="utf-8")

    #  Se mira sólo el código, no los comentarios ni el docstring.
    codigo = "\n".join(
        linea
        for linea in fuente.splitlines()
        if not linea.lstrip().startswith("#") and "div[" not in linea.split("#")[-1:][0][:0]
    )
    sospechosos = re.findall(r"""["'][^"']*\[data-testid[^"']*["']""", codigo)
    sospechosos += re.findall(r"""["'][^"']*div\[id=['"]?main[^"']*["']""", codigo)
    assert not sospechosos, f"selectores fuera de selectores.py: {sospechosos}"


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------


async def test_con_el_qr_a_la_vista_no_hay_sesion(navegador) -> None:
    pagina = await abrir(navegador, [], con_sesion=False)
    assert await pagina.sesion_iniciada() is False


async def test_con_la_lista_de_chats_hay_sesion(navegador) -> None:
    pagina = await abrir(navegador, [CORRALON])
    assert await pagina.sesion_iniciada() is True


# ---------------------------------------------------------------------------
# Buscar y abrir
# ---------------------------------------------------------------------------


async def test_abre_el_chat_que_se_busca(navegador) -> None:
    pagina = await abrir(navegador, [CORRALON, SIN_AGENDAR])

    assert await pagina.buscar_contacto("+5491123231151") is True
    assert await pagina.leer_header() == "Corralón San Justo"


async def test_un_contacto_que_no_esta_devuelve_False_y_no_lanza(navegador) -> None:
    """Que no exista es un dato del mundo, no que el DOM haya cambiado."""
    pagina = await abrir(navegador, [CORRALON])
    assert await pagina.buscar_contacto("+5491100000000") is False


async def test_una_busqueda_nueva_no_arrastra_la_anterior(navegador) -> None:
    """⚠️ Si el buscador no se limpia, se abre el chat del contacto anterior.

    Es de los errores que sólo aparecen en la segunda iteración de una corrida,
    cuando ya se mandó un mensaje.
    """
    pagina = await abrir(navegador, [CORRALON, SIN_AGENDAR])

    await pagina.buscar_contacto("+5491123231151")
    await pagina.buscar_contacto("+5491136007586")

    assert await pagina.leer_header() == "+54 9 11 3600-7586"


# ---------------------------------------------------------------------------
# Quién es — el paso que impide el peor error del sistema
# ---------------------------------------------------------------------------


async def test_lee_el_numero_del_header_cuando_no_esta_agendado(navegador) -> None:
    pagina = await abrir(navegador, [SIN_AGENDAR])
    await pagina.buscar_contacto("+5491136007586")

    assert await pagina.resolver_numero() == "+54 9 11 3600-7586"


async def test_abre_el_panel_para_un_contacto_agendado(navegador) -> None:
    """Con nombre en el header, el número sólo está en el panel de contacto."""
    pagina = await abrir(navegador, [CORRALON])
    await pagina.buscar_contacto("+5491123231151")

    assert await pagina.resolver_numero() == "+54 9 11 2323-1151"


async def test_si_no_hay_numero_devuelve_None_y_no_lo_deduce(navegador) -> None:
    """⚠️ El único comportamiento aceptable cuando no se sabe.

    Lo que sigue es una comparación de identidad. Un número aproximado acá es un
    mensaje comercial a otra persona.
    """
    pagina = await abrir(navegador, [ILEGIBLE])
    await pagina.buscar_contacto("+5491139273345")

    assert await pagina.resolver_numero() is None


async def test_un_grupo_se_reconoce(navegador) -> None:
    pagina = await abrir(navegador, [GRUPO])
    await pagina.buscar_contacto("obra-centro")

    assert await pagina.es_grupo() is True


async def test_una_persona_no_es_un_grupo(navegador) -> None:
    pagina = await abrir(navegador, [CORRALON])
    await pagina.buscar_contacto("+5491123231151")

    assert await pagina.es_grupo() is False


# ---------------------------------------------------------------------------
# Escribir
# ---------------------------------------------------------------------------


async def test_escribe_el_texto_literal(navegador) -> None:
    pagina = await abrir(navegador, [CORRALON])
    await pagina.buscar_contacto("+5491123231151")

    texto = "Hola, ¿confirmamos la cantidad de hierro del 8?"
    await pagina.escribir(texto)

    assert await pagina.campo_tiene_texto() is True
    assert (await pagina._page.inner_text("#campo")).strip() == texto


async def test_detecta_lo_que_el_vendedor_dejo_escrito(navegador) -> None:
    """Si hay algo en el campo, está usando ese chat en este momento."""
    ocupado = ChatFalso(id="+5491123231151", header="Corralón", borrador="estaba escribiendo")
    pagina = await abrir(navegador, [ocupado])
    await pagina.buscar_contacto("+5491123231151")

    assert await pagina.campo_tiene_texto() is True


async def test_limpiar_deja_el_campo_vacio(navegador) -> None:
    pagina = await abrir(navegador, [CORRALON])
    await pagina.buscar_contacto("+5491123231151")
    await pagina.escribir("algo")

    await pagina.limpiar_campo()

    assert await pagina.campo_tiene_texto() is False


async def test_enviar_lo_deja_en_el_hilo_y_se_confirma(navegador) -> None:
    pagina = await abrir(navegador, [CORRALON])
    await pagina.buscar_contacto("+5491123231151")
    await pagina.escribir("Hola, ¿seguimos?")

    await pagina.apretar_enviar()

    assert await pagina.confirmar_en_hilo("Hola, ¿seguimos?", timeout_s=3) is True


async def test_confirmar_algo_que_no_esta_devuelve_False_sin_lanzar(navegador) -> None:
    """`False` es "no pude verificar", que no es lo mismo que "no salió"."""
    pagina = await abrir(navegador, [CORRALON])
    await pagina.buscar_contacto("+5491123231151")

    assert await pagina.confirmar_en_hilo("nunca se escribió", timeout_s=1) is False


# ---------------------------------------------------------------------------
# El DOM cambió
# ---------------------------------------------------------------------------


async def test_sin_campo_de_texto_lanza_ErrorDeSelector(navegador) -> None:
    """⚠️ Esto frena la corrida entera, y por eso tiene que ser inconfundible.

    Que el campo de escritura no exista no es "este chat es raro": es que
    WhatsApp cambió, y los envíos siguientes van a fallar igual.
    """
    pagina = await abrir(navegador, [CORRALON], sin_campo_de_texto=True)
    await pagina.buscar_contacto("+5491123231151")

    with pytest.raises(ErrorDeSelector):
        await pagina.escribir("no debería llegar acá")


async def test_la_verificacion_de_selectores_pasa_contra_esta_pagina(navegador) -> None:
    pagina = await abrir(navegador, [CORRALON])
    revision = await verificar_selectores(pagina)

    assert revision.ok, revision.como_texto()


async def test_la_verificacion_falla_si_falta_la_lista_de_chats(navegador) -> None:
    """Sin las dos direcciones, no se sabe si la verificación verifica algo."""
    pagina = await abrir(navegador, [], con_sesion=False)
    revision = await verificar_selectores(pagina)

    assert not revision.ok
    assert "lista de chats" in revision.como_texto()


async def test_los_selectores_todavia_no_se_verificaron_contra_whatsapp() -> None:
    """Cuando alguien los verifique, este test cambia junto con la fecha.

    Existe para que nadie confunda "los tests pasan" con "esto anda contra
    WhatsApp Web".
    """
    from agente.adaptadores import selectores

    assert selectores.VERIFICADO is None, (
        "si ya se verificaron, actualizá este test y la fecha en selectores.py"
    )


# ---------------------------------------------------------------------------
# La secuencia entera, con el motor real
# ---------------------------------------------------------------------------


async def test_el_motor_completo_manda_al_contacto_correcto(navegador) -> None:
    """Los doce pasos de `jobs/enviar.py`, sobre el adaptador de verdad."""
    pagina = await abrir(navegador, [CORRALON, SIN_AGENDAR])

    resultado = await enviar(
        pagina,
        contacto_id="+5491123231151",
        contacto_nombre="Corralón San Justo",
        texto="Hola, ¿confirmamos la cantidad?",
        modo="real",
        destinos_permitidos=["+5491123231151"],
    )

    assert resultado.ok, resultado.detalle
    assert await pagina.confirmar_en_hilo("Hola, ¿confirmamos la cantidad?", timeout_s=3)


async def test_el_motor_aborta_si_el_numero_no_coincide_y_no_escribe_nada(navegador) -> None:
    """⚠️⚠️ El test más importante de este archivo.

    Se pide escribirle a un número, y el chat que se abre es de otro. El sistema
    tiene que abortar **y dejar el campo vacío**. Que el log diga "aborté" no
    alcanza: hay que ver que la pantalla quedó limpia.
    """
    confundido = ChatFalso(
        id="+5491123231151",
        header="Corralón San Justo",
        #  El panel dice OTRO número: el chat no es de quien creemos.
        telefono_en_panel="+54 9 11 9999-0000",
    )
    pagina = await abrir(navegador, [confundido])

    resultado = await enviar(
        pagina,
        contacto_id="+5491123231151",
        contacto_nombre="Corralón San Justo",
        texto="ESTO NO TIENE QUE SALIR",
        modo="real",
        destinos_permitidos=["+5491123231151"],
    )

    assert not resultado.ok
    assert resultado.codigo == "CONTACTO_NO_COINCIDE"
    #  Lo que de verdad importa: en el DOM no quedó nada escrito.
    assert await pagina.campo_tiene_texto() is False
    assert await pagina.confirmar_en_hilo("ESTO NO TIENE QUE SALIR", timeout_s=1) is False


async def test_el_motor_no_le_escribe_a_un_grupo(navegador) -> None:
    """El caso real: se busca un número y lo que se abre es un grupo."""
    grupo_con_ese_numero = ChatFalso(id="+5491123231151", header="Obra Centro", es_grupo=True)
    pagina = await abrir(navegador, [grupo_con_ese_numero])

    resultado = await enviar(
        pagina,
        contacto_id="+5491123231151",
        contacto_nombre="Obra Centro",
        texto="no",
        modo="real",
        destinos_permitidos=["+5491123231151"],
    )

    assert not resultado.ok
    assert resultado.codigo == "CONTACTO_NO_COINCIDE"
    assert await pagina.campo_tiene_texto() is False


async def test_en_modo_prueba_escribe_y_limpia_sin_enviar(navegador) -> None:
    """El modo prueba tiene que dejar la pantalla como la encontró."""
    pagina = await abrir(navegador, [CORRALON])

    resultado = await enviar(
        pagina,
        contacto_id="+5491123231151",
        contacto_nombre="Corralón San Justo",
        texto="mensaje de prueba",
        modo="prueba",
        destinos_permitidos=["+5491123231151"],
    )

    assert resultado.ok
    assert resultado.simulado is True
    assert await pagina.campo_tiene_texto() is False
    assert await pagina.confirmar_en_hilo("mensaje de prueba", timeout_s=1) is False


async def test_el_motor_no_escribe_a_un_destino_no_permitido(navegador) -> None:
    """R4, y ni siquiera llega a abrir el chat."""
    pagina = await abrir(navegador, [CORRALON])

    resultado = await enviar(
        pagina,
        contacto_id="+5491123231151",
        contacto_nombre="Corralón San Justo",
        texto="no",
        modo="real",
        destinos_permitidos=[],
    )

    assert not resultado.ok
    assert resultado.codigo == "DESTINO_NO_PERMITIDO"


def test_el_atajo_de_seleccionar_todo_sirve_en_macos() -> None:
    """⚠️ `Control+A` no selecciona todo en macOS, y macOS es donde esto corre.

    Lo agarró el CI, que prueba el agente en los tres sistemas. Los dos efectos
    de equivocarse:

    - El buscador no se limpia, la búsqueda anterior sigue puesta, y se abre el
      chat del contacto anterior. En una corrida, el segundo mensaje entra al
      chat del primero.
    - `limpiar_campo()` no borra, así que el modo prueba **deja el texto escrito
      en el chat del vendedor** — la trampa exacta que ese modo existe para no
      dejar.

    Este test no reemplaza al de macOS en CI: es para que quien lea el código
    entienda por qué no dice `Control`.
    """
    from agente.adaptadores import whatsapp_web

    assert whatsapp_web.SELECCIONAR_TODO == "ControlOrMeta+A"
    assert "Control+A" not in whatsapp_web.SELECCIONAR_TODO.replace("ControlOrMeta", "")
