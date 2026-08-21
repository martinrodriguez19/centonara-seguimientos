"""La sonda: los dos chequeos que sólo se contestan abriendo el navegador.

`permiso_sitio` y `whatsapp_sesion` salen `n/a` en el diagnóstico porque no se
pueden verificar leyendo archivos. Se intentó: el permiso de sitio **no queda
registrado** en el almacenamiento de la extensión, así que buscarlo ahí da
siempre lo mismo esté o no esté concedido. Usarlo es la única forma de saber.
"""

from __future__ import annotations

from pathlib import Path

from agente.jobs.claude_code import Invocacion
from agente.sonda import probar

CARPETA = Path(__file__).resolve().parents[1]
BIN = r"C:\claude.exe"
DEVICE = "f83d5f3e-3278-46c6-8ccc-148e58805116"


def responde(datos, **extra):
    guardado = {}

    async def invocador(prompt, **kwargs):
        guardado["prompt"] = prompt
        guardado.update(kwargs)
        return Invocacion(True, datos=datos, raw="crudo", **extra)

    invocador.visto = guardado
    return invocador


async def correr(invocador, **cambios):
    argumentos = {
        "device_id": DEVICE,
        "claude_bin": BIN,
        "carpeta": CARPETA,
        "invocador": invocador,
    }
    argumentos.update(cambios)
    return await probar(**argumentos)


async def test_con_permiso_y_sesion_pasa() -> None:
    invocador = responde(
        {"status": "ok", "sesion_iniciada": True, "chats_visibles": 9}, costo_usd=0.43
    )
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.chats_visibles == 9
    assert resultado.costo_usd == 0.43
    assert "permiso_sitio" in resultado.como_texto()


async def test_va_por_el_mismo_camino_que_listar() -> None:
    """Si la sonda pasa, `LISTAR` va a poder llegar. Ese es todo el valor."""
    invocador = responde({"status": "ok", "sesion_iniciada": True, "chats_visibles": 1})
    await correr(invocador)

    assert invocador.visto["con_navegador"] is True
    assert DEVICE in invocador.visto["prompt"]


async def test_no_le_pide_leer_ningun_chat() -> None:
    """En la máquina donde se prueba esto, la línea suele ser la personal."""
    invocador = responde({"status": "ok", "sesion_iniciada": True, "chats_visibles": 1})
    await correr(invocador)

    prompt = invocador.visto["prompt"]
    assert "NO leas el contenido de ningun chat" in prompt
    assert "NO abras ningun chat" in prompt


async def test_sin_permiso_lo_dice_con_todas_las_letras() -> None:
    invocador = responde(
        {"status": "error", "motivo": "sin_permiso", "detalle": "requires permission"}
    )
    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.motivo == "sin_permiso"
    assert "permiso de sitio" in resultado.como_texto()


async def test_llegar_a_la_pagina_sin_sesion_no_es_lo_mismo_que_no_llegar() -> None:
    """El permiso está y la sesión no. Son dos arreglos distintos."""
    invocador = responde({"status": "ok", "sesion_iniciada": False, "chats_visibles": 0})
    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.motivo == "sesion_no_iniciada"
    assert "QR" in resultado.como_texto()


async def test_un_device_id_que_no_esta_conectado_se_distingue() -> None:
    invocador = responde({"status": "error", "motivo": "browser_no_disponible"})
    resultado = await correr(invocador)

    assert not resultado.ok
    assert "deviceId" in resultado.como_texto()


async def test_sin_device_id_ni_se_invoca() -> None:
    invocador = responde({"status": "ok", "sesion_iniciada": True})
    resultado = await correr(invocador, device_id="")

    assert not resultado.ok
    assert "prompt" not in invocador.visto


async def test_un_fallo_de_la_invocacion_se_reporta_con_su_codigo() -> None:
    async def invocador(prompt, **kwargs):
        return Invocacion(False, codigo="TIMEOUT", detalle={"motivo": "tardó"}, raw="a medias")

    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.motivo == "TIMEOUT"


async def test_un_conteo_ilegible_no_rompe_nada() -> None:
    invocador = responde({"status": "ok", "sesion_iniciada": True, "chats_visibles": "varios"})
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.chats_visibles == 0
