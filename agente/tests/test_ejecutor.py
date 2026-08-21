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


def construir(*, modo: str = "simulado", diagnosticar=sano, claude_bin: str = ""):
    return ejecutor.construir(
        claude_bin=claude_bin,
        device_id="dev-1",
        carpeta=CARPETA,
        modo=modo,
        diagnosticar=diagnosticar,
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


async def test_enviar_se_rechaza_explicitamente_mientras_no_haya_navegador() -> None:
    """⚠️ R2: falla cerrado y con motivo, no de una forma rara más adelante.

    El motor de envío está escrito y probado contra la página simulada; lo que
    falta es `adaptadores/whatsapp_web.py`. Hasta entonces un `ENVIAR` no puede
    salir, y decirlo claro es mejor que un `ImportError` a mitad de una corrida.
    """
    resultado = await construir(modo="real")(
        Job("1", "ENVIAR", {"mensaje_id": "x", "contacto_id": "+5491123231151", "texto": "hola"})
    )

    assert resultado["ok"] is False
    assert "whatsapp_web" in resultado["detalle"]["motivo"]
    assert resultado["detalle"]["modo"] == "real"


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
