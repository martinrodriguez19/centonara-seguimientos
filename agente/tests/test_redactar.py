"""`REDACTAR`: el job frecuente, el que no abre el navegador.

Dos cosas se prueban acá y las dos son de plata o de criterio:

- Que no abra el navegador. Es uno por chat, contra uno por máquina de `LISTAR`.
- Que `sin_contexto` sea un **éxito**. Si se reportara como fallo, la cola lo
  reintentaría y el reintento daría exactamente lo mismo, gastando dinero para
  llegar a la misma conclusión.
"""

from __future__ import annotations

from pathlib import Path

from agente.jobs.claude_code import Invocacion
from agente.jobs.redactar import redactar

CARPETA = Path(__file__).resolve().parents[1]
BIN = r"C:\claude.exe"


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
        "contacto_nombre": "Corralón San Justo",
        "resumen": "preguntó por hierro del 8 y quedó en confirmar cantidad",
        "quien_hablo_ultimo": "contacto",
        "antiguedad_dias": 6,
        "largo_maximo": 600,
        "claude_bin": BIN,
        "carpeta": CARPETA,
        "invocador": invocador,
    }
    argumentos.update(cambios)
    return await redactar(**argumentos)


# ---------------------------------------------------------------------------
# Donde está el ahorro
# ---------------------------------------------------------------------------


async def test_no_pide_el_navegador() -> None:
    """⚠️ Sacar el job más frecuente del circuito del navegador es el proyecto."""
    invocador = responde({"status": "ok", "texto": "Hola, ¿confirmamos la cantidad?"})
    await correr(invocador)

    assert invocador.visto["con_navegador"] is False


async def test_veinte_borradores_siguen_sin_pedirlo() -> None:
    invocador = responde({"status": "ok", "texto": "Hola"})
    for _ in range(20):
        await correr(invocador)

    assert invocador.visto["con_navegador"] is False


# ---------------------------------------------------------------------------
# El contexto que se le pasa
# ---------------------------------------------------------------------------


async def test_el_contexto_del_chat_llega_al_prompt() -> None:
    invocador = responde({"status": "ok", "texto": "Hola"})
    await correr(invocador)

    prompt = invocador.visto["prompt"]
    assert "Corralón San Justo" in prompt
    assert "hierro del 8" in prompt
    assert "600" in prompt
    assert "{{" not in prompt


async def test_vendedor_se_dice_yo_en_el_prompt() -> None:
    """El payload habla del sistema; el prompt, de quien está mirando el chat."""
    invocador = responde({"status": "ok", "texto": "Hola"})
    await correr(invocador, quien_hablo_ultimo="vendedor")

    assert "lo mando:            yo" in invocador.visto["prompt"]


# ---------------------------------------------------------------------------
# Las respuestas
# ---------------------------------------------------------------------------


async def test_devuelve_el_texto_redactado() -> None:
    invocador = responde({"status": "ok", "texto": "  Hola, ¿seguimos?  "}, costo_usd=0.002)
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.detalle["texto"] == "Hola, ¿seguimos?"
    assert resultado.detalle["largo"] == 16
    assert resultado.costo_usd == 0.002


async def test_sin_contexto_es_un_exito_y_no_un_fallo() -> None:
    """⚠️ Reintentar esto sería pagar de nuevo por la misma conclusión.

    El prompt lo ofrece como alternativa a inventar un seguimiento genérico, y
    qué hacer con ese chat —apartarlo para que lo mire una persona— lo decide el
    backend.
    """
    invocador = responde({"status": "sin_contexto", "motivo": "es una charla personal"})
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.codigo is None
    assert resultado.detalle["status"] == "sin_contexto"
    assert "personal" in resultado.detalle["motivo"]


async def test_un_ok_sin_texto_se_contradice_y_no_pasa() -> None:
    invocador = responde({"status": "ok", "texto": "   "})
    resultado = await correr(invocador)

    assert not resultado.ok
    assert "sin texto" in str(resultado.detalle)


async def test_un_status_inesperado_no_se_toma_por_bueno() -> None:
    invocador = responde({"status": "listo", "texto": "Hola"})
    assert not (await correr(invocador)).ok


async def test_un_texto_largo_se_devuelve_entero() -> None:
    """No se recorta acá: el guardrail G3 del backend lo revisa (R3).

    Cortar un mensaje a la mitad sería peor que no mandarlo, y duplicar la
    política crea dos lugares donde puede aflojarse.
    """
    largo = "a" * 900
    invocador = responde({"status": "ok", "texto": largo})
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.detalle["texto"] == largo
    assert resultado.detalle["largo"] == 900


async def test_un_fallo_de_la_invocacion_se_propaga() -> None:
    async def invocador(prompt, **kwargs):
        return Invocacion(False, codigo="ERROR_INESPERADO", detalle={"motivo": "x"}, raw="crudo")

    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.raw == "crudo"
