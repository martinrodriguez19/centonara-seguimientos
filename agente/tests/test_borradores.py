"""`BORRADORES`: el pase único, y desconfiar de lo que vuelve.

Lo que estos tests custodian es distinto de `LISTAR` en un punto: acá el
reporte describe **hechos consumados** — borradores que ya están escritos en
los chats del vendedor. Un chat mal reportado que se cae en silencio puede ser
un borrador real que el panel nunca va a conocer, y un `texto_enviado` es la
tarea fallando de la única forma grave que tiene: hay que verlo con nombre
propio, con lo parcial preservado.
"""

from __future__ import annotations

from pathlib import Path

from agente.jobs.borradores import dejar_borradores
from agente.jobs.claude_code import Invocacion

CARPETA = Path(__file__).resolve().parents[1]
BIN = r"C:\claude.exe"
DEVICE = "f83d5f3e-3278-46c6-8ccc-148e58805116"
RUN = "6a8865306c710de7c9c9a757"


def visitado(**cambios):
    base = {
        "contacto_nombre": "Corralón San Justo",
        "contacto_telefono": "+5491123231151",
        "ultimo_mensaje_resumen": "preguntó por hierro del 8",
        "ultimo_lo_mando": "contacto",
        "antiguedad_dias": 6,
        "borrador_dejado": True,
        "texto_borrador": "Hola, quedó pendiente lo del hierro del 8. ¿Seguimos?",
        "motivo": None,
    }
    base.update(cambios)
    return base


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
        "n_chats": 6,
        "run_id": RUN,
        "device_id": DEVICE,
        "claude_bin": BIN,
        "carpeta": CARPETA,
        "invocador": invocador,
    }
    argumentos.update(cambios)
    return await dejar_borradores(**argumentos)


# ---------------------------------------------------------------------------
# El camino feliz
# ---------------------------------------------------------------------------


async def test_una_tanda_buena_vuelve_normalizada() -> None:
    invocador = responde(
        {
            "run_id": RUN,
            "status": "ok",
            "fin_de_ventana": False,
            "chats": [visitado(), visitado(contacto_nombre="Pinturería Sur")],
        },
        costo_usd=0.8,
    )
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.detalle["visitados"] == 2
    assert resultado.detalle["dejados"] == 2
    assert resultado.detalle["fin_de_ventana"] is False
    assert resultado.costo_usd == 0.8


async def test_un_salteado_viaja_con_su_motivo() -> None:
    invocador = responde(
        {
            "run_id": RUN,
            "status": "ok",
            "chats": [
                visitado(),
                visitado(
                    contacto_nombre="Ferretería Sur",
                    borrador_dejado=False,
                    texto_borrador=None,
                    motivo="campo_ocupado",
                ),
            ],
        }
    )
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.detalle["dejados"] == 1
    assert resultado.detalle["salteados"] == 1
    salteado = resultado.detalle["chats"][1]
    assert salteado["borrador_dejado"] is False
    assert salteado["motivo"] == "campo_ocupado"


async def test_un_motivo_desconocido_se_guarda_como_otro() -> None:
    """No se pierde, pero tampoco se deja que el modelo invente vocabulario."""
    invocador = responde(
        {
            "run_id": RUN,
            "status": "ok",
            "chats": [visitado(borrador_dejado=False, texto_borrador=None, motivo="me aburrí")],
        }
    )
    resultado = await correr(invocador)

    assert resultado.detalle["chats"][0]["motivo"] == "otro"


async def test_fin_de_ventana_pasa_tal_cual() -> None:
    """Lo dice el modelo, no lo deduce nadie contando: una tanda corta por
    tiempo no es lo mismo que una ventana agotada."""
    invocador = responde(
        {"run_id": RUN, "status": "ok", "fin_de_ventana": True, "chats": [visitado()]}
    )

    assert (await correr(invocador)).detalle["fin_de_ventana"] is True


# ---------------------------------------------------------------------------
# Desconfiar de la respuesta
# ---------------------------------------------------------------------------


async def test_dejado_sin_texto_se_degrada_y_no_se_registra_un_texto_fantasma() -> None:
    """«Dejé un borrador» sin decir cuál es contradictorio: no se puede
    registrar un texto que no se conoce. Se degrada a no-dejado con motivo
    propio, para que una persona revise ese chat."""
    invocador = responde({"run_id": RUN, "status": "ok", "chats": [visitado(texto_borrador="   ")]})
    resultado = await correr(invocador)

    assert resultado.ok
    chat = resultado.detalle["chats"][0]
    assert chat["borrador_dejado"] is False
    assert chat["motivo"] == "reporte_sin_texto"
    assert resultado.detalle["dejados"] == 0


async def test_un_chat_sin_nombre_se_descarta_y_se_cuenta() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": [visitado(contacto_nombre="")]})
    resultado = await correr(invocador)

    assert resultado.ok
    assert resultado.detalle["visitados"] == 0
    assert len(resultado.detalle["descartados"]) == 1


async def test_un_ok_sin_lista_de_chats_es_un_error_no_una_tanda_vacia() -> None:
    """⚠️ Si esto pasara como éxito, el backend lo leería como «no queda nada»,
    terminaría la corrida en verde con cero borradores, y nadie se enteraría."""
    invocador = responde({"run_id": RUN, "status": "ok"})
    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.codigo == "ERROR_INESPERADO"
    assert "no trae la lista" in resultado.detalle["motivo"]


