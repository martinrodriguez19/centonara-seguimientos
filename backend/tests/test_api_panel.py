"""Tests de los endpoints del panel.

Van contra la aplicación real y una base real: lo que interesa es que sin
sesión no se pueda hacer nada, que el botón encole, y que el kill switch tenga
efecto sobre lo que ve el agente.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app import db
from app.config import obtener_configuracion
from app.core import auditoria, cola, configuracion, vendedores
from app.core.esquema import inicializar
from app.main import app

CLAVE = "clave-de-prueba"
SECRETO = "secreto-de-prueba-largo"

sin_mongo = pytest.mark.skipif(
    not os.environ.get("MONGO_URL_TESTS"), reason="necesita un Mongo real"
)


@pytest.fixture(autouse=True)
def configurar(monkeypatch):
    monkeypatch.setenv("PANEL_PASSWORD", CLAVE)
    monkeypatch.setenv("SESION_SECRET", SECRETO)
    obtener_configuracion.cache_clear()
    yield
    obtener_configuracion.cache_clear()


@pytest.fixture
async def base(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient

    cliente = AsyncIOMotorClient(os.environ["MONGO_URL_TESTS"], tz_aware=True)
    nombre = f"seguimiento_test_{uuid4().hex[:12]}"
    db_prueba = cliente[nombre]
    await inicializar(db_prueba)
    monkeypatch.setattr(db, "obtener_base", lambda: db_prueba)
    try:
        yield db_prueba
    finally:
        await cliente.drop_database(nombre)
        cliente.close()


@pytest.fixture
async def http():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://prueba") as cliente:
        yield cliente


@pytest.fixture
async def adentro(http, base):
    """Un cliente ya logueado."""
    respuesta = await http.post("/api/sesion", json={"clave": CLAVE})
    assert respuesta.status_code == 200
    return http


@pytest.fixture
async def maquina_lista(base):
    alta = await vendedores.dar_de_alta(base, maquina="mac-rocio", nombre="Rocío")
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"},
        {"$set": {"activo": True, "acepto_condiciones_en": datetime.now(UTC)}},
    )
    return alta


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", ["/api/estado", "/api/configuracion", "/api/historial"])
@sin_mongo
async def test_sin_sesion_no_se_puede_leer_nada(http, base, ruta) -> None:
    assert (await http.get(ruta)).status_code == 401


@pytest.mark.parametrize("ruta", ["/api/corridas", "/api/sistema/pausa", "/api/vendedores"])
@sin_mongo
async def test_sin_sesion_no_se_puede_hacer_nada(http, base, ruta) -> None:
    assert (await http.post(ruta, json={})).status_code == 401


@sin_mongo
async def test_la_contraseña_correcta_deja_entrar(http, base) -> None:
    respuesta = await http.post("/api/sesion", json={"clave": CLAVE})
    assert respuesta.status_code == 200
    assert "sesion" in respuesta.cookies


@sin_mongo
async def test_la_contraseña_incorrecta_no(http, base) -> None:
    respuesta = await http.post("/api/sesion", json={"clave": "otra"})
    assert respuesta.status_code == 401
    assert "sesion" not in respuesta.cookies


@sin_mongo
async def test_la_cookie_no_la_puede_leer_el_javascript(http, base) -> None:
    """`httponly`: un script inyectado en la página no se la lleva."""
    respuesta = await http.post("/api/sesion", json={"clave": CLAVE})
    assert "httponly" in respuesta.headers["set-cookie"].lower()


@sin_mongo
async def test_salir_borra_la_cookie(adentro) -> None:
    respuesta = await adentro.delete("/api/sesion")
    assert respuesta.status_code == 200
    assert (await adentro.get("/api/estado")).status_code == 401


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_estado_de_una_base_vacia_no_rompe(adentro) -> None:
    cuerpo = (await adentro.get("/api/estado")).json()
    assert cuerpo["maquinas"] == []
    assert cuerpo["enviados_hoy"] == 0
    assert cuerpo["corrida_en_curso"] is None


@sin_mongo
async def test_una_maquina_sin_latido_se_ve_caida(adentro, maquina_lista) -> None:
    maquina = (await adentro.get("/api/estado")).json()["maquinas"][0]
    assert maquina["online"] is False


@sin_mongo
async def test_una_maquina_que_acaba_de_latir_se_ve_online(adentro, base, maquina_lista) -> None:
    await vendedores.registrar_latido(base, "mac-rocio")
    maquina = (await adentro.get("/api/estado")).json()["maquinas"][0]
    assert maquina["online"] is True


@sin_mongo
async def test_un_latido_viejo_no_alcanza(adentro, base, maquina_lista) -> None:
    viejo = datetime.now(UTC) - timedelta(minutes=10)
    await vendedores.registrar_latido(base, "mac-rocio", ahora=viejo)

    maquina = (await adentro.get("/api/estado")).json()["maquinas"][0]
    assert maquina["online"] is False


@sin_mongo
async def test_el_panel_dice_QUE_chequeo_fallo(adentro, base, maquina_lista) -> None:
    """⚠️ La diferencia con el MVP.

    Allá los siete problemas conocidos eran un HTTP 502 mudo. Acá la pantalla
    tiene el nombre del chequeo, que es lo único accionable.
    """
    await vendedores.registrar_latido(
        base,
        "mac-rocio",
        diagnostico={"claude_bin": "falla", "device_id": "falla", "claude_md": "ok"},
    )

    maquina = (await adentro.get("/api/estado")).json()["maquinas"][0]
    assert maquina["chequeos_fallando"] == ["claude_bin", "device_id"]


@sin_mongo
async def test_los_na_no_aparecen_como_fallas(adentro, base, maquina_lista) -> None:
    await vendedores.registrar_latido(
        base, "mac-rocio", diagnostico={"selectores": "n/a", "claude_bin": "ok"}
    )
    maquina = (await adentro.get("/api/estado")).json()["maquinas"][0]
    assert maquina["chequeos_fallando"] == []


@sin_mongo
async def test_el_estado_dice_si_los_destinos_estan_abiertos(adentro, base) -> None:
    """Es lo que decide la banda de "modo prueba" en la pantalla.

    Mientras la lista no esté abierta, esto NO es producción por más que el
    servidor lo sea.
    """
    assert (await adentro.get("/api/estado")).json()["destinos_abiertos"] is False

    await configuracion.actualizar(base, {"destinos_permitidos": [configuracion.TODOS]})
    assert (await adentro.get("/api/estado")).json()["destinos_abiertos"] is True


# ---------------------------------------------------------------------------
# Máquinas
# ---------------------------------------------------------------------------


@sin_mongo
async def test_dar_de_alta_devuelve_el_token_una_vez(adentro) -> None:
    respuesta = await adentro.post(
        "/api/vendedores", json={"maquina": "mac-juan", "nombre": "Juan"}
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["token"].startswith("sgc_")
    assert "no se va a volver a mostrar" in cuerpo["aviso"]


@sin_mongo
async def test_una_maquina_nace_inactiva(adentro) -> None:
    """Instalar no es activar."""
    await adentro.post("/api/vendedores", json={"maquina": "mac-juan", "nombre": "Juan"})
    maquina = (await adentro.get("/api/estado")).json()["maquinas"][0]
    assert maquina["activo"] is False
    assert maquina["pausada"] is True


@pytest.mark.parametrize("nombre", ["MAC-Juan", "mac juan", "-mac", "m", "mac_juan", "máquina"])
@sin_mongo
async def test_el_identificador_de_maquina_es_acotado(adentro, nombre) -> None:
    """Va en la URL y en la configuración de la Mac: sin mayúsculas ni espacios."""
    respuesta = await adentro.post("/api/vendedores", json={"maquina": nombre, "nombre": "X"})
    assert respuesta.status_code == 422


@sin_mongo
async def test_dos_maquinas_con_el_mismo_nombre_dan_409(adentro) -> None:
    await adentro.post("/api/vendedores", json={"maquina": "mac-juan", "nombre": "Juan"})
    respuesta = await adentro.post(
        "/api/vendedores", json={"maquina": "mac-juan", "nombre": "Otro"}
    )
    assert respuesta.status_code == 409


@sin_mongo
async def test_rotar_el_token_invalida_el_anterior(adentro, base, maquina_lista) -> None:
    respuesta = await adentro.post("/api/vendedores/mac-rocio/token")
    nuevo = respuesta.json()["token"]

    assert await vendedores.autenticar(base, maquina_lista.token) is None
    assert await vendedores.autenticar(base, nuevo) is not None


@sin_mongo
async def test_dar_de_baja_revoca_el_token(adentro, base, maquina_lista) -> None:
    await adentro.delete("/api/vendedores/mac-rocio")
    assert await vendedores.autenticar(base, maquina_lista.token) is None


@sin_mongo
async def test_el_consentimiento_se_guarda_como_fecha(adentro, base, maquina_lista) -> None:
    """ "¿Desde cuándo sabe?" tiene que responderse con una fecha, no con un sí."""
    await adentro.patch("/api/vendedores/mac-rocio", json={"acepto_condiciones": True})

    documento = await base["vendedores"].find_one({"maquina": "mac-rocio"})
    assert isinstance(documento["acepto_condiciones_en"], datetime)

    eventos = await auditoria.recientes(base, que=auditoria.Que.CONSENTIMIENTO_REGISTRADO)
    assert len(eventos) == 1


@sin_mongo
async def test_editar_una_maquina_que_no_existe_da_404(adentro) -> None:
    respuesta = await adentro.patch("/api/vendedores/no-existe", json={"activo": True})
    assert respuesta.status_code == 404


# ---------------------------------------------------------------------------
# El botón
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_boton_encola_un_job_por_maquina(adentro, base, maquina_lista) -> None:
    respuesta = await adentro.post("/api/corridas", json={})
    assert respuesta.status_code == 202

    cuerpo = respuesta.json()
    assert cuerpo["maquinas"] == ["mac-rocio"]
    assert cuerpo["jobs"] == 1
    assert await cola.tomar(base, "mac-rocio") is not None


@sin_mongo
async def test_el_boton_sin_maquinas_avisa_en_vez_de_no_hacer_nada(adentro) -> None:
    """ "No pasó nada" sin explicación es peor que un mensaje."""
    respuesta = await adentro.post("/api/corridas", json={})
    assert respuesta.status_code == 409


@sin_mongo
async def test_el_boton_no_le_da_trabajo_a_una_maquina_pausada(
    adentro, base, maquina_lista
) -> None:
    await base["vendedores"].update_one(
        {"maquina": "mac-rocio"},
        {"$set": {"pausado_hasta": datetime.now(UTC) + timedelta(hours=3)}},
    )
    respuesta = await adentro.post("/api/corridas", json={})
    assert respuesta.status_code == 409


@sin_mongo
async def test_el_boton_con_el_kill_switch_puesto_da_423(adentro, base, maquina_lista) -> None:
    await configuracion.pausar(base, pausado=True, quien="prueba")
    respuesta = await adentro.post("/api/corridas", json={})
    assert respuesta.status_code == 423


@sin_mongo
async def test_disparar_queda_en_la_auditoria(adentro, base, maquina_lista) -> None:
    await adentro.post("/api/corridas", json={})
    eventos = await auditoria.recientes(base, que=auditoria.Que.CORRIDA_DISPARADA)
    assert len(eventos) == 1


@sin_mongo
async def test_el_progreso_de_una_corrida(adentro, base, maquina_lista) -> None:
    corrida_id = (await adentro.post("/api/corridas", json={})).json()["id"]

    antes = (await adentro.get(f"/api/corridas/{corrida_id}")).json()
    assert antes["jobs"]["pendientes"] == 1
    assert antes["terminada"] is False

    job = await cola.tomar(base, "mac-rocio")
    await cola.reportar(base, job["_id"], ok=True)

    despues = (await adentro.get(f"/api/corridas/{corrida_id}")).json()
    assert despues["jobs"]["pendientes"] == 0
    assert despues["terminada"] is True


@sin_mongo
async def test_una_corrida_que_no_existe_da_404(adentro) -> None:
    assert (await adentro.get("/api/corridas/no-es-un-id")).status_code == 404


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_kill_switch_frena_al_agente(adentro, base, maquina_lista) -> None:
    """Sin empujar nada: el agente pregunta y a partir del próximo recibe 423."""
    await cola.encolar(base, tipo=cola.Tipo.DIAGNOSTICO, maquina="mac-rocio")

    await adentro.post("/api/sistema/pausa", json={"pausado": True})

    respuesta = await adentro.get(
        "/api/agente/jobs/proximo", headers={"Authorization": f"Bearer {maquina_lista.token}"}
    )
    assert respuesta.status_code == 423


@sin_mongo
async def test_soltar_el_kill_switch_devuelve_el_trabajo(adentro, base, maquina_lista) -> None:
    await cola.encolar(base, tipo=cola.Tipo.DIAGNOSTICO, maquina="mac-rocio")
    await adentro.post("/api/sistema/pausa", json={"pausado": True})
    await adentro.post("/api/sistema/pausa", json={"pausado": False})

    respuesta = await adentro.get(
        "/api/agente/jobs/proximo", headers={"Authorization": f"Bearer {maquina_lista.token}"}
    )
    assert respuesta.status_code == 200


@sin_mongo
async def test_quien_aprieta_el_kill_switch_queda_registrado(adentro, base) -> None:
    await adentro.post("/api/sistema/pausa", json={"pausado": True})
    eventos = await auditoria.recientes(base, que=auditoria.Que.KILL_SWITCH)
    assert eventos[0]["detalle"]["pausado"] is True


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_cliente_puede_cambiar_un_tope(adentro) -> None:
    respuesta = await adentro.patch("/api/configuracion", json={"tope_diario_maquina": 5})
    assert respuesta.json()["tope_diario_maquina"] == 5


@sin_mongo
async def test_el_cliente_puede_agregar_palabras_de_su_rubro(adentro) -> None:
    respuesta = await adentro.patch(
        "/api/configuracion", json={"palabras_conflicto": ["reclamo", "roto en obra"]}
    )
    assert "roto en obra" in respuesta.json()["palabras_conflicto"]


@sin_mongo
async def test_un_campo_que_no_existe_se_rechaza(adentro) -> None:
    respuesta = await adentro.patch("/api/configuracion", json={"tope_inventado": 5})
    assert respuesta.status_code == 422


@sin_mongo
async def test_abrir_los_destinos_queda_auditado_con_el_antes_y_el_despues(adentro, base) -> None:
    """⚠️ R4: es lo que decide si el sistema puede alcanzar a alguien real."""
    await adentro.patch("/api/configuracion", json={"destinos_permitidos": ["+5491144405036"]})
    await adentro.patch("/api/configuracion", json={"destinos_permitidos": ["*"]})

    eventos = await auditoria.recientes(base, que=auditoria.Que.DESTINOS_CAMBIADOS)
    assert len(eventos) == 2

    ultimo = eventos[0]["detalle"]
    assert ultimo["antes"] == ["+5491144405036"]
    assert ultimo["despues"] == ["*"]
    assert ultimo["abierto_a_todos"] is True


@sin_mongo
async def test_un_cambio_comun_no_se_audita_como_cambio_de_destinos(adentro, base) -> None:
    await adentro.patch("/api/configuracion", json={"largo_maximo": 400})
    assert await auditoria.recientes(base, que=auditoria.Que.DESTINOS_CAMBIADOS) == []


@sin_mongo
async def test_los_destinos_se_guardan_en_e164(adentro, base) -> None:
    """⚠️ R4: lo que se guarda tiene que ser lo que el guardrail compara.

    `destino_permitido()` hace `contacto_id in permitidos`, una comparación de
    cadenas exacta, y el agente trae el número ya normalizado. Un número
    guardado como lo escribe una persona —con espacios y guiones, que es como
    los manda un cliente por WhatsApp— no coincide con nada.

    Falla cerrado, que es la dirección segura, pero en silencio: la pantalla
    muestra tres destinos habilitados y el sistema entiende uno.
    """
    respuesta = await adentro.patch(
        "/api/configuracion",
        json={"destinos_permitidos": ["+54 9 11 2323-1151", "+5491136007586"]},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["destinos_permitidos"] == ["+5491123231151", "+5491136007586"]

    guardada = await configuracion.obtener(base)
    for numero in ("+5491123231151", "+5491136007586"):
        assert configuracion.destino_permitido(guardada, numero)


@sin_mongo
async def test_dos_formas_del_mismo_numero_no_cuentan_como_dos_destinos(adentro) -> None:
    """El tope de la prueba real es "exactamente estos tres y ninguno más"."""
    respuesta = await adentro.patch(
        "/api/configuracion",
        json={"destinos_permitidos": ["+54 9 11 2323-1151", "+5491123231151"]},
    )
    assert respuesta.json()["destinos_permitidos"] == ["+5491123231151"]


@sin_mongo
async def test_un_numero_ilegible_no_entra_a_la_lista(adentro, base) -> None:
    """Antes de esto se guardaba igual, y no coincidía con nada nunca."""
    respuesta = await adentro.patch(
        "/api/configuracion", json={"destinos_permitidos": ["no soy un numero"]}
    )
    assert respuesta.status_code == 422
    assert await configuracion.obtener(base) is not None
    assert (await configuracion.obtener(base))["destinos_permitidos"] == []


@sin_mongo
async def test_el_asterisco_sobrevive_a_la_normalizacion(adentro, base) -> None:
    """`*` no es un número: es la marca de lista abierta, y no se puede romper."""
    respuesta = await adentro.patch("/api/configuracion", json={"destinos_permitidos": ["*"]})
    assert respuesta.json()["destinos_permitidos"] == ["*"]
    assert configuracion.destino_permitido(await configuracion.obtener(base), "+5491100000000")


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------


@sin_mongo
async def test_el_historial_devuelve_lo_ultimo(adentro, base, maquina_lista) -> None:
    await adentro.post("/api/corridas", json={})
    await adentro.post("/api/sistema/pausa", json={"pausado": True})

    eventos = (await adentro.get("/api/historial")).json()["eventos"]
    assert len(eventos) >= 2
    assert eventos[0]["que"] == "kill_switch", "del más nuevo al más viejo"
    assert isinstance(eventos[0]["_id"], str), "serializable a JSON"


# ---------------------------------------------------------------------------
# Revisión de borradores
# ---------------------------------------------------------------------------


async def _con_borradores(base, http, cuantos: int = 3, **extra):
    """Una corrida con borradores ya validados, lista para revisar."""
    from bson import ObjectId

    from app.core import configuracion as config_mod
    from app.core import mensajes, validacion

    await config_mod.actualizar(base, {"destinos_permitidos": ["*"]})
    corrida_id = (
        await base["corridas"].insert_one(
            {
                "disparada_por": "panel",
                "tipo": "generacion",
                "modo": "prueba",
                "estado": "generando",
                "maquinas": ["mac-rocio"],
                "creada_en": datetime.now(UTC),
            }
        )
    ).inserted_id

    for n in range(cuantos):
        await mensajes.crear_borrador(
            base,
            corrida_id=corrida_id,
            maquina="mac-rocio",
            contacto_id=f"+54911000{n:05d}",
            contacto_nombre=f"Contacto {n}",
            texto="Hola, quedó pendiente lo que hablamos. ¿Seguimos?",
            resumen_ultimo=extra.get("resumen", "preguntó por precio de chapa"),
        )

    await validacion.validar_corrida(base, corrida_id)
    assert isinstance(corrida_id, ObjectId)
    return corrida_id


@sin_mongo
async def test_la_pantalla_de_revision_pone_los_retenidos_primero(
    adentro, base, maquina_lista
) -> None:
    """Son los que requieren una decisión: van arriba."""
    corrida_id = await _con_borradores(base, adentro, cuantos=3)
    from app.core import mensajes

    # Uno se retiene a mano, para que haya de los dos tipos.
    listos = await mensajes.de_la_corrida(base, corrida_id)
    await base["mensajes"].update_one(
        {"_id": listos[2]["_id"]},
        {"$set": {"estado": "RETENIDO", "senales": ["PALABRA_CONFLICTO"]}},
    )

    cuerpo = (await adentro.get(f"/api/corridas/{corrida_id}/mensajes")).json()
    assert cuerpo["mensajes"][0]["estado"] == "RETENIDO"


@sin_mongo
async def test_cada_retenido_dice_por_que(adentro, base, maquina_lista) -> None:
    """Sin el motivo, alguien tendría que releer el chat para adivinar."""
    corrida_id = await _con_borradores(base, adentro, cuantos=1, resumen="puso un reclamo")

    cuerpo = (await adentro.get(f"/api/corridas/{corrida_id}/mensajes")).json()
    mensaje = cuerpo["mensajes"][0]
    assert mensaje["estado"] == "RETENIDO"
    assert "PALABRA_CONFLICTO" in mensaje["senales"]


@sin_mongo
async def test_editar_con_un_placeholder_devuelve_422_y_no_rompe_nada(
    adentro, base, maquina_lista
) -> None:
    """Lo que corresponde es que la persona lo corrija, no perder lo que escribió."""
    corrida_id = await _con_borradores(base, adentro, cuantos=1)
    mensaje_id = (await adentro.get(f"/api/corridas/{corrida_id}/mensajes")).json()["mensajes"][0][
        "id"
    ]

    respuesta = await adentro.patch(f"/api/mensajes/{mensaje_id}", json={"texto": "Hola {nombre}"})
    assert respuesta.status_code == 422


@sin_mongo
async def test_vetar_es_terminal(adentro, base, maquina_lista) -> None:
    corrida_id = await _con_borradores(base, adentro, cuantos=1)
    mensaje_id = (await adentro.get(f"/api/corridas/{corrida_id}/mensajes")).json()["mensajes"][0][
        "id"
    ]

    assert (await adentro.post(f"/api/mensajes/{mensaje_id}/veto")).status_code == 200
    # No se resucita: si hay que mandarlo, se genera uno nuevo.
    assert (await adentro.post(f"/api/mensajes/{mensaje_id}/liberar")).status_code == 409


@sin_mongo
async def test_el_segundo_boton_encola_lo_que_quedo_listo(adentro, base, maquina_lista) -> None:
    corrida_id = await _con_borradores(base, adentro, cuantos=3)

    respuesta = await adentro.post(f"/api/corridas/{corrida_id}/enviar", json={})

    assert respuesta.status_code == 202
    cuerpo = respuesta.json()
    assert cuerpo["mensajes"] == 3
    assert cuerpo["modo"] == "prueba", "para que salga de verdad hay que decirlo"


@sin_mongo
async def test_el_segundo_boton_con_el_kill_switch_puesto_da_423(
    adentro, base, maquina_lista
) -> None:
    corrida_id = await _con_borradores(base, adentro, cuantos=1)
    await configuracion.pausar(base, pausado=True, quien="prueba")

    respuesta = await adentro.post(f"/api/corridas/{corrida_id}/enviar", json={})
    assert respuesta.status_code == 423


@sin_mongo
async def test_el_estado_ofrece_revisar_cuando_la_generacion_termino(
    adentro, base, maquina_lista
) -> None:
    """Una corrida terminada deja borradores esperando: la pantalla tiene que decirlo."""
    corrida_id = await _con_borradores(base, adentro, cuantos=1)

    cuerpo = (await adentro.get("/api/estado")).json()
    assert cuerpo["ultima_corrida"]["id"] == str(corrida_id)
