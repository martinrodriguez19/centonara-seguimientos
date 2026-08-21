"""`LISTAR`: leer chats, y desconfiar de lo que vuelve.

El modelo puede devolver un chat sin nombre, una antigüedad negativa, o un
teléfono que se inventó. Nada de eso puede llegar al backend como si fuera un
dato bueno — y nada puede desaparecer en silencio, que es la otra mitad.
"""

from __future__ import annotations

from pathlib import Path

from agente.jobs.claude_code import Invocacion
from agente.jobs.listar import listar

CARPETA = Path(__file__).resolve().parents[1]
BIN = r"C:\claude.exe"
DEVICE = "f83d5f3e-3278-46c6-8ccc-148e58805116"
RUN = "6a8865306c710de7c9c9a757"


def chat(**cambios):
    base = {
        "contacto_nombre": "Corralón San Justo",
        "contacto_telefono": "+5491123231151",
        "ultimo_mensaje_resumen": "preguntó por hierro del 8",
        "ultimo_lo_mando": "contacto",
        "antiguedad_dias": 6,
    }
    base.update(cambios)
    return base


def responde(datos, **extra):
    """Un invocador falso que contesta lo que se le diga."""
    guardado = {}

    async def invocador(prompt, **kwargs):
        guardado["prompt"] = prompt
        guardado.update(kwargs)
        return Invocacion(True, datos=datos, raw="crudo", **extra)

    invocador.visto = guardado
    return invocador


async def correr(invocador, **cambios):
    argumentos = {
        "n_chats": 5,
        "run_id": RUN,
        "device_id": DEVICE,
        "claude_bin": BIN,
        "carpeta": CARPETA,
        "invocador": invocador,
    }
    argumentos.update(cambios)
    return await listar(**argumentos)


# ---------------------------------------------------------------------------
# El camino feliz
# ---------------------------------------------------------------------------


async def test_lee_los_chats_y_los_devuelve_normalizados() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": [chat()]}, costo_usd=0.4)
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.detalle["leidos"] == 1
    assert resultado.costo_usd == 0.4

    leido = resultado.detalle["chats"][0]
    #  El payload del backend habla de `vendedor`; el prompt, de `yo`. La
    #  traducción se hace acá y no en el backend.
    assert leido["quien_hablo_ultimo"] == "contacto"
    assert leido["contacto_telefono"] == "+5491123231151"


async def test_yo_se_traduce_a_vendedor() -> None:
    invocador = responde({"status": "ok", "chats": [chat(ultimo_lo_mando="yo")]})
    resultado = await correr(invocador)

    assert resultado.detalle["chats"][0]["quien_hablo_ultimo"] == "vendedor"


async def test_el_prompt_lleva_el_device_id_de_esta_maquina() -> None:
    """Problema #5: con más de un Chrome conectado, headless elige cualquiera."""
    invocador = responde({"status": "ok", "chats": []})
    await correr(invocador)

    assert DEVICE in invocador.visto["prompt"]
    assert invocador.visto["con_navegador"] is True


async def test_sin_device_id_no_se_invoca_nada() -> None:
    """Falla cerrado: "cualquiera" puede ser el Chrome de otra persona."""
    invocador = responde({"status": "ok", "chats": []})
    resultado = await correr(invocador, device_id="")

    assert not resultado.ok
    assert "device" in str(resultado.detalle).lower()
    assert "prompt" not in invocador.visto


async def test_el_n_chats_tiene_una_cota_dura() -> None:
    invocador = responde({"status": "ok", "chats": []})
    await correr(invocador, n_chats=9999)

    assert "50" in invocador.visto["prompt"]
    assert "9999" not in invocador.visto["prompt"]


# ---------------------------------------------------------------------------
# Un teléfono que no se pudo leer NO es un error
# ---------------------------------------------------------------------------


async def test_un_telefono_nulo_se_conserva_como_nulo() -> None:
    """⚠️ El prompt pide explícitamente no deducirlo.

    Un número inventado acá termina en un mensaje comercial a otra persona. Que
    venga `null` es la respuesta correcta, y quien decide qué hacer con ese chat
    es el triage del backend, no este módulo.
    """
    invocador = responde({"status": "ok", "chats": [chat(contacto_telefono=None)]})
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.detalle["chats"][0]["contacto_telefono"] is None
    assert resultado.detalle["sin_telefono"] == 1


# ---------------------------------------------------------------------------
# Lo que vuelve mal
# ---------------------------------------------------------------------------


async def test_un_chat_mal_formado_se_descarta_y_se_cuenta() -> None:
    """Descartar sin contar sería un cliente sin mensaje y nadie sabe por qué."""
    invocador = responde(
        {
            "status": "ok",
            "chats": [chat(), chat(contacto_nombre=""), chat(antiguedad_dias="ayer")],
        }
    )
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.detalle["leidos"] == 1
    assert len(resultado.detalle["descartados"]) == 2
    assert any("contacto_nombre" in d for d in resultado.detalle["descartados"])


async def test_una_antiguedad_negativa_no_pasa() -> None:
    invocador = responde({"status": "ok", "chats": [chat(antiguedad_dias=-3)]})
    resultado = await correr(invocador)

    assert resultado.detalle["leidos"] == 0


async def test_un_quien_hablo_inventado_no_pasa() -> None:
    invocador = responde({"status": "ok", "chats": [chat(ultimo_lo_mando="el sistema")]})
    resultado = await correr(invocador)

    assert resultado.detalle["leidos"] == 0


async def test_la_sesion_caida_tiene_su_propio_codigo() -> None:
    invocador = responde({"status": "error", "motivo": "sesion_no_iniciada", "detalle": "pide QR"})
    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.codigo == "SESION_CAIDA"


async def test_un_navegador_no_disponible_se_reporta() -> None:
    invocador = responde({"status": "error", "motivo": "browser_no_disponible"})
    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.detalle["motivo"] == "browser_no_disponible"


async def test_una_respuesta_de_otra_corrida_no_se_usa() -> None:
    """Si el `run_id` no coincide, eso no es de esta corrida."""
    invocador = responde({"run_id": "otra-cosa", "status": "ok", "chats": [chat()]})
    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.detalle["esperado"] == RUN


async def test_un_status_inesperado_no_se_toma_por_bueno() -> None:
    invocador = responde({"status": "casi", "chats": []})
    assert not (await correr(invocador)).ok


async def test_sin_lista_de_chats_es_fallo() -> None:
    invocador = responde({"status": "ok"})
    assert not (await correr(invocador)).ok


async def test_un_fallo_de_la_invocacion_se_propaga_con_su_codigo() -> None:
    async def invocador(prompt, **kwargs):
        return Invocacion(False, codigo="TIMEOUT", detalle={"segundos": 600}, raw="a medias")

    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.codigo == "TIMEOUT"
    assert resultado.raw == "a medias"
