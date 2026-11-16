"""Las sesiones de cada máquina y su reconexión (D69-D73), sin Mongo.

Corren contra `base_falsa.BaseFalsa`: el dueño pidió que estas pruebas no
dependan de Docker. Lo que fija esto:

- el latido guarda las sesiones, anota transiciones y marca acciones hechas;
- la página pública devuelve EXACTAMENTE los campos de su contrato (D71);
- una reconexión se encola, viaja en el latido y no se puede repetir seguido;
- la línea equivocada pausa la máquina y la saca de las corridas (D72);
- el token de Claude viaja sólo a quien usa otro, y nunca vuelve al panel (D73).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app import db
from app.core import cola, conexiones, corridas, sesion, vendedores
from app.main import app
from tests.base_falsa import BaseFalsa

AHORA = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
TOKEN_CLAUDE = "sk-ant-oat01-" + "x" * 60


@pytest.fixture
def base(monkeypatch) -> BaseFalsa:
    falsa = BaseFalsa()
    monkeypatch.setattr(db, "obtener_base", lambda: falsa)
    return falsa


@pytest.fixture
async def cliente():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://prueba") as http:
        yield http


async def alta(base, maquina="mac-sofia", nombre="Sofía", **extra) -> str:
    hecho = await vendedores.dar_de_alta(base, maquina=maquina, nombre=nombre)
    await base["vendedores"].update_one(
        {"maquina": maquina},
        {"$set": {"activo": True, "ultimo_latido": datetime.now(UTC), **extra}},
    )
    return hecho.token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def leer(base, maquina="mac-sofia") -> dict:
    return await base["vendedores"].find_one({"maquina": maquina})


# ---------------------------------------------------------------------------
# Puro
# ---------------------------------------------------------------------------


class TestNumero:
    def test_coinciden_los_ultimos_diez_digitos(self):
        #  WhatsApp escribe 549…, E.164 +549…; el `9` y el país no importan.
        assert conexiones.numero_coincide("+5491144405036", "5491144405036") is True
        assert conexiones.numero_coincide("+541144405036", "5491144405036") is True

    def test_distinto_es_false(self):
        assert conexiones.numero_coincide("+5491144405036", "5491199998888") is False

    def test_sin_dato_no_se_compara(self):
        assert conexiones.numero_coincide(None, "5491144405036") is None
        assert conexiones.numero_coincide("+5491144405036", None) is None
        assert conexiones.numero_coincide("+5491144405036", "123") is None


class TestSemaforos:
    def test_whatsapp_ignora_el_motor_con_la_extension(self):
        vendedor = {
            "sesiones": {
                "whatsapp": {"estado": "ok"},
                "whatsapp_motor": {"estado": "caida"},
            }
        }
        assert conexiones.semaforo_whatsapp(vendedor, {"modo_borrador": "extension"}) == "ok"
        assert conexiones.semaforo_whatsapp(vendedor, {"modo_borrador": "playwright"}) == "caida"

    def test_sin_datos_no_se_sabe(self):
        assert conexiones.semaforo_whatsapp({}, {}) == "desconocido"
        assert conexiones.semaforo_claude({}) == "desconocido"


class TestExclusion:
    def _vendedor(self, **sesiones) -> dict:
        return {
            "maquina": "mac-sofia",
            "activo": True,
            "ultimo_latido": AHORA,
            "sesiones": sesiones,
        }

    def test_la_caida_de_un_job_saca_de_la_corrida(self):
        vendedor = self._vendedor(whatsapp={"estado": "caida", "fuente": "job"})
        assert corridas.motivo_de_exclusion(vendedor, ahora=AHORA) == "sin_whatsapp"

    def test_la_del_disco_no(self):
        #  D69.4: la heurística no deja a nadie afuera; si se equivoca, el job dice la verdad.
        vendedor = self._vendedor(whatsapp={"estado": "caida", "fuente": "disco"})
        assert corridas.motivo_de_exclusion(vendedor, ahora=AHORA) is None

    def test_la_extension_caida_segun_la_sonda(self):
        vendedor = self._vendedor(claude_extension={"estado": "caida", "fuente": "sonda"})
        assert corridas.motivo_de_exclusion(vendedor, ahora=AHORA) == "sin_claude"

    def test_la_linea_equivocada_pausa_y_saca(self):
        vendedor = {
            **self._vendedor(),
            "telefono_linea": "+5491144405036",
            "numero_vinculado": "5491199998888",
        }
        assert vendedores.esta_pausada(vendedor, ahora=AHORA)
        assert corridas.motivo_de_exclusion(vendedor, ahora=AHORA) == "linea_equivocada"

    def test_sin_numero_cargado_no_frena(self):
        vendedor = {**self._vendedor(), "numero_vinculado": "5491199998888"}
        assert not vendedores.esta_pausada(vendedor, ahora=AHORA)


class TestToken:
    def test_reconoce_un_token_de_setup_token(self):
        assert conexiones.token_valido(TOKEN_CLAUDE)
        assert not conexiones.token_valido("hola")
        assert not conexiones.token_valido("sk-ant-con espacio " + "x" * 40)

    def test_viaja_solo_a_quien_usa_otro(self):
        token = {"valor": TOKEN_CLAUDE, "hash": conexiones.hash_corto(TOKEN_CLAUDE)}
        assert conexiones.token_para({}, token, "") == TOKEN_CLAUDE
        assert conexiones.token_para({}, token, "otrohash") == TOKEN_CLAUDE
        assert conexiones.token_para({}, token, token["hash"]) is None
        #  Un agente viejo no manda el hash: no sabría qué hacer con el token.
        assert conexiones.token_para({}, token, None) is None
        assert conexiones.token_para({}, None, "") is None

    def test_el_codigo_nuevo_no_se_reintenta(self):
        assert not cola.Codigo.CLAUDE_SIN_SESION.reintenta


# ---------------------------------------------------------------------------
# Con la base falsa
# ---------------------------------------------------------------------------


class TestRegistrar:
    async def test_anota_la_transicion_y_conserva_el_desde(self, base):
        await alta(base)
        await conexiones.registrar(
            base,
            await leer(base),
            sesiones={"whatsapp": {"estado": "ok", "fuente": "job"}},
            ahora=AHORA,
        )
        await conexiones.registrar(
            base,
            await leer(base),
            sesiones={"whatsapp": {"estado": "ok", "fuente": "disco"}},
            ahora=AHORA + timedelta(hours=1),
        )
        vendedor = await leer(base)
        assert vendedor["sesiones"]["whatsapp"]["desde"] == AHORA
        #  La primera observación no es una transición: no había un "antes".
        assert vendedor.get("sesiones_historial") is None

        await conexiones.registrar(
            base,
            vendedor,
            sesiones={"whatsapp": {"estado": "caida", "fuente": "job"}},
            ahora=AHORA + timedelta(hours=2),
        )
        vendedor = await leer(base)
        assert vendedor["sesiones"]["whatsapp"]["desde"] == AHORA + timedelta(hours=2)
        [cambio] = vendedor["sesiones_historial"]
        assert (cambio["sesion"], cambio["antes"], cambio["estado"]) == ("whatsapp", "ok", "caida")

    async def test_ignora_sesiones_y_estados_desconocidos(self, base):
        await alta(base)
        await conexiones.registrar(
            base,
            await leer(base),
            sesiones={"otra": {"estado": "ok"}, "whatsapp": {"estado": "raro"}},
        )
        assert (await leer(base)).get("sesiones") is None

    async def test_el_numero_se_guarda_en_digitos(self, base):
        await alta(base)
        await conexiones.registrar(base, await leer(base), numero_vinculado="5491144405036:12@c.us")
        assert (await leer(base))["numero_vinculado"] == "549114440503612"


class TestAcciones:
    async def test_se_pide_viaja_y_se_marca_hecha(self, base):
        await alta(base)
        accion = await conexiones.pedir(base, await leer(base), "abrir_whatsapp", ahora=AHORA)
        [pendiente] = conexiones.pendientes(await leer(base), ahora=AHORA)
        assert pendiente["id"] == accion["id"]

        await conexiones.registrar(
            base,
            await leer(base),
            acciones_hechas=[{"id": accion["id"], "resultado": "abierto"}],
            ahora=AHORA,
        )
        assert conexiones.pendientes(await leer(base), ahora=AHORA) == []
        assert (await leer(base))["acciones"][0]["resultado"] == "abierto"

    async def test_no_se_repite_en_menos_de_dos_minutos(self, base):
        await alta(base)
        await conexiones.pedir(base, await leer(base), "abrir_claude", ahora=AHORA)
        with pytest.raises(conexiones.DemasiadoPronto):
            await conexiones.pedir(
                base, await leer(base), "abrir_claude", ahora=AHORA + timedelta(seconds=30)
            )
        #  Otro tipo sí, y el mismo pasado el tope también.
        await conexiones.pedir(base, await leer(base), "verificar", ahora=AHORA)
        await conexiones.pedir(
            base, await leer(base), "abrir_claude", ahora=AHORA + timedelta(minutes=3)
        )

    async def test_una_accion_vieja_vence(self, base):
        await alta(base)
        await conexiones.pedir(base, await leer(base), "abrir_whatsapp", ahora=AHORA)
        assert conexiones.pendientes(await leer(base), ahora=AHORA + timedelta(minutes=11)) == []


class TestPublico:
    async def test_devuelve_exactamente_los_campos_del_contrato(self, base, cliente):
        await alta(
            base,
            telefono_linea="+5491144405036",
            numero_vinculado="5491144405036",
            diagnostico={"perfiles": "falla"},
            sesiones={"whatsapp": {"estado": "caida", "fuente": "job", "detalle": "QR"}},
        )
        await alta(base, maquina="mac-off", nombre="Apagada")
        await base["vendedores"].update_one({"maquina": "mac-off"}, {"$set": {"activo": False}})

        respuesta = await cliente.get("/api/publico/conexiones")
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert set(cuerpo) == {"maquinas", "pedir_codigo_a"}
        [maquina] = cuerpo["maquinas"]  # la inactiva no aparece
        assert set(maquina) == {"maquina", "nombre", "estado", "whatsapp", "claude", "reconexion"}
        assert maquina["whatsapp"] == "caida"
        assert maquina["estado"] == "viva"
        assert "5036" not in respuesta.text  # ningún número, ni el detalle

    async def test_reconectar_encola_audita_y_no_devuelve_el_mail(self, base, cliente):
        await alta(base)
        await base["configuracion"].update_one(
            {"_id": "unica"},
            {"$set": {"cuenta_claude_mail": "cuenta@empresa.com"}},
            upsert=True,
        )
        respuesta = await cliente.post(
            "/api/publico/conexiones/mac-sofia/claude", headers={"x-forwarded-for": "1.2.3.4"}
        )
        assert respuesta.status_code == 202
        assert "cuenta@empresa.com" not in respuesta.text

        [accion] = (await leer(base))["acciones"]
        assert accion["tipo"] == "abrir_claude"
        assert accion["datos"] == {"mail": "cuenta@empresa.com"}  # éste sí viaja a la máquina
        [evento] = base["auditoria"].documentos
        assert evento["que"] == "reconexion_pedida"
        assert evento["detalle"]["ip"] == "1.2.3.4"

        otra = await cliente.post("/api/publico/conexiones/mac-sofia/claude")
        assert otra.status_code == 429

    async def test_maquina_inexistente_o_inactiva(self, base, cliente):
        assert (await cliente.post("/api/publico/conexiones/mac-nadie/whatsapp")).status_code == 404
        assert (await cliente.post("/api/publico/conexiones/mac-x/otra")).status_code == 422

    async def test_la_reconexion_en_curso_aparece_en_la_tarjeta(self, base, cliente):
        await alta(base)
        await cliente.post("/api/publico/conexiones/mac-sofia/whatsapp")
        [maquina] = (await cliente.get("/api/publico/conexiones")).json()["maquinas"]
        assert maquina["reconexion"]["tipo"] == "whatsapp"
        assert maquina["reconexion"]["hecha"] is False


class TestLatido:
    async def test_guarda_sesiones_y_entrega_acciones(self, base, cliente):
        token = await alta(base)
        await cliente.post("/api/publico/conexiones/mac-sofia/whatsapp")

        respuesta = await cliente.post(
            "/api/agente/latido",
            headers=auth(token),
            json={
                "diagnostico": {},
                "sesiones": {"whatsapp": {"estado": "caida", "fuente": "disco"}},
                "numero_vinculado": "5491144405036",
            },
        )
        assert respuesta.status_code == 200
        [accion] = respuesta.json()["acciones"]
        assert accion["tipo"] == "abrir_whatsapp"
        vendedor = await leer(base)
        assert vendedor["sesiones"]["whatsapp"]["estado"] == "caida"
        assert vendedor["numero_vinculado"] == "5491144405036"

        respuesta = await cliente.post(
            "/api/agente/latido",
            headers=auth(token),
            json={"acciones_hechas": [{"id": accion["id"], "resultado": "abierto"}]},
        )
        assert respuesta.json()["acciones"] == []

    async def test_un_agente_viejo_sigue_andando(self, base, cliente):
        token = await alta(base)
        respuesta = await cliente.post(
            "/api/agente/latido", headers=auth(token), json={"diagnostico": {}}
        )
        assert respuesta.status_code == 200
        assert "claude_token" not in respuesta.json()

    async def test_el_token_viaja_hasta_que_la_maquina_lo_usa(self, base, cliente):
        token = await alta(base)
        await conexiones.cargar_token(base, TOKEN_CLAUDE)

        respuesta = await cliente.post(
            "/api/agente/latido", headers=auth(token), json={"claude_token_hash": ""}
        )
        assert respuesta.json()["claude_token"] == TOKEN_CLAUDE

        respuesta = await cliente.post(
            "/api/agente/latido",
            headers=auth(token),
            json={"claude_token_hash": conexiones.hash_corto(TOKEN_CLAUDE)},
        )
        assert "claude_token" not in respuesta.json()


class TestPanel:
    @pytest.fixture
    def cookies(self, configurar) -> dict[str, str]:
        config = configurar(sesion_secret="s" * 32, panel_password="clave")
        return {sesion.NOMBRE_COOKIE: sesion.emitir(config.sesion_secret)}

    async def test_el_token_se_carga_y_nunca_se_devuelve(self, base, cliente, cookies):
        await alta(base)
        cliente.cookies.update(cookies)

        respuesta = await cliente.post("/api/sistema/token-claude", json={"token": TOKEN_CLAUDE})
        assert respuesta.status_code == 200
        assert TOKEN_CLAUDE not in respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["cargado"] is True
        assert (cuerpo["maquinas_al_dia"], cuerpo["maquinas_activas"]) == (0, 1)

        configuracion = await cliente.get("/api/configuracion")
        assert TOKEN_CLAUDE not in configuracion.text
        [evento] = base["auditoria"].documentos
        assert TOKEN_CLAUDE not in str(evento)

        assert (
            await cliente.post("/api/sistema/token-claude", json={"token": "cualquiera"})
        ).status_code == 400

        borrado = await cliente.delete("/api/sistema/token-claude")
        assert borrado.json()["cargado"] is False

    async def test_sin_login_no(self, base, cliente, configurar):
        configurar(sesion_secret="s" * 32, panel_password="clave")
        assert (await cliente.get("/api/sistema/token-claude")).status_code == 401

    async def test_el_numero_de_la_linea_se_normaliza(self, base, cliente, cookies):
        await alta(base)
        cliente.cookies.update(cookies)
        respuesta = await cliente.patch(
            "/api/vendedores/mac-sofia", json={"telefono_linea": "11 4440-5036"}
        )
        assert respuesta.status_code == 200
        assert (await leer(base))["telefono_linea"] == "+5491144405036"

        await cliente.patch("/api/vendedores/mac-sofia", json={"telefono_linea": ""})
        assert (await leer(base))["telefono_linea"] is None


class TestAlertas:
    async def _codigos(self, base, ahora=None) -> dict[str, str]:
        from app.core import alertas

        return {
            a.codigo: str(a.nivel)
            for a in await alertas._sesiones(base, ahora or datetime.now(UTC))
        }

    async def test_whatsapp_caido_segun_un_job_es_urgente_y_segun_el_disco_aviso(self, base):
        await alta(base, sesiones={"whatsapp": {"estado": "caida", "fuente": "job"}})
        assert (await self._codigos(base))["whatsapp_desconectado"] == "urgente"
        await base["vendedores"].update_one(
            {"maquina": "mac-sofia"}, {"$set": {"sesiones.whatsapp.fuente": "disco"}}
        )
        assert (await self._codigos(base))["whatsapp_desconectado"] == "aviso"

    async def test_el_dueno_se_entera_de_que_tiene_que_pasar_el_codigo(self, base):
        await alta(base, sesiones={"claude_extension": {"estado": "caida", "fuente": "job"}})
        await conexiones.pedir(base, await leer(base), "abrir_claude")
        codigos = await self._codigos(base)
        assert codigos["reconexion_claude"] == "urgente"
        #  No se duplica con "se desconectó la extensión".
        assert "claude_desconectado" not in codigos

        await conexiones.registrar(
            base,
            await leer(base),
            sesiones={"claude_extension": {"estado": "ok", "fuente": "sonda"}},
            ahora=datetime.now(UTC) + timedelta(seconds=5),
        )
        assert "reconexion_claude" not in await self._codigos(base)

    async def test_claude_code_sin_sesion_y_linea_equivocada(self, base):
        await alta(
            base,
            sesiones={"claude_cli": {"estado": "caida", "fuente": "job"}},
            telefono_linea="+5491144405036",
            numero_vinculado="5491199998888",
        )
        codigos = await self._codigos(base)
        assert codigos["claude_code_sin_sesion"] == "urgente"
        assert codigos["linea_equivocada"] == "urgente"

    async def test_el_token_por_vencer(self, base):
        await conexiones.cargar_token(base, TOKEN_CLAUDE, ahora=AHORA)
        assert "token_claude_por_vencer" not in await self._codigos(base, AHORA)
        assert "token_claude_por_vencer" in await self._codigos(base, AHORA + timedelta(days=340))
