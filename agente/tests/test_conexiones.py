"""Las sesiones de la máquina y sus reconexiones (D69, D70, D73).

Lo que fija esto:

- qué dice cada job y cada sonda de cada sesión;
- que una acción del latido se ejecuta una vez, y se reporta hasta que llega;
- que la apertura automática del QR y las verificaciones tienen tope;
- que nada que gaste una llamada corre con un job en curso o de noche;
- que el token del panel se usa al instante y queda en el `.env`, sin
  imprimirse;
- que un backend viejo no deja a la máquina sin latido ni sin reporte.

Nada abre un navegador ni lanza un proceso: el reloj, Chrome, la sonda y los
avisos se inyectan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from agente import notificar, reconexion, sesiones, token_claude
from agente.adaptadores import navegador
from agente.cliente import Cliente

TOKEN = "sk-ant-oat01-" + "y" * 60


class Reloj:
    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora

    def pasar(self, minutos: float) -> None:
        self.ahora += minutos * 60


@dataclass
class Sonda:
    ok: bool
    motivo: str = ""
    detalle: str = ""


class Maquina:
    """Chrome, la sonda y los avisos, de mentira."""

    def __init__(self, *, sonda: Sonda | None = None) -> None:
        self.urls: list[str] = []
        self.avisos: list[tuple[str, str]] = []
        self.sondas = 0
        self.ocupada = False
        self.de_noche = False
        self.sonda = sonda or Sonda(True)

    def abrir_url(self, url: str):
        self.urls.append(url)
        return navegador.Resultado(navegador.Estado.ABIERTO)

    async def verificar(self):
        self.sondas += 1
        return self.sonda

    def avisar(self, titulo: str, texto: str) -> None:
        self.avisos.append((titulo, texto))


def armar(maquina: Maquina | None = None, **extra):
    maquina = maquina or Maquina()
    reloj = Reloj()
    estado = sesiones.Sesiones(reloj=reloj)
    rec = reconexion.Reconexion(
        estado,
        abrir_url=maquina.abrir_url,
        verificar=maquina.verificar,
        avisar=maquina.avisar,
        ocupado=lambda: maquina.ocupada,
        descansando=lambda: maquina.de_noche,
        reloj=reloj,
        **extra,
    )
    return rec, estado, maquina, reloj


# ---------------------------------------------------------------------------
# Lo que dicen los jobs y la sonda
# ---------------------------------------------------------------------------


class TestSesiones:
    def test_una_tanda_que_anda_confirma_las_tres(self):
        estado = sesiones.Sesiones()
        estado.resultado_de_job("BORRADORES", {"ok": True})
        assert estado.a_dict()["whatsapp"]["estado"] == "ok"
        assert estado.a_dict()["claude_extension"]["fuente"] == "job"
        assert estado.estado("claude_cli") == "ok"

    def test_el_qr_es_whatsapp_caido_con_la_extension_viva(self):
        estado = sesiones.Sesiones()
        estado.resultado_de_job(
            "BORRADORES", {"ok": False, "codigo": "SESION_CAIDA", "detalle": {"motivo": "QR"}}
        )
        assert estado.estado("whatsapp") == "caida"
        assert estado.estado("claude_extension") == "ok"

    def test_sin_navegador_es_la_extension(self):
        estado = sesiones.Sesiones()
        estado.resultado_de_job("LISTAR", {"ok": False, "codigo": "NAVEGADOR_AUSENTE"})
        assert estado.estado("claude_extension") == "caida"
        assert estado.estado("whatsapp") == "desconocido"

    def test_el_401_es_claude_code(self):
        estado = sesiones.Sesiones()
        estado.resultado_de_job("REDACTAR", {"ok": False, "codigo": "CLAUDE_SIN_SESION"})
        assert estado.estado("claude_cli") == "caida"

    def test_sin_cuota_no_dice_nada(self):
        estado = sesiones.Sesiones()
        estado.resultado_de_job("BORRADORES", {"ok": False, "codigo": "LIMITE_USO"})
        assert estado.a_dict() == {}

    def test_el_envio_habla_del_motor(self):
        estado = sesiones.Sesiones()
        estado.resultado_de_job("ENVIAR", {"ok": False, "codigo": "SESION_CAIDA"})
        assert estado.estado("whatsapp_motor") == "caida"
        assert estado.estado("whatsapp") == "desconocido"

    def test_la_sonda(self):
        estado = sesiones.Sesiones()
        estado.resultado_de_sonda(Sonda(False, "sesion_no_iniciada"))
        assert estado.estado("whatsapp") == "caida"
        assert estado.estado("claude_extension") == "ok"
        estado.resultado_de_sonda(Sonda(True))
        assert {n: o["estado"] for n, o in estado.a_dict().items()} == {
            "whatsapp": "ok",
            "claude_extension": "ok",
            "claude_cli": "ok",
        }

    def test_avisa_la_caida_una_sola_vez(self):
        estado = sesiones.Sesiones()
        caidas = []
        estado.al_caer(lambda nombre, fuente: caidas.append((nombre, fuente)))
        estado.observar("whatsapp", "caida", "job")
        estado.observar("whatsapp", "caida", "sonda")
        assert caidas == [("whatsapp", "job")]


# ---------------------------------------------------------------------------
# Las reconexiones
# ---------------------------------------------------------------------------


class TestAcciones:
    async def test_abrir_whatsapp_abre_avisa_y_se_reporta(self):
        rec, _, maquina, _ = armar()
        rec.recibir([{"id": "a1", "tipo": "abrir_whatsapp"}])
        rec.recibir([{"id": "a1", "tipo": "abrir_whatsapp"}])  # el latido la repite
        await rec.una_vuelta()
        await rec.una_vuelta()
        assert maquina.urls == [reconexion.URL_WHATSAPP]
        assert maquina.avisos[0][0] == "Volvé a conectar WhatsApp"
        assert rec.hechas() == [{"id": "a1", "resultado": "abierto: chrome"}]
        #  Ya hecha: si el backend la vuelve a mandar, no se repite.
        rec.recibir([{"id": "a1", "tipo": "abrir_whatsapp"}])
        await rec.una_vuelta()
        assert len(maquina.urls) == 1

    async def test_abrir_claude_dice_el_mail_solo_en_la_maquina(self):
        rec, _, maquina, _ = armar()
        rec.recibir([{"id": "c1", "tipo": "abrir_claude", "datos": {"mail": "cuenta@x.com"}}])
        await rec.una_vuelta()
        assert maquina.urls == [reconexion.URL_CLAUDE]
        assert "cuenta@x.com" in maquina.avisos[0][1]
        assert "cuenta@x.com" not in json.dumps(rec.hechas())

    async def test_verificar_espera_a_que_termine_el_job(self):
        rec, estado, maquina, _ = armar(Maquina(sonda=Sonda(False, "sesion_no_iniciada")))
        maquina.ocupada = True
        rec.recibir([{"id": "v1", "tipo": "verificar"}])
        await rec.una_vuelta()
        assert maquina.sondas == 0
        maquina.ocupada = False
        await rec.una_vuelta()
        assert maquina.sondas == 1
        assert estado.estado("whatsapp") == "caida"
        assert rec.hechas() == [{"id": "v1", "resultado": "falla: sesion_no_iniciada"}]

    async def test_las_hechas_se_olvidan_a_los_quince_minutos(self):
        rec, _, _, reloj = armar()
        rec.recibir([{"id": "a1", "tipo": "abrir_claude"}])
        await rec.una_vuelta()
        reloj.pasar(16)
        assert rec.hechas() == []

    async def test_despues_de_abrir_verifica_solo_hasta_que_anda(self):
        rec, estado, maquina, reloj = armar()
        rec.recibir([{"id": "a1", "tipo": "abrir_whatsapp"}])
        await rec.una_vuelta()
        reloj.pasar(2)
        await rec.una_vuelta()
        assert maquina.sondas == 1
        assert estado.estado("whatsapp") == "ok"
        #  Ya anda: la segunda verificación programada no gasta otra llamada.
        reloj.pasar(4)
        await rec.una_vuelta()
        assert maquina.sondas == 1


class TestAutomatico:
    async def test_whatsapp_caido_abre_el_qr_una_vez_cada_dos_horas(self):
        rec, estado, maquina, reloj = armar()
        estado.observar("whatsapp", "caida", "job")
        await rec.una_vuelta()
        assert maquina.urls == [reconexion.URL_WHATSAPP]

        estado.observar("whatsapp", "ok", "job")
        reloj.pasar(30)
        estado.observar("whatsapp", "caida", "job")
        await rec.una_vuelta()
        assert len(maquina.urls) == 1  # dentro de las dos horas, no

    async def test_de_noche_no_abre_nada(self):
        maquina = Maquina()
        maquina.de_noche = True
        rec, estado, maquina, _ = armar(maquina)
        estado.observar("whatsapp", "caida", "job")
        await rec.una_vuelta()
        assert maquina.urls == []

    async def test_la_revision_diaria_y_su_tope(self):
        rec, _, maquina, reloj = armar()
        await rec.una_vuelta()
        assert maquina.sondas == 0  # recién arrancó
        reloj.pasar(reconexion.MINUTOS_PRIMERA_REVISION)
        await rec.una_vuelta()
        assert maquina.sondas == 1
        reloj.pasar(60)
        await rec.una_vuelta()
        assert maquina.sondas == 1  # una por día

    async def test_si_un_job_ya_confirmo_no_hace_falta(self):
        rec, estado, maquina, reloj = armar()
        reloj.pasar(reconexion.MINUTOS_PRIMERA_REVISION)
        estado.resultado_de_job("BORRADORES", {"ok": True})
        await rec.una_vuelta()
        assert maquina.sondas == 0

    async def test_nunca_con_un_job_en_curso(self):
        rec, _, maquina, reloj = armar()
        maquina.ocupada = True
        reloj.pasar(reconexion.MINUTOS_PRIMERA_REVISION + 1)
        await rec.una_vuelta()
        assert maquina.sondas == 0

    async def test_una_caida_de_un_job_se_reverifica_despues(self):
        rec, estado, maquina, reloj = armar()
        reloj.pasar(reconexion.MINUTOS_PRIMERA_REVISION)
        await rec.una_vuelta()  # la revisión diaria
        maquina.sonda = Sonda(True)
        estado.observar("claude_extension", "caida", "job")
        reloj.pasar(reconexion.MINUTOS_ANTES_DE_REVERIFICAR)
        await rec.una_vuelta()
        assert maquina.sondas == 2
        assert estado.estado("claude_extension") == "ok"


# ---------------------------------------------------------------------------
# El token del panel
# ---------------------------------------------------------------------------


class TestToken:
    @pytest.fixture(autouse=True)
    def limpio(self):
        token_claude.olvidar()
        yield
        token_claude.olvidar()

    def test_se_usa_al_instante_y_queda_en_el_env(self, tmp_path: Path, capsys):
        env = tmp_path / ".env"
        env.write_text("AGENTE_TOKEN=sgc_x\nCLAUDE_CODE_OAUTH_TOKEN=viejo\n", encoding="utf-8")

        assert token_claude.aplicar(TOKEN, archivo=env)
        assert token_claude.vigente() == TOKEN
        assert token_claude.reportado() == token_claude.hash_corto(TOKEN)
        lineas = env.read_text(encoding="utf-8").splitlines()
        assert lineas == ["AGENTE_TOKEN=sgc_x", f"CLAUDE_CODE_OAUTH_TOKEN={TOKEN}"]
        assert TOKEN not in capsys.readouterr().out

    def test_lo_que_no_parece_un_token_no_se_toma(self, tmp_path: Path):
        env = tmp_path / ".env"
        assert not token_claude.aplicar("cualquier cosa", archivo=env)
        assert not env.exists()
        assert token_claude.reportado() == ""

    def test_el_hash_coincide_con_el_del_backend(self):
        #  `app.core.conexiones.hash_corto` hace exactamente esto.
        import hashlib

        assert token_claude.hash_corto(TOKEN) == hashlib.sha256(TOKEN.encode()).hexdigest()[:16]

    def test_claude_code_recibe_el_token_nuevo(self):
        from agente.jobs import claude_code

        token_claude._recibido = TOKEN
        assert claude_code._entorno_de_claude()["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN


# ---------------------------------------------------------------------------
# Con un backend que todavía no se actualizó
# ---------------------------------------------------------------------------


def con_backend(responder) -> tuple[Cliente, list[dict]]:
    recibidos: list[dict] = []

    def manejar(pedido: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(pedido.content)
        recibidos.append(cuerpo)
        return responder(cuerpo)

    cliente = Cliente("http://backend", "token")
    cliente._http = httpx.AsyncClient(
        base_url="http://backend", transport=httpx.MockTransport(manejar)
    )
    return cliente, recibidos


class TestBackendViejo:
    async def test_el_latido_sigue_sin_las_sesiones(self):
        def viejo(cuerpo: dict) -> httpx.Response:
            return httpx.Response(422 if "sesiones" in cuerpo else 200, json={"ok": True})

        cliente, recibidos = con_backend(viejo)
        conexiones = {"sesiones": {}, "claude_token_hash": "", "acciones_hechas": []}
        assert (await cliente.latido({}, conexiones=conexiones))["ok"]
        assert (await cliente.latido({}, conexiones=conexiones))["ok"]
        #  Al primer 422 deja de mandarlas: tres pedidos, no cuatro.
        assert len(recibidos) == 3
        assert "sesiones" not in recibidos[-1]

    async def test_el_codigo_nuevo_sale_como_el_de_antes(self):
        def viejo(cuerpo: dict) -> httpx.Response:
            if cuerpo["codigo"] == "CLAUDE_SIN_SESION":
                return httpx.Response(422, json={"detail": "codigo"})
            return httpx.Response(200, json={"ok": True})

        cliente, recibidos = con_backend(viejo)
        await cliente.reportar("j1", ok=False, codigo="CLAUDE_SIN_SESION", detalle={"motivo": "x"})
        assert recibidos[-1]["codigo"] == "ERROR_INESPERADO"
        assert recibidos[-1]["detalle"] == {"motivo": "x", "codigo_nuevo": "CLAUDE_SIN_SESION"}


# ---------------------------------------------------------------------------
# Lo que toca la máquina, con el sistema operativo de mentira
# ---------------------------------------------------------------------------


class TestSistema:
    def test_abrir_url_usa_el_perfil_y_no_abre_puertos(self, tmp_path: Path):
        chrome = tmp_path / "chrome.exe"
        chrome.write_text("")
        lanzados = []
        resultado = navegador.abrir_url(
            reconexion.URL_WHATSAPP,
            chrome_bin=str(chrome),
            perfil_dir="Profile 9",
            lanzar=lanzados.append,
            plataforma="linux",
        )
        assert resultado.utilizable
        assert lanzados == [[str(chrome), "--profile-directory=Profile 9", reconexion.URL_WHATSAPP]]

    def test_sin_chrome_no_se_puede(self, tmp_path: Path):
        resultado = navegador.abrir_url(
            reconexion.URL_CLAUDE, chrome_bin=str(tmp_path / "no-esta"), lanzar=lambda c: None
        )
        assert not resultado.utilizable

    def test_el_aviso_va_por_variables_y_no_armado_en_el_comando(self):
        corridas = []
        notificar.avisar(
            'Ti"tulo',
            "texto; rm -rf",
            plataforma="win32",
            correr=lambda c, e=None: corridas.append((c, e)),
        )
        comando, entorno = corridas[0]
        assert "texto; rm -rf" not in " ".join(comando)
        assert entorno == {"CENTONARA_TITULO": 'Ti"tulo', "CENTONARA_TEXTO": "texto; rm -rf"}

    def test_en_mac_va_como_argumentos(self):
        corridas = []
        notificar.avisar("T", "x", plataforma="darwin", correr=lambda c, e=None: corridas.append(c))
        assert corridas[0][0] == "osascript"
        assert corridas[0][-2:] == ["T", "x"]

    def test_un_aviso_que_falla_no_lanza(self):
        def revienta(c, e=None):
            raise OSError("sin powershell")

        assert notificar.avisar("T", "x", plataforma="win32", correr=revienta) is False
