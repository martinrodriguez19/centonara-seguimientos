"""Lo que se puede vigilar de los instaladores sin una máquina real.

Los instaladores no tienen tests de verdad: instalan cosas, escriben plists y
tareas programadas, y sólo se saben buenos en una Mac o una PC de vendedor. Lo
que sí se puede fijar desde acá es lo que ya se rompió una vez sin que nadie lo
viera:

- El 25/09/2026 ninguno de los comandos de Windows de la documentación anduvo,
  porque el BOM de `instalar.ps1` rompía `irm … | iex`. La respuesta fue dejar
  el BOM (Windows PowerShell 5.1 lo necesita para los acentos) y que ninguna
  guía vuelva a usar `iex` con nuestros scripts.
- Un script nombrado en la guía del panel que no existe en el repositorio: el
  desinstalador nació el 30/09/2026, y la guía lo nombra en tres lugares.
- Un `.sh` que no parsea: el instalador vive adentro de una función a propósito
  (se pisa a sí mismo mientras corre) y un paréntesis de menos no se ve hasta la
  Mac del vendedor.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INSTALADOR = RAIZ / "agente" / "instalador"

BOM = b"\xef\xbb\xbf"

SCRIPTS_PS1 = ["instalar.ps1", "actualizar.ps1", "desinstalar.ps1"]
SCRIPTS_SH = [
    INSTALADOR / "instalar.sh",
    INSTALADOR / "instalar-mac.sh",
    INSTALADOR / "actualizar.sh",
    INSTALADOR / "desinstalar.sh",
    RAIZ / "instalar.sh",
    RAIZ / "desinstalar.sh",
]

#  Las guías que nombran comandos. Si aparece una nueva, se agrega acá.
GUIAS = [
    RAIZ / "frontend" / "lib" / "guia.ts",
    RAIZ / "docs" / "SOP-instalar-windows.md",
    RAIZ / "docs" / "SOP-instalar-mac.md",
    RAIZ / "docs" / "COMANDOS-MAQUINAS.md",
    RAIZ / "agente" / "instalador" / "README.md",
]


@pytest.mark.parametrize("nombre", SCRIPTS_PS1)
def test_los_ps1_llevan_bom(nombre: str) -> None:
    """Sin BOM, Windows PowerShell 5.1 lee el archivo como ANSI y rompe los acentos."""
    assert (INSTALADOR / nombre).read_bytes().startswith(BOM), f"{nombre} perdió el BOM"


@pytest.mark.parametrize("nombre", SCRIPTS_PS1)
def test_los_ps1_no_llevan_crlf(nombre: str) -> None:
    """Con `-File` da igual, pero un `.gitattributes` que los convierta rompe el diff."""
    assert b"\r\n" not in (INSTALADOR / nombre).read_bytes(), f"{nombre} tiene CRLF"


@pytest.mark.parametrize("script", SCRIPTS_SH, ids=lambda p: p.name)
def test_los_sh_parsean(script: Path) -> None:
    #  En Windows, `bash` puede ser el de WSL sin distribución instalada y
    #  fallar por eso; los .sh corren en Mac, y las corridas de Mac y Linux
    #  del CI los cubren.
    if sys.platform == "win32":
        pytest.skip("los .sh se verifican en Mac y Linux")
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no hay bash en esta máquina")
    resultado = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stderr


@pytest.mark.parametrize("script", SCRIPTS_SH, ids=lambda p: p.name)
def test_los_sh_tienen_shebang_y_set_e(script: Path) -> None:
    texto = script.read_text(encoding="utf-8")
    assert texto.startswith("#!/usr/bin/env bash"), script.name
    assert "set -Eeuo pipefail" in texto, script.name


@pytest.mark.parametrize("guia", GUIAS, ids=lambda p: p.name)
def test_ninguna_guia_corre_nuestros_ps1_con_iex(guia: Path) -> None:
    """`irm … | iex` con nuestros scripts no funciona (25/09/2026). Ver instalar.ps1."""
    con_iex = re.compile(r"\|\s*(iex|Invoke-Expression)\b")
    for numero, linea in enumerate(guia.read_text(encoding="utf-8").splitlines(), 1):
        donde = f"{guia.name}:{numero}"
        if "centonara-seguimientos" in linea and con_iex.search(linea):
            pytest.fail(f"{donde} corre un .ps1 nuestro con iex: {linea.strip()[:100]}")
        if "[scriptblock]::Create((irm" in linea:
            pytest.fail(f"{donde} usa el atajo con scriptblock, que falla igual que iex")


def test_los_scripts_que_nombra_la_guia_del_panel_existen() -> None:
    """La guía del panel y las hojas de docs no pueden apuntar a un archivo que no está."""
    nombrados: set[str] = set()
    for guia in GUIAS:
        texto = guia.read_text(encoding="utf-8")
        nombrados.update(re.findall(r"agente/instalador/([a-z\-]+\.(?:sh|ps1|py))", texto))
        nombrados.update(re.findall(r"raw/main/([a-z\-]+\.sh)", texto))
    assert nombrados, "ninguna guía nombra un script: el patrón de búsqueda se rompió"
    for nombre in sorted(nombrados):
        existe = (INSTALADOR / nombre).exists() or (RAIZ / nombre).exists()
        assert existe, f"la guía nombra {nombre} y no existe en el repositorio"


def test_los_instaladores_miran_la_misma_senal_de_vida_que_el_agente() -> None:
    """La verificación final lee el archivo que escribe `reinicio.marcar_vivo`."""
    from agente import reinicio

    assert reinicio.ARCHIVO_VIVO == "vivo.json"
    sh = (INSTALADOR / "instalar.sh").read_text(encoding="utf-8")
    ps1 = (INSTALADOR / "instalar.ps1").read_text(encoding="utf-8-sig")
    assert '".centonara" / "estado" / "vivo.json"' in sh
    assert ".centonara\\estado\\vivo.json" in ps1
    #  Y el desinstalador borra esa carpeta, no otra.
    desinstalar = (INSTALADOR / "desinstalar.sh").read_text(encoding="utf-8")
    assert 'ESTADO="$HOME/.centonara"' in desinstalar


def test_el_desinstalador_conserva_la_sesion_del_navegador_de_envio_por_defecto() -> None:
    """Reinstalar no obliga a escanear el QR: la sesión del motor sólo se borra con --todo."""
    sh = (INSTALADOR / "desinstalar.sh").read_text(encoding="utf-8")
    ps1 = (INSTALADOR / "desinstalar.ps1").read_text(encoding="utf-8-sig")
    assert 'SESION_ENVIO="$HOME/Library/Application Support/Centonara"' in sh
    assert '[ "$TODO" = si ] && [ -d "$SESION_ENVIO" ]' in sh
    assert '$SESION_ENVIO = Join-Path $CENTONARA_LOCAL "Chrome"' in ps1
    assert "if ($Todo) { Borrar $SESION_ENVIO" in ps1


def test_el_instalador_de_windows_detiene_tambien_los_agentes_relanzados() -> None:
    """Un agente relanzado por versión nueva no cuelga de la tarea: se busca por su comando."""
    ps1 = (INSTALADOR / "instalar.ps1").read_text(encoding="utf-8-sig")
    assert "function DetenerAgente" in ps1
    assert "agente\\.main" in ps1
    #  Y se llama antes de arrancar, no después.
    assert ps1.index("DetenerAgente\n") < ps1.index("Start-ScheduledTask -TaskName $TAREA_AGENTE")


def test_el_instalador_de_mac_no_toma_por_desarrollo_la_carpeta_del_vendedor() -> None:
    """Corrido por ruta desde ~/centonara-seguimientos tiene que aplicar D53, no saltearlo."""
    sh = (INSTALADOR / "instalar.sh").read_text(encoding="utf-8")
    assert '[ "$posible" != "$REPO" ]' in sh
