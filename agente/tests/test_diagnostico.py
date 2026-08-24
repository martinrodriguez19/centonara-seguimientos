"""Tests de los nueve chequeos.

Lo que se prueba acá no es que los chequeos existan: es que **digan qué falta**.
En el MVP los siete problemas conocidos se manifestaban como un HTTP 502 mudo y
había que adivinar cuál era; la diferencia entre esto y aquello es el `detalle`.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest

from agente.diagnostico import (
    PERMISO_MCP,
    Chequeo,
    Diagnostico,
    Estado,
    ejecutar,
)


def por_nombre(diagnostico: Diagnostico) -> dict[str, Chequeo]:
    return {c.nombre: c for c in diagnostico.chequeos}


@pytest.fixture
def hogar(tmp_path: Path) -> Path:
    """Un `~` de mentira, con el settings.json bien puesto."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(
        json.dumps({"permissions": {"allow": [PERMISO_MCP]}}), encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def carpeta_agente(tmp_path: Path) -> Path:
    carpeta = tmp_path / "agente"
    (carpeta / "prompts").mkdir(parents=True)
    (carpeta / "prompts" / "CLAUDE.md").write_text("# contexto", encoding="utf-8")
    return carpeta


def correr(hogar: Path, carpeta: Path, **extra) -> Diagnostico:
    opciones = {
        "claude_bin": str(Path(__file__)),  # un archivo que existe seguro
        "device_id": "dispositivo-1",
        "carpeta_agente": carpeta,
        "inicio": hogar,
        "con_navegador": False,
    }
    opciones.update(extra)
    return ejecutar(**opciones)


# ---------------------------------------------------------------------------
# La forma del diagnóstico
# ---------------------------------------------------------------------------


def test_son_diez_chequeos(hogar: Path, carpeta_agente: Path) -> None:
    assert len(correr(hogar, carpeta_agente).chequeos) == 10


def test_estan_los_siete_del_mvp_mas_los_tres_nuevos(hogar: Path, carpeta_agente: Path) -> None:
    nombres = set(por_nombre(correr(hogar, carpeta_agente)))
    assert nombres == {
        "claude_bin",
        "permiso_mcp",
        "permiso_sitio",
        "device_id",
        "chrome",
        "chrome_puerto",
        "whatsapp_sesion",
        "claude_md",
        "permisos_macos",
        "selectores",
    }


def test_cada_chequeo_del_mvp_dice_de_que_problema_viene(hogar: Path, carpeta_agente: Path) -> None:
    """Para que alguien pueda ir al historial y leer qué era."""
    chequeos = por_nombre(correr(hogar, carpeta_agente))
    for nombre in ("claude_bin", "permiso_mcp", "permiso_sitio", "device_id", "claude_md"):
        assert chequeos[nombre].origen.startswith("MVP #"), nombre


def test_lo_que_viaja_al_backend_es_nombre_y_estado(hogar: Path, carpeta_agente: Path) -> None:
    resumen = correr(hogar, carpeta_agente).a_dict()
    assert resumen["claude_bin"] == "ok"
    assert set(resumen.values()) <= {"ok", "falla", "n/a"}


# ---------------------------------------------------------------------------
# n/a no es falla — lo que permite desarrollar en Windows
# ---------------------------------------------------------------------------


def test_los_na_no_impiden_trabajar(hogar: Path, carpeta_agente: Path) -> None:
    """Varios chequeos dan `n/a` y ninguno de ellos frena al agente.

    Es lo que permitió construir las fases 1 a 3 desde Windows: lo que no se
    puede verificar en esta máquina no cuenta como roto.
    """
    diagnostico = correr(hogar, carpeta_agente)

    assert any(c.estado is Estado.NO_APLICA for c in diagnostico.chequeos)
    #  Ninguna de las fallas, si las hay, viene de un `n/a`.
    assert all(c.estado is Estado.FALLA for c in diagnostico.fallas)