async def test_una_tanda_con_muchos_salteados_no_se_trunca() -> None:
    """Truncar el reporte podría tirar un borrador que SÍ quedó en WhatsApp."""
    muchos = [
        visitado(
            contacto_nombre=f"Contacto {i}",
            borrador_dejado=False,
            texto_borrador=None,
            motivo="campo_ocupado",
        )
        for i in range(30)
    ] + [visitado()]
    invocador = responde({"run_id": RUN, "status": "ok", "chats": muchos})
    resultado = await correr(invocador)

    assert resultado.detalle["visitados"] == 31
    assert resultado.detalle["dejados"] == 1, "el dejado del final no se perdió"


async def test_un_run_id_ajeno_no_se_usa() -> None:
    invocador = responde({"run_id": "otro", "status": "ok", "chats": [visitado()]})
    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.codigo == "ERROR_INESPERADO"


async def test_sin_device_id_no_se_abre_ningun_navegador() -> None:
    resultado = await correr(responde({}), device_id="")

    assert not resultado.ok
    assert "deviceId" in resultado.detalle["motivo"]


# ---------------------------------------------------------------------------
# texto_enviado: la falla grave, con lo parcial preservado
# ---------------------------------------------------------------------------


async def test_texto_enviado_corta_con_codigo_propio() -> None:
    invocador = responde(
        {
            "run_id": RUN,
            "status": "error",
            "motivo": "texto_enviado",
            "detalle": "en el chat de Corralón San Justo",
            "chats": [visitado()],
        }
    )
    resultado = await correr(invocador)

    assert not resultado.ok
    assert resultado.codigo == "TEXTO_ENVIADO"
    #  Lo dejado antes del error viaja igual: son borradores que YA están en
    #  los chats y el backend los tiene que registrar.
    assert len(resultado.detalle["chats"]) == 1
    assert "Corralón" in resultado.detalle["detalle"]


async def test_la_sesion_caida_se_reporta_como_siempre() -> None:
    invocador = responde({"run_id": RUN, "status": "error", "motivo": "sesion_no_iniciada"})

    assert (await correr(invocador)).codigo == "SESION_CAIDA"


# ---------------------------------------------------------------------------
# Lo que viaja en el prompt: las listas son datos (R3)
# ---------------------------------------------------------------------------


async def test_las_listas_del_backend_van_al_prompt() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(
        invocador,
        ya_vistos=["Corralón San Justo"],
        no_escribir=["Pinturería Sur"],
    )

    prompt = invocador.visto["prompt"]
    assert "- Corralón San Justo" in prompt
    assert "- Pinturería Sur" in prompt
    assert invocador.visto["con_navegador"] is True


async def test_con_numeros_permitidos_el_prompt_restringe() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, solo_numeros=["+5491123231151"])

    prompt = invocador.visto["prompt"]
    assert "+5491123231151" in prompt
    assert "fuera_de_lista" in prompt


async def test_sin_numeros_el_prompt_no_restringe() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador)

    assert "ninguna: cualquier chat" in invocador.visto["prompt"]


async def test_el_contexto_de_la_empresa_viaja_una_vez_por_tanda() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, contexto_empresa="Vendemos hierro y chapa. Tono directo.")

    prompt = invocador.visto["prompt"]
    assert "Vendemos hierro y chapa" in prompt
    assert "<<INDICACIONES DEL DUEÑO>>" in prompt


# ---------------------------------------------------------------------------
# Las dos estrategias (D27)
# ---------------------------------------------------------------------------


async def test_por_defecto_recorre_de_arriba_hacia_abajo() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, antiguedad_min_dias=7, antiguedad_max_dias=90)

    prompt = invocador.visto["prompt"]
    assert "entre 7 y 90 dias" in prompt
    assert "desde arriba hacia abajo" in prompt
    assert "BARRIDO DEL HISTORIAL" not in prompt


async def test_el_barrido_va_al_fondo_y_avanza_hacia_hoy() -> None:
    """Lo que pidió el dueño: los más viejos primero, igual que el circuito
    viejo, con el cursor de la máquina marcando hasta dónde se llegó."""
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, estrategia="barrido", barrido_hasta_dias=84)

    prompt = invocador.visto["prompt"]
    assert "BARRIDO DEL HISTORIAL" in prompt
    assert "HASTA EL FONDO" in prompt
    assert "84 dias o menos" in prompt
    assert "MAS VIEJO AL MAS" in prompt and "NUEVO" in prompt
    #  La ventana de antigüedad no manda en barrido: es su propia selección.
    assert "entre 0 y 3650 dias" not in prompt


async def test_las_variables_del_bloque_de_recorrido_se_rellenan() -> None:
    """El bloque de estrategia trae `{{N_CHATS}}` adentro: si no se sustituye,
    el modelo recibe la llave literal y no sabe cuántos dejar."""
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, n_chats=5, estrategia="barrido", barrido_hasta_dias=120)

    prompt = invocador.visto["prompt"]
    assert "{{" not in prompt, "quedó una variable sin rellenar"
    assert "5 borradores" in prompt


async def test_el_prompt_prohibe_enviar() -> None:
    """La regla que hace que esto sea «dejar borradores» y no otra cosa."""
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador)

    prompt = invocador.visto["prompt"]
    assert "NUNCA aprietes enviar" in prompt
    assert "Enter" in prompt
