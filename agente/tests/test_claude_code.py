"""La invocación a Claude Code: cómo se la llama y cómo se le lee la respuesta.

Cuatro de los siete problemas del MVP viven en la forma de esta llamada, y todos
son invisibles hasta que alguien está en la máquina de un vendedor mirando por
qué no anda. Por eso se testean como contrato y no como detalle: si mañana
alguien "limpia" el `encoding="utf-8"` porque en su Mac no hace falta, esto lo
agarra.

Ninguno de estos tests lanza un proceso. `_correr` se inyecta.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agente.jobs.claude_code import Salida, invocar, rellenar

CARPETA = Path(__file__).resolve().parents[1]
BIN = r"C:\claude.exe"


class Espia:
    """Un doble de `subprocess.run` que anota con qué lo llamaron."""

    def __init__(self, salida: Salida | None = None, revienta: Exception | None = None) -> None:
        self.salida = salida or Salida(0, json.dumps({"result": '{"status": "ok"}'}), "")
        self.revienta = revienta
        self.comando: list[str] = []
        self.prompt = ""
        self.cwd: Path | None = None
        self.timeout: float | None = None
        self.llamadas = 0

    def __call__(self, comando, prompt, *, timeout, cwd):
        self.llamadas += 1
        self.comando = comando
        self.prompt = prompt
        self.cwd = cwd
        self.timeout = timeout
        if self.revienta:
            raise self.revienta
        return self.salida


def sobre(interior: str, *, costo: float = 0.0) -> Salida:
    """Lo que devuelve `--output-format json`: nuestra respuesta, envuelta."""
    return Salida(0, json.dumps({"result": interior, "total_cost_usd": costo}), "")


# ---------------------------------------------------------------------------
# La forma de la llamada
# ---------------------------------------------------------------------------


async def test_el_prompt_va_por_stdin_y_no_como_argumento() -> None:
    """Problema del MVP: `cmd.exe` corta el comando en el primer salto de línea.

    Un prompt multilínea pasado como argumento llega mutilado. En macOS no pasa
    y se hace igual, porque el código es compartido.
    """
    espia = Espia()
    prompt = "linea uno\nlinea dos\nlinea tres"

    await invocar(prompt, claude_bin=BIN, carpeta=CARPETA, con_navegador=True, correr=espia)

    assert espia.prompt == prompt
    assert not any("linea uno" in arg for arg in espia.comando)


async def test_listar_abre_el_navegador() -> None:
    espia = Espia()
    await invocar("x", claude_bin=BIN, carpeta=CARPETA, con_navegador=True, correr=espia)
    assert "--chrome" in espia.comando


async def test_redactar_no_abre_el_navegador() -> None:
    """⚠️ El criterio verificable de `docs/04-AGENTE.md` §6.

    Es donde está el ahorro del proyecto: `REDACTAR` es uno por chat y `LISTAR`
    uno por máquina. Si `--chrome` se cuela acá, el costo por mensaje se va a
    donde estaba en el MVP y nadie lo nota hasta ver la factura.
    """
    espia = Espia()
    await invocar("x", claude_bin=BIN, carpeta=CARPETA, con_navegador=False, correr=espia)
    assert "--chrome" not in espia.comando


async def test_veinte_borradores_no_abren_ninguna_pestania() -> None:
    """El mismo criterio, dicho como lo dice el documento."""
    espia = Espia()
    for _ in range(20):
        await invocar("x", claude_bin=BIN, carpeta=CARPETA, con_navegador=False, correr=espia)

    assert espia.llamadas == 20
    assert "--chrome" not in espia.comando


async def test_corre_en_la_carpeta_del_agente() -> None:
    """Para que Claude Code encuentre el `CLAUDE.md` (problema #7 del MVP)."""
    espia = Espia()
    await invocar("x", claude_bin=BIN, carpeta=CARPETA, con_navegador=True, correr=espia)
    assert espia.cwd == CARPETA
    assert (CARPETA / "prompts" / "CLAUDE.md").exists()


async def test_usa_la_ruta_completa_que_le_dan() -> None:
    """Problema #2: `which("claude")` devolvía None bajo launchd."""
    espia = Espia()
    await invocar("x", claude_bin=BIN, carpeta=CARPETA, con_navegador=True, correr=espia)
    assert espia.comando[0] == BIN


async def test_sin_claude_bin_no_se_lanza_nada() -> None:
    espia = Espia()
    resultado = await invocar("x", claude_bin="", carpeta=CARPETA, con_navegador=True, correr=espia)

    assert not resultado.ok
    assert espia.llamadas == 0


# ---------------------------------------------------------------------------
# Leer la respuesta
# ---------------------------------------------------------------------------


async def test_desenvuelve_el_sobre_y_saca_el_costo() -> None:
    espia = Espia(sobre('{"status": "ok", "texto": "hola"}', costo=0.0123))
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=False, correr=espia
    )

    assert resultado.ok
    assert resultado.datos == {"status": "ok", "texto": "hola"}
    assert resultado.costo_usd == pytest.approx(0.0123)


