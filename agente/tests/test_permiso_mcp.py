"""El permiso del modo headless, sin pisarle la configuración a nadie.

El SOP tenía un `echo ... > ~/.claude/settings.json`, que **sobrescribe el
archivo entero**. En la máquina donde se desarrolló esto ese archivo tenía
además `agentPushNotifEnabled`; el comando lo habría borrado. En la máquina de
un vendedor que ya usaba Claude Code, le habría borrado su configuración.
"""

from __future__ import annotations

import json

from agente.permiso_mcp import PERMISO, asegurar


def leer(hogar):
    return json.loads((hogar / ".claude" / "settings.json").read_text(encoding="utf-8"))


def test_lo_crea_si_no_existe(tmp_path) -> None:
    resultado = asegurar(tmp_path)

    assert resultado.cambiado
    assert leer(tmp_path)["permissions"]["allow"] == [PERMISO]


def test_no_pisa_lo_que_ya_habia(tmp_path) -> None:
    """⚠️ Lo que el `echo` del SOP rompía.

    Alguien que ya usaba Claude Code para otra cosa tiene ahí su configuración.
    """
    archivo = tmp_path / ".claude" / "settings.json"
    archivo.parent.mkdir()
    archivo.write_text(
        json.dumps(
            {
                "agentPushNotifEnabled": True,
                "theme": "dark",
                "permissions": {"allow": ["mcp__otra-cosa"], "deny": ["algo"]},
            }
        ),
        encoding="utf-8",
    )

    asegurar(tmp_path)

    contenido = leer(tmp_path)
    assert contenido["agentPushNotifEnabled"] is True
    assert contenido["theme"] == "dark"
    assert contenido["permissions"]["deny"] == ["algo"]
    assert contenido["permissions"]["allow"] == ["mcp__otra-cosa", PERMISO]


def test_si_ya_estaba_no_toca_nada(tmp_path) -> None:
    """Idempotente: el instalador se puede correr dos veces."""
    asegurar(tmp_path)
    antes = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")

    resultado = asegurar(tmp_path)

    assert not resultado.cambiado
    assert "ya estaba" in resultado.detalle
    assert (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8") == antes


def test_un_archivo_ilegible_no_se_sobrescribe(tmp_path) -> None:
    """⚠️ Puede tener la configuración de alguien y estar sólo mal formado.

    Pisarlo cambiaría un problema chico —un JSON roto— por uno peor: la
    configuración perdida sin que nadie se entere.
    """
    archivo = tmp_path / ".claude" / "settings.json"
    archivo.parent.mkdir()
    archivo.write_text('{"permissions": ROTO', encoding="utf-8")

    resultado = asegurar(tmp_path)

    assert not resultado.cambiado
    assert "no se pudo leer" in resultado.detalle
    assert archivo.read_text(encoding="utf-8") == '{"permissions": ROTO'


def test_un_json_que_no_es_objeto_tampoco(tmp_path) -> None:
    archivo = tmp_path / ".claude" / "settings.json"
    archivo.parent.mkdir()
    archivo.write_text("[1, 2, 3]", encoding="utf-8")

    resultado = asegurar(tmp_path)

    assert not resultado.cambiado
    assert archivo.read_text(encoding="utf-8") == "[1, 2, 3]"


def test_permissions_con_una_forma_rara_no_se_rompe(tmp_path) -> None:
    archivo = tmp_path / ".claude" / "settings.json"
    archivo.parent.mkdir()
    archivo.write_text('{"permissions": "todo"}', encoding="utf-8")

    resultado = asegurar(tmp_path)

    assert not resultado.cambiado
    assert "no es un objeto" in resultado.detalle
