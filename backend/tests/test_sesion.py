"""Tests de la sesión del panel.

Es criptografía escrita a mano, así que los tests importan más de lo habitual:
lo que verifican es que no se pueda fabricar una cookie sin el secreto, y que
una cookie rota no sea distinguible de una ausente.
"""

from __future__ import annotations

import time

import pytest

from app.core import sesion

SECRETO = "un-secreto-de-prueba-largo-y-aleatorio"
AHORA = 1_800_000_000.0


# ---------------------------------------------------------------------------
# Emitir y verificar
# ---------------------------------------------------------------------------


def test_una_cookie_recien_emitida_vale() -> None:
    cookie = sesion.emitir(SECRETO, ahora=AHORA)
    assert sesion.verificar(SECRETO, cookie, ahora=AHORA) is not None


def test_la_cookie_no_lleva_la_contraseña_ni_nada_secreto() -> None:
    """Se puede leer: lo que la hace confiable es la firma, no el secreto."""
    cookie = sesion.emitir(SECRETO, ahora=AHORA)
    assert SECRETO not in cookie


def test_la_cookie_vence() -> None:
    cookie = sesion.emitir(SECRETO, duracion=60, ahora=AHORA)
    assert sesion.verificar(SECRETO, cookie, ahora=AHORA + 59) is not None
    assert sesion.verificar(SECRETO, cookie, ahora=AHORA + 61) is None


def test_la_duracion_por_defecto_es_una_jornada() -> None:
    """Que pida la contraseña al día siguiente es razonable; a los 20 min, no."""
    assert sesion.DURACION_SEGUNDOS == 8 * 60 * 60


def test_sin_secreto_no_se_puede_emitir() -> None:
    """Si SESION_SECRET no se cargó en Render, esto tiene que romper fuerte."""
    with pytest.raises(ValueError, match="SESION_SECRET"):
        sesion.emitir("")


# ---------------------------------------------------------------------------
# Lo que no tiene que valer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cookie",
    [
        None,
        "",
        "sin-punto",
        ".",
        "1800000000.",
        ".firma",
        "no-es-un-numero.firma",
        "1800000000.firma-inventada",
    ],
)
def test_una_cookie_mal_formada_no_vale(cookie: str | None) -> None:
    """Ausente, rota, o con firma inventada son todas lo mismo: no autenticado."""
    assert sesion.verificar(SECRETO, cookie, ahora=AHORA) is None


def test_no_se_puede_estirar_el_vencimiento_sin_el_secreto() -> None:
    """⚠️ Lo que hace que esto sirva.

    Alguien lee su cookie, ve que es una fecha, y la cambia por una de dentro de
    diez años. La firma deja de coincidir.
    """
    cookie = sesion.emitir(SECRETO, duracion=60, ahora=AHORA)
    _, _, firma = cookie.rpartition(".")
    falsificada = f"{int(AHORA) + 10_000_000}.{firma}"

    assert sesion.verificar(SECRETO, falsificada, ahora=AHORA) is None


def test_una_cookie_de_otro_secreto_no_vale() -> None:
    """Rotar SESION_SECRET cierra todas las sesiones abiertas. Es lo que se espera."""
    cookie = sesion.emitir("secreto-viejo", ahora=AHORA)
    assert sesion.verificar("secreto-nuevo", cookie, ahora=AHORA) is None


def test_sin_secreto_no_valida_nada() -> None:
    cookie = sesion.emitir(SECRETO, ahora=AHORA)
    assert sesion.verificar("", cookie, ahora=AHORA) is None


# ---------------------------------------------------------------------------
# La contraseña
# ---------------------------------------------------------------------------


def test_la_contraseña_correcta_valida() -> None:
    assert sesion.clave_correcta("abracadabra", "abracadabra")


def test_una_contraseña_distinta_no_valida() -> None:
    assert not sesion.clave_correcta("abracadabra", "abracadabrá")
    assert not sesion.clave_correcta("abracadabra", "abracadabr")
    assert not sesion.clave_correcta("abracadabra", "")


def test_una_contraseña_sin_configurar_deja_el_panel_cerrado() -> None:
    """⚠️ Si PANEL_PASSWORD no se cargó en Render, nadie entra.

    El error tiene que ser "no puedo entrar", no "entra cualquiera que mande el
    formulario vacío". Es la diferencia entre un despliegue mal configurado que
    se nota y uno que no.
    """
    assert not sesion.clave_correcta("", "")
    assert not sesion.clave_correcta("", "lo que sea")


def test_el_generador_de_secretos_da_algo_distinto_cada_vez() -> None:
    assert len({sesion.generar_secreto() for _ in range(100)}) == 100


def test_la_sesion_sabe_si_ya_vencio_sin_que_le_pasen_la_hora() -> None:
    assert sesion.Sesion(vence_en=int(time.time()) - 1).vencida()
    assert not sesion.Sesion(vence_en=int(time.time()) + 60).vencida()


@pytest.mark.parametrize("clave", ["contraseñá", "日本語", "señal-de-radio", "emoji-🔒"])
def test_una_contraseña_con_acentos_funciona(clave: str) -> None:
    """Regresión: `hmac.compare_digest` sobre str exige ASCII y lanza TypeError.

    Con la versión anterior, una contraseña con acento hacía que el login
    devolviera 500 en vez de "contraseña incorrecta" — o peor, reventaba el
    endpoint con la contraseña correcta.
    """
    assert sesion.clave_correcta(clave, clave)
    assert not sesion.clave_correcta(clave, clave + "x")


def test_una_cookie_con_caracteres_raros_no_revienta() -> None:
    """La cookie la manda el cliente: puede tener cualquier cosa."""
    assert sesion.verificar(SECRETO, "1800000000.ñoño-🔒", ahora=AHORA) is None
