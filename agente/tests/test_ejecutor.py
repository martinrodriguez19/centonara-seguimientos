"""El despachador: que cada job vaya a donde tiene que ir.

Hasta la fase 3 el bucle se construía sin ejecutor y todo job caía en el "no sé
hacer eso". Estos tests son los que impiden volver ahí sin darse cuenta.
"""

from __future__ import annotations

from pathlib import Path

from agente.cliente import Job
from agente.diagnostico import Chequeo, Diagnostico, Estado
from agente.jobs import ejecutor

CARPETA = Path(__file__).resolve().parents[1]


def sano() -> Diagnostico:
    return Diagnostico([Chequeo("claude_bin", Estado.OK, "ok", "MVP #2")])


def roto() -> Diagnostico:
    return Diagnostico([Chequeo("device_id", Estado.FALLA, "sin deviceId", "MVP #5")])


def construir(
    *, modo: str = "simulado", diagnosticar=sano, claude_bin: str = "", asegurar_navegador=None
):
    return ejecutor.construir(
        claude_bin=claude_bin,
        device_id="dev-1",
        carpeta=CARPETA,
        modo=modo,
        diagnosticar=diagnosticar,
        asegurar_navegador=asegurar_navegador,
    )


async def test_un_tipo_desconocido_se_reporta_y_no_revienta() -> None:
    """Un job que nadie reporta queda colgado y el panel no dice por qué."""
    resultado = await construir()(Job("1", "BAILAR", {}))

    assert resultado["ok"] is False
    assert "BAILAR" in str(resultado["detalle"])


async def test_diagnostico_sano_reporta_ok() -> None:
    resultado = await construir()(Job("1", "DIAGNOSTICO", {}))

    assert resultado["ok"] is True
    assert resultado["detalle"] == {"claude_bin": "ok"}


async def test_diagnostico_degradado_reporta_fallo_con_el_detalle() -> None:
    """El panel muestra qué chequeo falló, no un error genérico."""
    resultado = await construir(diagnosticar=roto)(Job("1", "DIAGNOSTICO", {}))

    assert resultado["ok"] is False
    assert resultado["detalle"] == {"device_id": "falla"}


async def test_sin_el_chrome_del_vendedor_no_se_le_paga_a_ningun_modelo() -> None:
    """⚠️ La extensión vive en el Chrome del vendedor: si él lo cerró con Cmd+Q,
    no hay extensión para nadie.

    Sin esto, `LISTAR` gasta la llamada al modelo para que descubra que no hay
    navegador y vuelva con `browser_no_disponible` — y la cola lo reintenta
    tres veces. El motivo además tiene que decir qué hacer.
    """

    class NoSePudo:
        utilizable = False
        detalle = "no se encontró el ejecutable de Chrome"

    llamadas = {"veces": 0}

    async def asegurar():
        llamadas["veces"] += 1
        return NoSePudo()

    resultado = await construir(modo="real", asegurar_navegador=asegurar)(
        Job("1", "LISTAR", {"n_chats": 5, "run_id": "r1"})
    )

    assert resultado["ok"] is False
    assert "Chrome" in resultado["detalle"]["motivo"]
    assert llamadas["veces"] == 1
    #  Y no se llegó a invocar al modelo: `claude_bin` está vacío, así que si
    #  hubiera seguido, el motivo sería otro.
    assert "CLAUDE_BIN" not in str(resultado["detalle"])


def job_enviar(destinos=None, **cambios) -> Job:
    """Un `ENVIAR` como lo entrega el backend, con lo vigente adjunto."""
    payload = {
        "mensaje_id": "m1",
        "contacto_id": "+5491123231151",
        "contacto_nombre": "Corralón San Justo",
        "texto": "Hola, ¿seguimos?",
    }
    payload.update(cambios)
    return Job(
        "1",
        "ENVIAR",
        payload,
        vigente={} if destinos is None else {"destinos_permitidos": destinos},
    )


async def test_en_modo_real_no_se_envia_con_los_selectores_sin_verificar(monkeypatch) -> None:
    """⚠️ El guard sigue vivo aunque hoy `VERIFICADO` tenga fecha (25/8/2026).

    El día que WhatsApp cambie y una recalibración vuelva la fecha a `None`,
    el envío real se tiene que bloquear solo, sin que nadie se acuerde de nada.
    Esto es lo que lo garantiza.
    """
    monkeypatch.setattr(ejecutor.selectores, "VERIFICADO", None)
    resultado = await construir(modo="real")(job_enviar(["+5491123231151"]))

    assert resultado["ok"] is False
    assert resultado["codigo"] == "SELECTOR_ROTO"
    assert "nunca se verificaron" in resultado["detalle"]["motivo"]


