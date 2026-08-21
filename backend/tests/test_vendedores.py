"""Tests de las máquinas y sus tokens."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core import vendedores
from app.core.esquema import inicializar

AHORA = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)


@pytest.fixture
async def base():
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    try:
        db = cliente[nombre]
        await inicializar(db)
        yield db
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


# ---------------------------------------------------------------------------
# El token — sin base de datos
# ---------------------------------------------------------------------------


def test_el_token_lleva_prefijo_reconocible() -> None:
    """Para poder identificarlo en un archivo de configuración o en un pegado."""
    assert vendedores.generar_token().startswith(vendedores.PREFIJO)


def test_dos_tokens_nunca_son_iguales() -> None:
    assert len({vendedores.generar_token() for _ in range(500)}) == 500


def test_el_token_tiene_entropia_suficiente() -> None:
    """32 bytes. Es el número que hace innecesario un KDF lento como Argon2."""
    token = vendedores.generar_token()
    assert len(token) - len(vendedores.PREFIJO) >= 40  # base64url de 32 bytes


def test_el_hash_es_determinístico_y_distinto_del_token() -> None:
    token = vendedores.generar_token()
    assert vendedores.hashear(token) == vendedores.hashear(token)
    assert token not in vendedores.hashear(token)


def test_dos_tokens_distintos_dan_hashes_distintos() -> None:
    assert vendedores.hashear("uno") != vendedores.hashear("otro")


# ---------------------------------------------------------------------------
# Pausas y consentimiento — sin base de datos
# ---------------------------------------------------------------------------


def test_una_maquina_inactiva_esta_pausada() -> None:
    """Nace inactiva: instalar no es activar."""
    assert vendedores.esta_pausada({"activo": False})


def test_una_maquina_activa_sin_pausa_no_esta_pausada() -> None:
    assert not vendedores.esta_pausada({"activo": True, "pausado_hasta": None}, ahora=AHORA)


def test_el_vendedor_puede_pausar_su_propia_maquina() -> None:
    """ "Pausar por hoy", desde el ícono de la barra de menú."""
    maquina = {"activo": True, "pausado_hasta": AHORA + timedelta(hours=3)}
    assert vendedores.esta_pausada(maquina, ahora=AHORA)


def test_la_pausa_del_vendedor_se_vence_sola() -> None:
    maquina = {"activo": True, "pausado_hasta": AHORA - timedelta(minutes=1)}
    assert not vendedores.esta_pausada(maquina, ahora=AHORA)


def test_sin_consentimiento_no_se_le_encolan_envios() -> None:
    """Salen mensajes en su nombre, desde su línea. Tiene que constar que lo sabe."""
    assert not vendedores.puede_enviar({"acepto_condiciones_en": None})
    assert vendedores.puede_enviar({"acepto_condiciones_en": AHORA})


# ---------------------------------------------------------------------------
# Alta, baja y autenticación — con base
# ---------------------------------------------------------------------------


@sin_mongo
async def test_dar_de_alta_devuelve_un_token_que_autentica(base) -> None:
    alta = await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    encontrada = await vendedores.autenticar(base, alta.token)

    assert encontrada is not None
    assert encontrada["maquina"] == "mac-rocio"


@sin_mongo
async def test_el_token_en_claro_no_queda_guardado(base) -> None:
    """Se muestra una vez y después no se puede recuperar de ningún lado."""
    alta = await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    documento = await base["vendedores"].find_one({"maquina": "mac-rocio"})

    assert alta.token not in str(documento)
    assert documento["token_hash"] == vendedores.hashear(alta.token)


@sin_mongo
async def test_una_maquina_nace_inactiva(base) -> None:
    """Instalar no es activar. Se activan de a una, según el calendario."""
    await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    documento = await base["vendedores"].find_one({"maquina": "mac-rocio"})

    assert documento["activo"] is False
    assert documento["acepto_condiciones_en"] is None


@sin_mongo
async def test_no_se_pueden_dar_de_alta_dos_maquinas_con_el_mismo_nombre(base) -> None:
    await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    with pytest.raises(vendedores.MaquinaDuplicada):
        await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Otra")


@sin_mongo
async def test_un_token_inventado_no_autentica(base) -> None:
    await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    assert await vendedores.autenticar(base, "sgc_inventado") is None


@pytest.mark.parametrize("token", [None, "", "   ", "sin-prefijo", "sgc_"])
@sin_mongo
async def test_un_token_vacio_o_mal_formado_no_es_un_caso_especial(base, token) -> None:
    """No coincide con nada, igual que uno inventado. Sin ramas aparte."""
    await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    assert await vendedores.autenticar(base, token) is None


@sin_mongo
async def test_rotar_el_token_invalida_el_anterior(base) -> None:
    alta = await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    nueva = await vendedores.rotar_token(base, "mac-rocio")

    assert await vendedores.autenticar(base, alta.token) is None
    assert await vendedores.autenticar(base, nueva.token) is not None


@sin_mongo
async def test_dar_de_baja_revoca_el_token(base) -> None:
    """Revocar es borrar la máquina: no hay dos mecanismos."""
    alta = await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    await vendedores.dar_de_baja(base, "mac-rocio")

    assert await vendedores.autenticar(base, alta.token) is None


@sin_mongo
async def test_rotar_o_borrar_una_maquina_que_no_existe_falla(base) -> None:
    with pytest.raises(vendedores.MaquinaDesconocida):
        await vendedores.rotar_token(base, "no-existe")
    with pytest.raises(vendedores.MaquinaDesconocida):
        await vendedores.dar_de_baja(base, "no-existe")


@sin_mongo
async def test_el_latido_guarda_el_diagnostico(base) -> None:
    await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    await vendedores.registrar_latido(
        base,
        "mac-rocio",
        diagnostico={"chrome": "ok", "whatsapp_sesion": "pide_qr"},
        version_agente="0.2.0",
        ahora=AHORA,
    )

    documento = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert documento["diagnostico"]["whatsapp_sesion"] == "pide_qr"
    assert documento["version_agente"] == "0.2.0"
    assert documento["ultimo_latido"] == AHORA