def test_sin_selectores_verificados_la_maquina_no_puede_enviar(
    hogar: Path, carpeta_agente: Path
) -> None:
    """⚠️ Es el único chequeo que hoy separa al sistema de poder escribir.

    Los selectores de WhatsApp Web nunca se verificaron contra una sesión real,
    así que `selectores` **falla** —no da `n/a`— y con eso `puede_enviar` es
    `False` y el agente no toma jobs de envío.

    No es un placeholder: cuando alguien complete `selectores.VERIFICADO`, esto
    pasa a verde solo. Mientras tanto tiene que verse en el panel, porque es lo
    que hay que ir a resolver.
    """
    from agente.adaptadores import selectores

    chequeo = por_nombre(correr(hogar, carpeta_agente))["selectores"]

    if selectores.VERIFICADO is None:
        assert chequeo.estado is Estado.FALLA
        assert "envío real está bloqueado" in chequeo.detalle
        assert not correr(hogar, carpeta_agente).puede_enviar
    else:
        assert chequeo.estado is Estado.OK


def test_un_na_no_cuenta_como_falla() -> None:
    diagnostico = Diagnostico(
        (
            Chequeo("uno", Estado.OK),
            Chequeo("dos", Estado.NO_APLICA, "todavía no aplica"),
        )
    )
    assert diagnostico.puede_enviar
    assert diagnostico.fallas == ()


def test_una_sola_falla_alcanza_para_no_tomar_envios() -> None:
    diagnostico = Diagnostico(
        (Chequeo("uno", Estado.OK), Chequeo("dos", Estado.FALLA, "no existe"))
    )
    assert not diagnostico.puede_enviar


def test_lo_que_solo_se_ve_abriendo_la_pagina_da_na(hogar: Path, carpeta_agente: Path) -> None:
    """`whatsapp_sesion` y `permiso_sitio` no se pueden verificar leyendo archivos.

    Los contesta `--sonda`, que abre la página una vez. Acá dan `n/a` y no
    falla, porque no saber no es lo mismo que estar roto.
    """
    chequeos = por_nombre(correr(hogar, carpeta_agente))
    for nombre in ("whatsapp_sesion", "permiso_sitio"):
        assert chequeos[nombre].estado is Estado.NO_APLICA


def test_el_puerto_de_chrome_cerrado_no_es_una_falla(hogar: Path, carpeta_agente: Path) -> None:
    """El agente lo abre solo cuando llega trabajo.

    Que ahora esté cerrado no dice nada. Lo que sí sería un problema —Chrome
    abierto SIN el puerto— se detecta al intentar abrirlo, no acá.
    """
    chequeo = por_nombre(correr(hogar, carpeta_agente))["chrome_puerto"]
    assert chequeo.estado in (Estado.OK, Estado.NO_APLICA)


def test_los_permisos_de_macos_dan_na_fuera_de_macos(hogar: Path, carpeta_agente: Path) -> None:
    chequeo = por_nombre(correr(hogar, carpeta_agente))["permisos_macos"]
    assert chequeo.estado is Estado.NO_APLICA
    if platform.system() != "Darwin":
        assert platform.system() in chequeo.detalle


def test_el_permiso_de_sitio_no_se_puede_verificar_desde_afuera(
    hogar: Path, carpeta_agente: Path
) -> None:
    """Problema #4 del MVP, y el que se olvida.

    Queda declarado aunque siempre dé `n/a`, para que aparezca en el panel y
    alguien se acuerde de que existe. Es una capa distinta del permiso MCP.
    """
    chequeo = por_nombre(correr(hogar, carpeta_agente))["permiso_sitio"]
    assert chequeo.estado is Estado.NO_APLICA
    assert "web.whatsapp.com" in chequeo.detalle


# ---------------------------------------------------------------------------
# Los siete problemas del MVP, cada uno detectado
# ---------------------------------------------------------------------------


def test_mvp_2_sin_claude_bin(hogar: Path, carpeta_agente: Path) -> None:
    chequeo = por_nombre(correr(hogar, carpeta_agente, claude_bin=""))["claude_bin"]
    assert chequeo.estado is Estado.FALLA
    assert "ruta completa" in chequeo.detalle


def test_mvp_2_con_una_ruta_que_no_existe(hogar: Path, carpeta_agente: Path) -> None:
    ruta = "/no/existe/claude"
    chequeo = por_nombre(correr(hogar, carpeta_agente, claude_bin=ruta))["claude_bin"]
    assert chequeo.estado is Estado.FALLA
    assert ruta in chequeo.detalle, "el detalle dice CUÁL ruta falló"