async def test_en_simulado_el_motor_corre_contra_la_pagina_en_memoria() -> None:
    """Una máquina recién instalada recorre la cola sin tocar ningún navegador."""
    resultado = await construir(modo="simulado")(job_enviar(["+5491123231151"]))

    #  La página simulada no tiene ese chat, así que el motor aborta por eso —
    #  que es lo correcto— y no por falta de navegador.
    assert resultado["codigo"] == "CHAT_NO_ABRE"


async def test_sin_destinos_vigentes_no_se_escribe_a_nadie() -> None:
    """⚠️ R4, segunda verificación.

    Si el backend no manda la lista, o la manda vacía, el agente no escribe. La
    ausencia no habilita: significa a nadie, igual que en el backend.
    """
    for job in (job_enviar(None), job_enviar([])):
        resultado = await construir(modo="simulado")(job)
        assert resultado["codigo"] == "DESTINO_NO_PERMITIDO"


async def test_un_destino_que_no_esta_en_la_lista_vigente_se_rechaza() -> None:
    """La lista viene del backend al ENTREGAR el job, no al encolarlo.

    Es lo que hace que cerrarla desde el panel tenga efecto sobre un mensaje que
    ya estaba encolado.
    """
    resultado = await construir(modo="simulado")(job_enviar(["+5491199990000"]))

    assert resultado["codigo"] == "DESTINO_NO_PERMITIDO"


async def test_sin_forma_de_abrir_el_navegador_lo_dice(monkeypatch) -> None:
    """Si nadie inyectó `abrir_pagina`, el motivo lo tiene que decir claro."""
    monkeypatch.setattr(ejecutor.selectores, "VERIFICADO", "2026-08-24")

    resultado = await construir(modo="real")(job_enviar(["+5491123231151"]))

    assert resultado["ok"] is False
    assert "navegador" in resultado["detalle"]["motivo"]


async def test_en_modo_real_usa_la_pagina_que_le_dan(monkeypatch) -> None:
    """El despachador no sabe de dónde sale el navegador, y no tiene por qué."""
    from agente.adaptadores.simulada import Chat, PaginaSimulada

    monkeypatch.setattr(ejecutor.selectores, "VERIFICADO", "2026-08-24")
    falsa = PaginaSimulada(
        {"+5491123231151": Chat(nombre="Corralón San Justo", telefono="+5491123231151")}
    )

    async def abrir():
        return falsa

    ejecutar = ejecutor.construir(
        claude_bin="",
        device_id="dev-1",
        carpeta=CARPETA,
        modo="real",
        diagnosticar=sano,
        abrir_pagina=abrir,
    )
    resultado = await ejecutar(job_enviar(["+5491123231151"], modo="real"))

    assert resultado["ok"] is True
    assert falsa.enviados == [("+5491123231151", "Hola, ¿seguimos?")]


async def test_listar_llega_a_su_ejecutor(monkeypatch) -> None:
    visto = {}

    async def falso(**kwargs):
        visto.update(kwargs)

        class R:
            def a_reporte(self):
                return {"ok": True, "codigo": None, "detalle": {"leidos": 3}}

        return R()

    monkeypatch.setattr(ejecutor.listar_job, "listar", falso)
    resultado = await construir()(Job("1", "LISTAR", {"n_chats": 7, "run_id": "abc"}))

    assert resultado["detalle"]["leidos"] == 3
    assert visto["n_chats"] == 7
    assert visto["run_id"] == "abc"
    assert visto["device_id"] == "dev-1"


async def test_redactar_llega_a_su_ejecutor(monkeypatch) -> None:
    visto = {}

    async def falso(**kwargs):
        visto.update(kwargs)

        class R:
            def a_reporte(self):
                return {"ok": True, "codigo": None, "detalle": {"status": "ok"}}

        return R()

    monkeypatch.setattr(ejecutor.redactar_job, "redactar", falso)
    await construir()(
        Job(
            "1",
            "REDACTAR",
            {
                "contacto_nombre": "Corralón",
                "resumen": "preguntó por hierro",
                "quien_hablo_ultimo": "vendedor",
                "antiguedad_dias": 4,
                "largo_maximo": 300,
            },
        )
    )

    assert visto["contacto_nombre"] == "Corralón"
    assert visto["quien_hablo_ultimo"] == "vendedor"
    assert visto["largo_maximo"] == 300


async def test_un_payload_incompleto_usa_los_valores_por_defecto(monkeypatch) -> None:
    """El backend valida al encolar; acá igual no se cae por una clave que falta."""
    visto = {}

    async def falso(**kwargs):
        visto.update(kwargs)

        class R:
            def a_reporte(self):
                return {"ok": True, "codigo": None, "detalle": {}}

        return R()

    monkeypatch.setattr(ejecutor.listar_job, "listar", falso)
    await construir()(Job("1", "LISTAR", {}))

    assert visto["n_chats"] == 20
