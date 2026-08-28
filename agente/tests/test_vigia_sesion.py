"""Tests de la vigía de la sesión dedicada.

Lo que se prueba es la honestidad del chequeo: sólo afirma `ok` o `falla`
cuando vio la lista o el QR con sus propios ojos; todo tropiezo transitorio es
`n/a` — una alerta de "re-vincular" disparada por red lenta enseñaría a
ignorar la alerta de verdad.
"""

from __future__ import annotations

from agente import diagnostico, vigia_sesion
from agente.adaptadores.simulada import Chat, PaginaSimulada
from agente.bucle import Estado as EstadoBucle


def abrir(pagina: PaginaSimulada):
    async def _abrir():
        return pagina

    return _abrir


# ---------------------------------------------------------------------------
# Una revisión
# ---------------------------------------------------------------------------


async def test_con_sesion_activa_reporta_ok() -> None:
    pagina = PaginaSimulada({"x": Chat(nombre="X", telefono="+5491100000001")})

    chequeo = await vigia_sesion.revisar_sesion(abrir(pagina))

    assert chequeo.nombre == "whatsapp_sesion"
    assert chequeo.estado is diagnostico.Estado.OK
    assert pagina.navegada, "la vigía navega antes de preguntar, como el motor"


async def test_con_el_qr_a_la_vista_reporta_falla_y_dice_que_hacer() -> None:
    """Es la alerta que le llega al panel: tiene que traer la acción."""
    chequeo = await vigia_sesion.revisar_sesion(abrir(PaginaSimulada(sesion=False)))

    assert chequeo.estado is diagnostico.Estado.FALLA
    assert "--vincular" in chequeo.detalle


async def test_una_pagina_que_no_carga_no_es_una_sesion_caida() -> None:
    """Transitorio: afirmar `falla` acá dispararía la alerta sin necesidad."""
    chequeo = await vigia_sesion.revisar_sesion(abrir(PaginaSimulada(carga=False)))

    assert chequeo.estado is diagnostico.Estado.NO_APLICA


async def test_un_navegador_que_revienta_no_tira_la_vigia() -> None:
    async def revienta():
        raise RuntimeError("Chrome no abre")

    chequeo = await vigia_sesion.revisar_sesion(revienta)

    assert chequeo.estado is diagnostico.Estado.NO_APLICA
    assert "Chrome no abre" in chequeo.detalle


# ---------------------------------------------------------------------------
# El bucle de la vigía
# ---------------------------------------------------------------------------


async def test_vigilar_deja_el_resultado_donde_lo_lee_el_latido() -> None:
    """El latido manda `estado.diagnostico`: ahí tiene que quedar lo visto."""
    estado = EstadoBucle()
    pagina = PaginaSimulada(sesion=False)

    hechas = await vigia_sesion.vigilar(abrir(pagina), estado, vueltas=1)

    assert hechas == 1
    assert estado.diagnostico.a_dict()["whatsapp_sesion"] == "falla"


async def test_vigilar_reemplaza_el_na_del_diagnostico_de_arranque() -> None:
    base = diagnostico.Diagnostico(
        (
            diagnostico.Chequeo("claude_bin", diagnostico.Estado.OK),
            diagnostico.Chequeo("whatsapp_sesion", diagnostico.Estado.NO_APLICA, "vigía pendiente"),
        )
    )
    estado = EstadoBucle(diagnostico=base)
    pagina = PaginaSimulada({"x": Chat(nombre="X", telefono="+5491100000001")})

    await vigia_sesion.vigilar(abrir(pagina), estado, vueltas=1)

    resultado = estado.diagnostico.a_dict()
    assert resultado["whatsapp_sesion"] == "ok"
    assert resultado["claude_bin"] == "ok", "los demás chequeos no se tocan"


# ---------------------------------------------------------------------------
# `con_chequeo`
# ---------------------------------------------------------------------------


def test_con_chequeo_agrega_si_el_nombre_no_estaba() -> None:
    """Un diagnóstico vacío de arranque no pierde lo que la vigía averiguó."""
    nuevo = diagnostico.con_chequeo(
        diagnostico.Diagnostico(),
        diagnostico.Chequeo("whatsapp_sesion", diagnostico.Estado.OK),
    )

    assert nuevo.a_dict() == {"whatsapp_sesion": "ok"}
