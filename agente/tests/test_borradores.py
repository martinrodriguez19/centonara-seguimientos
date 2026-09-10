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


# ---------------------------------------------------------------------------
# La redacción con anclaje y las tres ramas (D40, D41)
# ---------------------------------------------------------------------------


async def test_el_anclaje_viaja_normalizado() -> None:
    """`tema` y `cita` son lo que permite saber si el modelo leyó (D40)."""
    invocador = responde(
        {
            "run_id": RUN,
            "status": "ok",
            "chats": [visitado(tema="  hierro del 8  ", cita="me pasas precio del hierro del 8?")],
        }
    )
    resultado = await correr(invocador)

    chat = resultado.detalle["chats"][0]
    assert chat["tema"] == "hierro del 8"
    assert chat["cita"] == "me pasas precio del hierro del 8?"


async def test_el_nivel_b_va_sin_tema_ni_cita_y_es_valido() -> None:
    """El nivel B es una respuesta correcta, no una falla: no se descarta."""
    invocador = responde({"run_id": RUN, "status": "ok", "chats": [visitado(tema=None, cita=None)]})
    resultado = await correr(invocador)

    assert resultado.ok
    chat = resultado.detalle["chats"][0]
    assert chat["borrador_dejado"] is True
    assert chat["tema"] is None
    assert chat["cita"] is None


async def test_la_cita_se_acota_a_ochenta_caracteres() -> None:
    """Es texto literal de un tercero: lo mínimo que sirve para verificar."""
    invocador = responde(
        {"run_id": RUN, "status": "ok", "chats": [visitado(tema="chapa", cita="x" * 300)]}
    )
    resultado = await correr(invocador)

    assert len(resultado.detalle["chats"][0]["cita"]) == 80


async def test_un_salteado_no_lleva_anclaje() -> None:
    invocador = responde(
        {
            "run_id": RUN,
            "status": "ok",
            "chats": [
                visitado(
                    borrador_dejado=False,
                    texto_borrador=None,
                    motivo="sin_tema",
                    tema="algo",
                    cita="algo",
                )
            ],
        }
    )
    resultado = await correr(invocador)

    chat = resultado.detalle["chats"][0]
    assert chat["tema"] is None
    assert chat["cita"] is None


async def test_el_post_venta_es_un_dejado_con_motivo_ya_compro() -> None:
    """D41: el mensaje queda, y la venta cerrada también queda dicha —es lo
    que veta al contacto para las corridas siguientes."""
    invocador = responde(
        {
            "run_id": RUN,
            "status": "ok",
            "chats": [
                visitado(
                    texto_borrador="Hola, vi que al final lo compraste. Te falto algo?",
                    motivo="ya_compro",
                )
            ],
        }
    )
    resultado = await correr(invocador)

    chat = resultado.detalle["chats"][0]
    assert chat["borrador_dejado"] is True
    assert chat["motivo"] == "ya_compro"
    assert resultado.detalle["dejados"] == 1


async def test_un_dejado_con_otro_motivo_no_lo_conserva() -> None:
    """Sólo el post-venta lleva motivo con borrador: cualquier otro es ruido."""
    invocador = responde(
        {"run_id": RUN, "status": "ok", "chats": [visitado(motivo="campo_ocupado")]}
    )
    resultado = await correr(invocador)

    assert resultado.detalle["chats"][0]["motivo"] is None


async def test_disconforme_y_ya_compro_son_motivos_conocidos() -> None:
    invocador = responde(
        {
            "run_id": RUN,
            "status": "ok",
            "chats": [
                visitado(
                    contacto_nombre="Enojado",
                    borrador_dejado=False,
                    texto_borrador=None,
                    motivo="disconforme",
                ),
                visitado(
                    contacto_nombre="Ya compró",
                    borrador_dejado=False,
                    texto_borrador=None,
                    motivo="ya_compro",
                ),
            ],
        }
    )
    resultado = await correr(invocador)

    motivos = [c["motivo"] for c in resultado.detalle["chats"]]
    assert motivos == ["disconforme", "ya_compro"]


# ---------------------------------------------------------------------------
# El corte de la tanda (D44)
# ---------------------------------------------------------------------------


async def test_el_corte_viaja_dentro_del_vocabulario() -> None:
    invocador = responde(
        {"run_id": RUN, "status": "ok", "corte": "tope_de_visitas", "chats": [visitado()]}
    )
    resultado = await correr(invocador)

    assert resultado.detalle["corte"] == "tope_de_visitas"
    assert resultado.detalle["fin_de_ventana"] is False


async def test_un_corte_inventado_se_vuelve_otro() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "corte": "me cansé", "chats": []})
    resultado = await correr(invocador)

    assert resultado.detalle["corte"] == "otro"


async def test_sin_corte_pero_con_fin_de_ventana_el_corte_es_ese() -> None:
    """Son el mismo hecho contado dos veces: el campo nuevo no contradice al viejo."""
    invocador = responde({"run_id": RUN, "status": "ok", "fin_de_ventana": True, "chats": []})
    resultado = await correr(invocador)

    assert resultado.detalle["corte"] == "fin_de_ventana"


# ---------------------------------------------------------------------------
# Lo que el prompt lleva de las reglas nuevas
# ---------------------------------------------------------------------------


async def test_el_techo_de_visitas_va_al_prompt_en_las_dos_estrategias() -> None:
    for estrategia in ("recientes", "barrido"):
        invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
        await correr(invocador, n_chats=8, max_visitas=20, estrategia=estrategia)

        prompt = invocador.visto["prompt"]
        assert "ABRISTE 20 chats" in prompt or "abrir 20" in prompt, estrategia
        assert "tope_de_visitas" in prompt
        assert "{{" not in prompt