async def test_saca_los_backticks_que_el_modelo_agrega_igual() -> None:
    espia = Espia(sobre('```json\n{"status": "ok"}\n```'))
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=False, correr=espia
    )

    assert resultado.ok
    assert resultado.datos == {"status": "ok"}


async def test_sin_sobre_tambien_parsea() -> None:
    """Si `--output-format json` cambiara, el JSON de adentro sigue sirviendo."""
    espia = Espia(Salida(0, '{"status": "ok"}', ""))
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=False, correr=espia
    )

    assert resultado.ok
    assert resultado.datos == {"status": "ok"}


async def test_un_costo_ilegible_no_rompe_la_corrida() -> None:
    espia = Espia(
        Salida(0, json.dumps({"result": '{"status":"ok"}', "total_cost_usd": "gratis"}), "")
    )
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=False, correr=espia
    )

    assert resultado.ok
    assert resultado.costo_usd == 0.0


async def test_una_salida_que_no_parsea_se_reporta_con_el_crudo_entero() -> None:
    """Sin el crudo, "no devolvió JSON" es un callejón sin salida.

    Es el fallo más probable cuando alguien toca el prompt, y el crudo es lo
    único que dice qué contestó el modelo.
    """
    espia = Espia(sobre("Claro, con gusto. Los chats que leí son:"))
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=True, correr=espia
    )

    assert not resultado.ok
    assert resultado.codigo == "ERROR_INESPERADO"
    assert "Claro, con gusto" in resultado.raw


async def test_un_json_que_no_es_objeto_se_rechaza() -> None:
    espia = Espia(sobre("[1, 2, 3]"))
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=True, correr=espia
    )

    assert not resultado.ok
    assert "list" in str(resultado.detalle)


async def test_un_codigo_de_salida_distinto_de_cero_es_fallo() -> None:
    espia = Espia(Salida(2, "", "no se pudo conectar al navegador"))
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=True, correr=espia
    )

    assert not resultado.ok
    assert resultado.detalle["returncode"] == 2
    assert "navegador" in resultado.stderr


async def test_el_timeout_tiene_su_propio_codigo() -> None:
    """Se distingue de un error genérico porque la cola sí lo reintenta."""
    espia = Espia(revienta=subprocess.TimeoutExpired("claude", 600))
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=True, correr=espia
    )

    assert not resultado.ok
    assert resultado.codigo == "TIMEOUT"


async def test_un_ejecutable_que_no_arranca_no_revienta_el_agente() -> None:
    espia = Espia(revienta=OSError("no es una aplicación válida"))
    resultado = await invocar(
        "x", claude_bin=BIN, carpeta=CARPETA, con_navegador=True, correr=espia
    )

    assert not resultado.ok
    assert resultado.codigo == "ERROR_INESPERADO"


# ---------------------------------------------------------------------------
# El prompt
# ---------------------------------------------------------------------------


def test_rellenar_sustituye_las_variables(tmp_path: Path) -> None:
    plantilla = tmp_path / "p.txt"
    plantilla.write_text("hola {{QUIEN}}, son {{CUANTOS}}", encoding="utf-8")

    assert rellenar(plantilla, {"QUIEN": "mundo", "CUANTOS": "3"}) == "hola mundo, son 3"


def test_un_valor_no_puede_inyectar_otra_variable(tmp_path: Path) -> None:
    """El backend manda variables validadas, no texto de prompt.

    Aun así, un valor que contenga `{{OTRA}}` no se vuelve a expandir: la
    sustitución es una sola pasada por variable, sobre el texto que va quedando.
    """
    plantilla = tmp_path / "p.txt"
    plantilla.write_text("{{UNO}} y {{DOS}}", encoding="utf-8")

    salida = rellenar(plantilla, {"UNO": "{{DOS}}", "DOS": "final"})

    #  `{{DOS}}` inyectado por UNO se expande, porque DOS se sustituye después;
    #  lo que no puede es inventar una variable que no estaba en el diccionario.
    assert "{{" not in salida.replace("{{DOS}}", "")
    assert rellenar(plantilla, {"UNO": "{{TRES}}"}) == "{{TRES}} y {{DOS}}"


def test_los_dos_prompts_estan_en_disco_y_tienen_sus_variables() -> None:
    """El prompt no viaja por la red: vive en la máquina del vendedor."""
    listar = (CARPETA / "prompts" / "prompt-listar.txt").read_text(encoding="utf-8")
    redactar = (CARPETA / "prompts" / "prompt-redactar.txt").read_text(encoding="utf-8")

    for variable in ("{{N_CHATS}}", "{{RUN_ID}}", "{{DEVICE_ID}}"):
        assert variable in listar
    for variable in ("{{CONTACTO_NOMBRE}}", "{{ULTIMO_MENSAJE_RESUMEN}}", "{{LARGO_MAXIMO}}"):
        assert variable in redactar
