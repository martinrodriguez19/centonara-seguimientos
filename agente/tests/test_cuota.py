"""Reconocer la cuota agotada de Claude Code, y a qué hora vuelve (D60).

Los textos de los avisos son los que Claude Code imprimió en distintas
versiones. Si aparece uno nuevo en el panel (motivo del job), se suma acá y en
`agente/jobs/cuota.py`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from agente.jobs import cuota
from agente.jobs.claude_code import Salida, invocar

CARPETA = Path(__file__).resolve().parents[1]
BIN = "/usr/local/bin/claude"

# Viernes 02/10/2026, 18:00 en Argentina (UTC-3).
ARGENTINA = timezone(timedelta(hours=-3))
AHORA = datetime(2026, 10, 2, 18, 0, tzinfo=ARGENTINA)


def correr_con(salida: Salida):
    def _correr(comando, prompt, *, timeout, cwd):
        return salida

    return _correr


# ---------------------------------------------------------------------------
# ¿Es el aviso?
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Claude AI usage limit reached|1759453200",
        "5-hour limit reached ∙ resets 9pm",
        "You've hit your limit · resets 3pm (America/Argentina/Buenos_Aires)",
        "Weekly limit reached ∙ resets Oct 6, 9am",
        "You're out of extra usage · resets 11pm",
        "Credit balance is too low",
    ],
)
def test_reconoce_los_avisos(texto: str) -> None:
    assert cuota.agotada(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "Invalid model name",
        "OAuth access token has expired",
        '{"type":"error","error":{"type":"rate_limit_error"}}',
        "no se pudo conectar al navegador",
    ],
)
def test_no_confunde_otros_errores(texto: str) -> None:
    assert not cuota.agotada(texto)


# ---------------------------------------------------------------------------
# ¿Cuándo vuelve?
# ---------------------------------------------------------------------------


def test_el_epoch_despues_de_la_barra() -> None:
    vuelve = cuota.reinicio("Claude AI usage limit reached|1759453200", ahora=AHORA)
    assert vuelve == datetime.fromtimestamp(1759453200, tz=UTC)


def test_una_hora_de_hoy_que_todavia_no_paso() -> None:
    vuelve = cuota.reinicio("5-hour limit reached ∙ resets 9pm", ahora=AHORA)
    assert vuelve == datetime(2026, 10, 2, 21, 0, tzinfo=ARGENTINA).astimezone(UTC)


def test_una_hora_que_ya_paso_es_de_manana() -> None:
    vuelve = cuota.reinicio("resets 3pm", ahora=AHORA)
    assert vuelve == datetime(2026, 10, 3, 15, 0, tzinfo=ARGENTINA).astimezone(UTC)


def test_con_minutos() -> None:
    vuelve = cuota.reinicio("resets at 9:30pm", ahora=AHORA)
    assert vuelve == datetime(2026, 10, 2, 21, 30, tzinfo=ARGENTINA).astimezone(UTC)


def test_las_doce_de_la_noche_y_del_mediodia() -> None:
    assert cuota.reinicio("resets 12am", ahora=AHORA) == datetime(
        2026, 10, 3, 0, 0, tzinfo=ARGENTINA
    ).astimezone(UTC)
    assert cuota.reinicio("resets 12pm", ahora=AHORA) == datetime(
        2026, 10, 3, 12, 0, tzinfo=ARGENTINA
    ).astimezone(UTC)


def test_con_fecha() -> None:
    vuelve = cuota.reinicio("Weekly limit reached ∙ resets Oct 6, 9am", ahora=AHORA)
    assert vuelve == datetime(2026, 10, 6, 9, 0, tzinfo=ARGENTINA).astimezone(UTC)


def test_con_la_zona_entre_parentesis() -> None:
    vuelve = cuota.reinicio("resets 9pm (UTC)", ahora=AHORA)
    assert vuelve == datetime(2026, 10, 3, 21, 0, tzinfo=UTC)


def test_una_zona_que_no_existe_usa_la_de_la_maquina() -> None:
    vuelve = cuota.reinicio("resets 9pm (Marte/Olympus)", ahora=AHORA)
    assert vuelve == datetime(2026, 10, 2, 21, 0, tzinfo=ARGENTINA).astimezone(UTC)


@pytest.mark.parametrize(
    "texto",
    ["usage limit reached", "resets Foo 6, 9am", "resets Feb 31, 9am", "resets 9:75pm"],
)
def test_si_no_se_entiende_no_se_inventa(texto: str) -> None:
    assert cuota.reinicio(texto, ahora=AHORA) is None


# ---------------------------------------------------------------------------
# En la invocación
# ---------------------------------------------------------------------------


async def test_con_codigo_de_error_sale_limite_uso_con_la_hora() -> None:
    salida = Salida(
        1, json.dumps({"is_error": True, "result": "Claude AI usage limit reached|1759453200"}), ""
    )
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=True, correr=correr_con(salida)
    )

    assert not resultado.ok
    assert resultado.codigo == "LIMITE_USO"
    assert (
        resultado.detalle["reinicia_en"] == datetime.fromtimestamp(1759453200, tz=UTC).isoformat()
    )
    assert "sin cuota" in resultado.detalle["motivo"]


async def test_tambien_si_el_aviso_viene_por_stderr() -> None:
    salida = Salida(1, "", "Error: 5-hour limit reached")
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=False, correr=correr_con(salida)
    )
    assert resultado.codigo == "LIMITE_USO"
    assert "reinicia_en" not in resultado.detalle


async def test_con_codigo_cero_y_sobre_de_error_tambien() -> None:
    salida = Salida(0, json.dumps({"is_error": True, "result": "You've hit your limit"}), "")
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=False, correr=correr_con(salida)
    )
    assert resultado.codigo == "LIMITE_USO"


async def test_una_respuesta_sana_que_habla_de_limites_no_es_cuota() -> None:
    """El cliente puede escribir "llegué al límite de crédito": eso es un chat."""
    interior = json.dumps({"status": "ok", "texto": "Usage limit reached en la tarjeta"})
    salida = Salida(0, json.dumps({"result": interior}), "")
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=False, correr=correr_con(salida)
    )
    assert resultado.ok


async def test_un_error_cualquiera_sigue_siendo_inesperado() -> None:
    salida = Salida(1, '{"result": "Invalid model name"}', "")
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=False, correr=correr_con(salida)
    )
    assert resultado.codigo == "ERROR_INESPERADO"