async def test_el_techo_de_visitas_nunca_queda_debajo_de_la_tanda() -> None:
    """Pedir 8 borradores y prohibir abrir 8 chats sería una tanda imposible."""
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, n_chats=8, max_visitas=3)

    assert "ABRISTE 8 chats" in invocador.visto["prompt"]


async def test_las_frases_prohibidas_y_las_palabras_de_veto_viajan() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(
        invocador,
        frases_prohibidas=["sigue en pie", "quedo a disposicion"],
        palabras_veto=["no me interesa", "estafa"],
    )

    prompt = invocador.visto["prompt"]
    assert "- sigue en pie" in prompt
    assert "- quedo a disposicion" in prompt
    assert "- no me interesa" in prompt
    assert "- estafa" in prompt


async def test_el_post_venta_se_apaga_con_la_perilla() -> None:
    """Con la perilla en `false`, la venta cerrada no recibe nada (D41)."""
    activo = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(activo, mensaje_post_compra=True)
    apagado = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(apagado, mensaje_post_compra=False)

    assert "POST-VENTA" in activo.visto["prompt"]
    assert "POST-VENTA" not in apagado.visto["prompt"]
    assert '"ya_compro"' in apagado.visto["prompt"]


async def test_el_prompt_lleva_las_reglas_contables_y_los_dos_niveles() -> None:
    """Lo que convierte «tono cordial» en algo que se puede verificar (D40)."""
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador)

    prompt = invocador.visto["prompt"]
    assert "CERO signos de exclamacion" in prompt
    assert "Nivel A" in prompt and "Nivel B" in prompt
    assert "Si dudas entre A y B, es B" in prompt
    assert "DISCONFORME" in prompt and "VENTA CERRADA" in prompt
    assert "no solo el ultimo mensaje" in prompt


# ---------------------------------------------------------------------------
# De atrás para adelante, frenando en el mínimo (D43)
# ---------------------------------------------------------------------------


async def test_del_mas_viejo_hacia_hoy_dentro_de_la_ventana() -> None:
    """Lo que pidió el dueño: los más viejos primero, pero nada de menos de 21 días."""
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(
        invocador,
        orden="mas_viejos_primero",
        antiguedad_min_dias=21,
        antiguedad_max_dias=90,
        ventana_hasta_dias=60,
    )

    prompt = invocador.visto["prompt"]
    assert "DEL MAS VIEJO AL MAS NUEVO" in prompt
    assert "60 dias o menos" in prompt
    assert "MENOS de 21 dias es demasiado fresco" in prompt
    assert "BARRIDO DEL HISTORIAL" not in prompt
    assert "desde arriba hacia abajo" not in prompt
    assert "{{" not in prompt


async def test_el_cursor_de_la_ventana_nunca_pasa_del_maximo() -> None:
    """Si el dueño bajó la ventana después de la última tanda, manda la ventana."""
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(
        invocador,
        orden="mas_viejos_primero",
        antiguedad_min_dias=21,
        antiguedad_max_dias=90,
        ventana_hasta_dias=3650,
    )

    assert "90 dias o menos" in invocador.visto["prompt"]


async def test_el_orden_no_cambia_nada_en_barrido() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, estrategia="barrido", orden="mas_viejos_primero")

    assert "BARRIDO DEL HISTORIAL" in invocador.visto["prompt"]


async def test_ya_vistos_admite_ciento_veinte_nombres() -> None:
    """Con veinte por día y contando los salteados, sesenta se llenaban en un día."""
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, ya_vistos=[f"Visto {i:03d}" for i in range(130)])

    prompt = invocador.visto["prompt"]
    assert "- Visto 119" in prompt
    assert "- Visto 120" not in prompt


# ---------------------------------------------------------------------------
# No repetir números (D43)
# ---------------------------------------------------------------------------


async def test_los_numeros_a_no_escribir_van_al_prompt_con_su_regla() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, no_escribir_numeros=["+5491100000001", "+5491100000002"])

    prompt = invocador.visto["prompt"]
    assert "- +5491100000001" in prompt
    assert "- +5491100000002" in prompt
    assert '"numero_repetido"' in prompt


async def test_numero_repetido_es_un_motivo_conocido() -> None:
    invocador = responde(
        {
            "run_id": RUN,
            "status": "ok",
            "chats": [
                visitado(borrador_dejado=False, texto_borrador=None, motivo="numero_repetido")
            ],
        }
    )
    resultado = await correr(invocador)

    assert resultado.detalle["chats"][0]["motivo"] == "numero_repetido"


async def test_sin_oferta_el_prompt_es_identico_al_de_siempre() -> None:
    """La perilla nueva, vacía, no cambia ni una letra: preparado y apagado."""
    sin_parametro = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(sin_parametro)
    vacia = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(vacia, post_venta_ofrecer="   \n ")

    assert vacia.visto["prompt"] == sin_parametro.visto["prompt"]
    assert "ofreces" not in vacia.visto["prompt"]


async def test_con_oferta_el_post_venta_la_lleva_con_las_palabras_del_dueno() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, post_venta_ofrecer="10% en accesorios\n  hasta fin de mes")

    prompt = invocador.visto["prompt"]
    assert "POST-VENTA" in prompt
    assert "- 10% en accesorios hasta fin de mes" in prompt
    assert "Ni una palabra de la venta ya cerrada" in prompt
    assert "{{" not in prompt


async def test_con_el_post_venta_apagado_la_oferta_no_viaja() -> None:
    invocador = responde({"run_id": RUN, "status": "ok", "chats": []})
    await correr(invocador, mensaje_post_compra=False, post_venta_ofrecer="10% en accesorios")
    assert "10% en accesorios" not in invocador.visto["prompt"]
    assert "POST-VENTA" not in invocador.visto["prompt"]