def test_mvp_3_sin_settings_json(tmp_path: Path, carpeta_agente: Path) -> None:
    chequeo = por_nombre(correr(tmp_path, carpeta_agente))["permiso_mcp"]
    assert chequeo.estado is Estado.FALLA
    assert "settings.json" in chequeo.detalle


def test_mvp_3_con_settings_json_sin_el_permiso(tmp_path: Path, carpeta_agente: Path) -> None:
    """El caso real: el archivo está, y justo falta ese permiso."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["otra_cosa"]}}), encoding="utf-8"
    )

    chequeo = por_nombre(correr(tmp_path, carpeta_agente))["permiso_mcp"]
    assert chequeo.estado is Estado.FALLA
    assert PERMISO_MCP in chequeo.detalle


def test_mvp_3_con_settings_json_roto(tmp_path: Path, carpeta_agente: Path) -> None:
    """Un JSON mal formado no puede reventar el diagnóstico entero."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{ esto no es json", encoding="utf-8")

    chequeo = por_nombre(correr(tmp_path, carpeta_agente))["permiso_mcp"]
    assert chequeo.estado is Estado.FALLA
    assert "ilegible" in chequeo.detalle


def test_mvp_5_sin_device_id(hogar: Path, carpeta_agente: Path) -> None:
    chequeo = por_nombre(correr(hogar, carpeta_agente, device_id=""))["device_id"]
    assert chequeo.estado is Estado.FALLA
    assert "Chrome" in chequeo.detalle, "el detalle explica por qué importa"


def test_mvp_7_sin_claude_md(hogar: Path, tmp_path: Path) -> None:
    vacia = tmp_path / "sin_prompts"
    vacia.mkdir()

    chequeo = por_nombre(correr(hogar, vacia))["claude_md"]
    assert chequeo.estado is Estado.FALLA
    assert "CLAUDE.md" in chequeo.detalle


# ---------------------------------------------------------------------------
# El chequeo que lanza un proceso
# ---------------------------------------------------------------------------


def test_sin_navegador_el_chequeo_de_chrome_se_saltea(hogar: Path, carpeta_agente: Path) -> None:
    """Para que el arranque no espere a `claude --version`, que tarda."""
    chequeo = por_nombre(correr(hogar, carpeta_agente))["chrome"]
    assert chequeo.estado is Estado.NO_APLICA


def test_un_ejecutable_que_no_arranca_se_reporta_como_falla(
    hogar: Path, carpeta_agente: Path, tmp_path: Path
) -> None:
    falso = tmp_path / "no-ejecutable.txt"
    falso.write_text("no soy un programa", encoding="utf-8")

    chequeo = por_nombre(correr(hogar, carpeta_agente, claude_bin=str(falso), con_navegador=True))[
        "chrome"
    ]
    assert chequeo.estado is Estado.FALLA


def test_sin_claude_bin_el_chequeo_de_chrome_es_na(hogar: Path, carpeta_agente: Path) -> None:
    """No se reporta dos veces el mismo problema: ya lo dijo `claude_bin`."""
    chequeo = por_nombre(correr(hogar, carpeta_agente, claude_bin="", con_navegador=True))["chrome"]
    assert chequeo.estado is Estado.NO_APLICA


# ---------------------------------------------------------------------------
# El resumen
# ---------------------------------------------------------------------------


def test_el_resumen_nombra_cada_falla_con_su_motivo() -> None:
    """Es lo que va a leer alguien en el panel para arreglarlo."""
    diagnostico = Diagnostico(
        (
            Chequeo("claude_bin", Estado.FALLA, "no existe: /mal/camino"),
            Chequeo("device_id", Estado.FALLA, "sin deviceId"),
            Chequeo("claude_md", Estado.OK),
        )
    )
    resumen = diagnostico.resumen()

    assert "claude_bin: no existe: /mal/camino" in resumen
    assert "device_id: sin deviceId" in resumen
    assert "claude_md" not in resumen, "lo que anda bien no ocupa lugar"


def test_un_diagnostico_vacio_no_rompe() -> None:
    vacio = Diagnostico()
    assert vacio.puede_enviar
    assert vacio.a_dict() == {}
