"""Qué perfil de Chrome usar, y de dónde sale el `deviceId`.

Estos dos datos los sacaba una persona a mano: un `grep` con espacios escapados
y comparar dos listas de rutas a ojo. Es de las cosas que nadie hace bien la
primera vez, y equivocarse deja una instalación que no funciona sin decir por
qué.

Los perfiles se arman en `tmp_path`: ninguno de estos tests mira el Chrome de
quien los corre.
"""

from __future__ import annotations

import pytest

from agente import perfiles
from agente.perfiles import EXTENSION, recomendar


def armar(base, nombre: str, *, extension=False, whatsapp=False, device_id=None):
    """Un perfil de Chrome de mentira, con la estructura que se inspecciona."""
    carpeta = base / nombre
    carpeta.mkdir(parents=True, exist_ok=True)

    if extension:
        (carpeta / "Extensions" / EXTENSION).mkdir(parents=True)
    if whatsapp:
        idb = carpeta / "IndexedDB" / "https_web.whatsapp.com_0.indexeddb.leveldb"
        idb.mkdir(parents=True)
        (idb / "000003.log").write_bytes(b"lo que sea")
    if device_id:
        almacen = carpeta / "Local Extension Settings" / EXTENSION
        almacen.mkdir(parents=True, exist_ok=True)
        (almacen / "000003.log").write_bytes(
            b'\x00\x01basura anterior\x00bridgeDeviceId&"'
            + device_id.encode()
            + b'"\x00mcpConnected'
        )
    return carpeta


@pytest.fixture
def chrome(tmp_path, monkeypatch):
    """Una carpeta `User Data` vacía, en lugar de la de esta máquina."""
    base = tmp_path / "User Data"
    base.mkdir()
    monkeypatch.setattr(perfiles, "carpeta_chrome", lambda: base)
    return base


# ---------------------------------------------------------------------------
# Leer los perfiles
# ---------------------------------------------------------------------------


def test_encuentra_lo_que_tiene_cada_perfil(chrome) -> None:
    armar(chrome, "Default", extension=True)
    armar(chrome, "Profile 3", whatsapp=True)
    armar(chrome, "Profile 7")

    por_nombre = {p.nombre: p for p in perfiles.listar()}

    assert por_nombre["Default"].tiene_extension
    assert not por_nombre["Default"].tiene_whatsapp
    assert por_nombre["Profile 3"].tiene_whatsapp
    assert not por_nombre["Profile 7"].sirve


def test_saca_el_device_id_del_almacen_de_la_extension(chrome) -> None:
    """Es el dato que estaba documentado como un `grep` de dos líneas."""
    armar(
        chrome,
        "Default",
        extension=True,
        whatsapp=True,
        device_id="f83d5f3e-3278-46c6-8ccc-148e58805116",
    )

    perfil = perfiles.listar()[0]

    assert perfil.device_id == "f83d5f3e-3278-46c6-8ccc-148e58805116"


def test_una_carpeta_de_whatsapp_vacia_no_cuenta(chrome) -> None:
    """Queda vacía cuando la sesión venció, y eso no es haberla usado."""
    carpeta = armar(chrome, "Default", extension=True)
    (carpeta / "IndexedDB" / "https_web.whatsapp.com_0.indexeddb.leveldb").mkdir(parents=True)

    assert not perfiles.listar()[0].tiene_whatsapp


def test_no_se_confunde_con_carpetas_que_no_son_perfiles(chrome) -> None:
    armar(chrome, "Profile 1", extension=True, whatsapp=True)
    (chrome / "ShaderCache").mkdir()
    (chrome / "GrShaderCache").mkdir()

    assert [p.nombre for p in perfiles.listar()] == ["Profile 1"]


# ---------------------------------------------------------------------------
# Qué recomendar — que es lo que se le ahorra a una persona
# ---------------------------------------------------------------------------


def test_elige_el_perfil_que_tiene_las_dos_cosas(chrome) -> None:
    armar(chrome, "Default", extension=True)
    armar(chrome, "Profile 3", whatsapp=True)
    armar(chrome, "Profile 9", extension=True, whatsapp=True)

    recomendacion = recomendar()

    assert recomendacion.listo
    assert recomendacion.perfil.nombre == "Profile 9"


def test_entre_dos_que_sirven_prefiere_el_que_se_uso(chrome) -> None:
    """El que tiene `deviceId` es el que la extensión usó de verdad."""
    armar(chrome, "Profile 1", extension=True, whatsapp=True)
    armar(
        chrome,
        "Profile 5",
        extension=True,
        whatsapp=True,
        device_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )

    assert recomendar().perfil.nombre == "Profile 5"


def test_separados_lo_dice_y_dice_como_juntarlos(chrome) -> None:
    """⚠️ El caso que apareció de verdad: extensión en uno, sesión en otro.

    Con las dos listas de rutas había que darse cuenta comparando a ojo. Acá
    tiene que salir dicho, y con la salida.
    """
    armar(chrome, "Profile 37", extension=True)
    armar(chrome, "Profile 20", whatsapp=True)

    recomendacion = recomendar()

    assert not recomendacion.listo
    assert "Profile 37" in recomendacion.problema
    assert "Profile 20" in recomendacion.problema
    assert "distintos" in recomendacion.problema
    assert recomendacion.solucion, "un problema sin qué hacer es una queja"


def test_sin_whatsapp_en_ningun_lado_manda_a_escanear_el_qr(chrome) -> None:
    armar(chrome, "Default", extension=True)

    recomendacion = recomendar()

    assert not recomendacion.listo
    assert "web.whatsapp.com" in recomendacion.solucion


def test_sin_la_extension_manda_a_instalarla(chrome) -> None:
    armar(chrome, "Default", whatsapp=True)

    recomendacion = recomendar()

    assert not recomendacion.listo
    assert "extensión" in recomendacion.solucion


def test_sin_chrome_lo_dice_y_dice_donde_busco(chrome, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(perfiles, "carpeta_chrome", lambda: tmp_path / "no-existe")

    recomendacion = recomendar()

    assert not recomendacion.listo
    assert "no-existe" in recomendacion.solucion


def test_todo_problema_trae_su_solucion(chrome) -> None:
    """Un diagnóstico sin qué hacer obliga a preguntarle a alguien."""
    for armado in (
        lambda: armar(chrome, "A", extension=True),
        lambda: armar(chrome, "B", whatsapp=True),
    ):
        armado()
    recomendacion = recomendar()

    if not recomendacion.listo:
        assert recomendacion.problema
        assert recomendacion.solucion
