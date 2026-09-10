"""El actualizador (D45, D46), sin red, sin uv y sin launchd.

Se importa el archivo suelto de `instalador/` y se le inyecta un `Entorno`
falso: un backend guionado, un tarball armado en `tmp_path`, un `correr` que
anota los comandos y contesta lo que el test diga, y una marca de vida que el
test escribe a mano como si fuera el agente.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[1] / "instalador" / "actualizar.py"
_spec = importlib.util.spec_from_file_location("actualizar", RUTA)
assert _spec and _spec.loader
act = importlib.util.module_from_spec(_spec)
#  Registrado antes de ejecutarlo: `dataclass` busca el módulo por nombre.
sys.modules["actualizar"] = act
_spec.loader.exec_module(act)

SHA_VIEJO = "4decc8c2a03c40cc3a277e852bda0ac048df4b2e"
SHA_NUEVO = "7912e13c5d3fa2b1c4d5e6f7a8b9c0d1e2f3a4b5"
T0 = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


class Mundo:
    """Todo lo que el actualizador toca, guionado."""

    def __init__(self, tmp_path: Path) -> None:
        self.casa = tmp_path / "casa"
        self.casa.mkdir()
        self.repo = tmp_path / "repo"
        self.reloj = T0
        self.comandos: list[list[str]] = []
        self.fallan: set[str] = set()  # nombres de comando que devuelven 1
        self.esperada: dict = {"sha": SHA_NUEVO, "origen": "rama", "repo": "x/y"}
        self.backend_caido = False
        self.tarball_roto = False
        self.lineas: list[str] = []
        #  Qué hace "el agente" cuando ve la VERSION nueva: por defecto vuelve.
        self.el_agente_vuelve = True
        self.entorno = act.Entorno(
            casa=self.casa,
            plataforma="darwin",
            fetch=self._fetch,
            correr=self._correr,
            dormir=self._dormir,
            ahora=lambda: self.reloj,
            log=self.lineas.append,
        )

    # -- el repo instalado -------------------------------------------------
    def instalar(self, sha: str | None = SHA_VIEJO, *, con_env: bool = True) -> None:
        (self.repo / "agente" / "agente").mkdir(parents=True)
        (self.repo / "agente" / "pyproject.toml").write_text("[project]\n", "utf-8")
        (self.repo / "agente" / "agente" / "main.py").write_text("viejo\n", "utf-8")
        (self.repo / "agente" / "viejo_que_se_borra.py").write_text("x\n", "utf-8")
        (self.repo / "agente" / ".venv").mkdir()
        (self.repo / "agente" / ".venv" / "python").write_text("venv\n", "utf-8")
        (self.repo / "agente" / "__pycache__").mkdir()
        (self.repo / "agente" / "__pycache__" / "x.pyc").write_text("cache\n", "utf-8")
        if con_env:
            (self.repo / ".env").write_text(
                "AGENTE_BACKEND_URL=https://backend.prueba\nAGENTE_TOKEN=sgc_prueba\n", "utf-8"
            )
        if sha:
            (self.repo / "agente" / "VERSION").write_text(f"{sha[:12]} 2026-09-01\n", "utf-8")

    def tarball(self, sha: str) -> bytes:
        """El árbol del commit `sha`, como lo manda GitHub."""
        buffer = io.BytesIO()
        raiz = f"repo-{sha}"
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for nombre, contenido in {
                f"{raiz}/agente/pyproject.toml": "[project]\n",
                f"{raiz}/agente/agente/main.py": f"nuevo {sha[:7]}\n",
                f"{raiz}/agente/agente/nuevo.py": "nuevo\n",
                f"{raiz}/agente/instalador/actualizar.py": "# el actualizador del commit nuevo\n",
                f"{raiz}/README.md": "hola\n",
            }.items():
                datos = contenido.encode()
                info = tarfile.TarInfo(nombre)
                info.size = len(datos)
                tar.addfile(info, io.BytesIO(datos))
        return buffer.getvalue()

    # -- el mundo de afuera -------------------------------------------------
    def _fetch(self, url: str, encabezados: dict, timeout: float) -> bytes:
        if "version-esperada" in url:
            if self.backend_caido:
                raise OSError("timeout")
            assert encabezados.get("Authorization") == "Bearer sgc_prueba"
            return json.dumps(self.esperada).encode()
        if "/archive/" in url:
            if self.tarball_roto:
                return b"esto no es un tar"
            sha = url.rsplit("/", 1)[1].removesuffix(".tar.gz")
            return self.tarball(sha)
        raise AssertionError(f"url inesperada: {url}")

    def _correr(self, comando: list[str], cwd: Path | None) -> int:
        self.comandos.append(comando)
        nombre = Path(comando[0]).name
        if "sync" in comando:
            return 1 if "uv" in self.fallan else 0
        if "--version" in comando:
            return 1 if "humo" in self.fallan else 0
        return 0 if nombre not in self.fallan else 1

    def _dormir(self, segundos: float) -> None:
        self.reloj += timedelta(seconds=segundos)
        #  Al dormir por primera vez ya se escribió la VERSION: "el agente" la
        #  ve, se reinicia y deja su marca con el sha nuevo — si vuelve.
        if self.el_agente_vuelve:
            self.marcar_vivo(act.sha_instalado(self.repo))

    # -- lo que hace el agente ---------------------------------------------
    def marcar_vivo(self, sha: str, *, hace_s: float = 0, ocupado: bool = False) -> None:
        carpeta = self.casa / ".centonara" / "estado"
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "vivo.json").write_text(
            json.dumps(
                {
                    "version": f"{sha[:12]} 2026-09-10",
                    "sha": sha[:12] if sha else None,
                    "pid": 1,
                    "ocupado": ocupado,
                    "cuando": (self.reloj - timedelta(seconds=hace_s)).isoformat(),
                }
            ),
            "utf-8",
        )

    def correr(self, **extra) -> int:
        return act.actualizar(self.entorno, self.repo, **extra)

    @property
    def log(self) -> str:
        return "\n".join(self.lineas)


@pytest.fixture
def mundo(tmp_path: Path) -> Mundo:
    return Mundo(tmp_path)


# ---------------------------------------------------------------------------
# Los caminos cortos: al día, sin respuesta, sin datos
# ---------------------------------------------------------------------------


def test_al_dia_no_hace_nada(mundo: Mundo) -> None:
    mundo.instalar(SHA_NUEVO)
    assert mundo.correr() == act.SALIDA_OK
    assert "al día" in mundo.log
    assert mundo.comandos == []
    assert (mundo.repo / "agente" / "viejo_que_se_borra.py").exists()


def test_el_abreviado_y_el_entero_son_el_mismo_commit(mundo: Mundo) -> None:
    mundo.instalar(SHA_NUEVO[:7])
    assert mundo.correr() == act.SALIDA_OK
    assert "al día" in mundo.log


def test_si_el_backend_no_contesta_no_se_toca_nada(mundo: Mundo) -> None:
    """Seguir con lo que hay es mejor que saltar a algo que nadie fijó."""
    mundo.instalar()
    mundo.backend_caido = True
    assert mundo.correr() == act.SALIDA_OK
    assert "no se toca nada" in mundo.log
    assert (mundo.repo / "agente" / "agente" / "main.py").read_text() == "viejo\n"


def test_si_el_backend_no_sabe_tampoco(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.esperada = {"sha": "", "origen": "desconocida"}
    assert mundo.correr() == act.SALIDA_OK
    assert "no se toca nada" in mundo.log


def test_sin_token_no_hay_a_quien_preguntar(mundo: Mundo) -> None:
    mundo.instalar(con_env=False)
    assert mundo.correr() == act.SALIDA_ERROR
    assert "AGENTE_TOKEN" in mundo.log


# ---------------------------------------------------------------------------
# La actualización entera
# ---------------------------------------------------------------------------


def test_actualiza_sincroniza_borra_lo_viejo_y_conserva_lo_de_la_maquina(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.marcar_vivo(SHA_VIEJO)  # el agente estaba vivo

    assert mundo.correr() == act.SALIDA_OK

    agente = mundo.repo / "agente"
    assert (agente / "agente" / "main.py").read_text() == f"nuevo {SHA_NUEVO[:7]}\n"
    assert (agente / "agente" / "nuevo.py").exists()
    assert not (agente / "viejo_que_se_borra.py").exists(), "lo que arriba no existe, abajo tampoco"
    #  Lo de esta máquina sobrevive:
    assert (mundo.repo / ".env").read_text().startswith("AGENTE_BACKEND_URL")
    assert (agente / ".venv" / "python").exists()
    assert (agente / "__pycache__" / "x.pyc").exists()
    #  VERSION quedó con el sha nuevo y la fecha:
    assert (agente / "VERSION").read_text() == f"{SHA_NUEVO[:12]} 2026-09-10\n"
    #  uv sync y la prueba de humo corrieron, en ese orden:
    assert [c[1] for c in mundo.comandos[:1]] == ["sync"]
    assert "--version" in mundo.comandos[1]
    assert "LISTO" in mundo.log


def test_se_copia_a_si_mismo_afuera_del_arbol(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.marcar_vivo(SHA_VIEJO)
    mundo.correr()
    copia = mundo.casa / ".centonara" / "bin" / "actualizar.py"
    assert copia.read_text() == "# el actualizador del commit nuevo\n"


def test_deja_un_respaldo_del_arbol_anterior(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.marcar_vivo(SHA_VIEJO)
    mundo.correr()
    respaldo = mundo.casa / ".centonara" / "respaldo" / SHA_VIEJO[:12]
    assert (respaldo / "agente" / "agente" / "main.py").read_text() == "viejo\n"
    assert not (respaldo / "agente" / ".venv").exists()


def test_sin_version_instalada_igual_actualiza(mundo: Mundo) -> None:
    """Una máquina instalada a mano, sin VERSION: la primera vuelta la pone al día."""
    mundo.instalar(sha=None)
    mundo.marcar_vivo("")
    assert mundo.correr() == act.SALIDA_OK
    assert act.sha_instalado(mundo.repo) == SHA_NUEVO[:12]


def test_el_sha_forzado_no_pregunta_al_backend(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.backend_caido = True
    mundo.marcar_vivo(SHA_VIEJO)
    assert mundo.correr(sha_forzado=SHA_NUEVO[:7].upper()) == act.SALIDA_OK
    assert act.mismo_sha(act.sha_instalado(mundo.repo), SHA_NUEVO)


def test_un_sha_forzado_invalido_no_hace_nada(mundo: Mundo) -> None:
    mundo.instalar()
    assert mundo.correr(sha_forzado="main") == act.SALIDA_ERROR


def test_si_el_agente_no_estaba_corriendo_no_espera_e_intenta_levantarlo(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.marcar_vivo(SHA_VIEJO, hace_s=3600)  # una marca vieja: no está corriendo
    mundo.el_agente_vuelve = False
    assert mundo.correr() == act.SALIDA_OK
    assert "no estaba corriendo" in mundo.log
    assert any(c[0] == "launchctl" and "kickstart" in c for c in mundo.comandos)


def test_en_windows_se_levanta_con_la_tarea_programada(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.entorno.plataforma = "win32"
    mundo.el_agente_vuelve = False
    mundo.correr()
    assert any(c[0] == "schtasks" and "/Run" in c for c in mundo.comandos)


# ---------------------------------------------------------------------------
# Deshacer: lo que hace que se pueda actualizar sin nadie mirando
# ---------------------------------------------------------------------------


def restaurado(mundo: Mundo) -> None:
    assert (mundo.repo / "agente" / "agente" / "main.py").read_text() == "viejo\n"
    assert (mundo.repo / "agente" / "viejo_que_se_borra.py").exists()
    assert not (mundo.repo / "agente" / "agente" / "nuevo.py").exists()
    assert act.sha_instalado(mundo.repo) == SHA_VIEJO[:12]
    assert (mundo.repo / ".env").exists()


def test_si_uv_sync_falla_se_deshace(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.marcar_vivo(SHA_VIEJO)
    mundo.fallan.add("uv")
    assert mundo.correr() == act.SALIDA_DESHECHO
    assert "DESHACIENDO: uv sync" in mundo.log
    restaurado(mundo)


def test_si_el_agente_nuevo_no_importa_se_deshace(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.marcar_vivo(SHA_VIEJO)
    mundo.fallan.add("humo")
    assert mundo.correr() == act.SALIDA_DESHECHO
    assert "no arranca" in mundo.log
    restaurado(mundo)


def test_si_el_agente_no_vuelve_se_deshace(mundo: Mundo) -> None:
    """Estaba vivo, se le dejó la versión nueva, y no volvió a dar señales con ella."""
    mundo.instalar()
    mundo.marcar_vivo(SHA_VIEJO)
    mundo.el_agente_vuelve = False
    assert mundo.correr() == act.SALIDA_DESHECHO
    assert "no volvió" in mundo.log
    restaurado(mundo)
    #  Y no esperó para siempre: el techo de la espera se respeta.
    assert (mundo.reloj - T0).total_seconds() <= act.ESPERA_VUELTA_S + 10


def test_un_agente_ocupado_en_una_tanda_no_se_da_por_muerto(mundo: Mundo) -> None:
    """Una tanda dura hasta 35 min: mientras la marca diga ocupado, se espera."""
    mundo.instalar()
    mundo.marcar_vivo(SHA_VIEJO, ocupado=True)
    mundo.el_agente_vuelve = False
    dormidas = {"n": 0}

    def dormir(segundos: float) -> None:
        mundo.reloj += timedelta(seconds=segundos)
        dormidas["n"] += 1
        #  Sigue ocupado 20 minutos (más que ESPERA_VUELTA_S); después vuelve.
        if (mundo.reloj - T0).total_seconds() < 20 * 60:
            mundo.marcar_vivo(SHA_VIEJO, ocupado=True)
        else:
            mundo.marcar_vivo(act.sha_instalado(mundo.repo))

    mundo.entorno.dormir = dormir
    assert mundo.correr() == act.SALIDA_OK
    assert "volvió" in mundo.log
    assert (mundo.reloj - T0).total_seconds() >= 20 * 60


def test_sin_verificar_no_espera(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.marcar_vivo(SHA_VIEJO)
    mundo.el_agente_vuelve = False
    assert mundo.correr(verificar=False) == act.SALIDA_OK
    assert act.sha_instalado(mundo.repo) == SHA_NUEVO[:12]


def test_un_tarball_roto_no_toca_nada(mundo: Mundo) -> None:
    mundo.instalar()
    mundo.tarball_roto = True
    assert mundo.correr() == act.SALIDA_ERROR
    assert "no se pudo bajar" in mundo.log
    assert (mundo.repo / "agente" / "agente" / "main.py").read_text() == "viejo\n"
    assert act.sha_instalado(mundo.repo) == SHA_VIEJO[:12]


# ---------------------------------------------------------------------------
# Piezas sueltas
# ---------------------------------------------------------------------------


def test_leer_env_ignora_comentarios_y_comillas(tmp_path: Path) -> None:
    archivo = tmp_path / ".env"
    archivo.write_text(
        "# comentario\nAGENTE_TOKEN='sgc_x'\nAGENTE_BACKEND_URL=\"https://b\"\nSIN_IGUAL\n\n",
        "utf-8",
    )
    assert act.leer_env(archivo) == {"AGENTE_TOKEN": "sgc_x", "AGENTE_BACKEND_URL": "https://b"}
    assert act.leer_env(tmp_path / "no-existe") == {}


def test_el_tarball_no_puede_escapar_de_su_carpeta(mundo: Mundo, tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("repo-x/../../fuera.txt")
        info.size = 0
        tar.addfile(info, io.BytesIO(b""))
    mundo.entorno.fetch = lambda url, enc, t: buffer.getvalue()
    with pytest.raises(ValueError):
        act.bajar_arbol(mundo.entorno, "x/y", SHA_NUEVO, tmp_path / "destino")


def test_el_candado_evita_dos_corridas_a_la_vez(mundo: Mundo) -> None:
    candado = mundo.casa / ".centonara" / "actualizador.lock"
    candado.parent.mkdir(parents=True)
    candado.write_text("123")
    llamadas: list[int] = []
    assert (
        act.con_candado(mundo.entorno, mundo.repo, lambda: llamadas.append(1) or 0) == act.SALIDA_OK
    )
    assert llamadas == []
    assert "ya hay un actualizador" in mundo.log


def test_el_candado_se_suelta_al_terminar(mundo: Mundo) -> None:
    candado = mundo.casa / ".centonara" / "actualizador.lock"
    assert act.con_candado(mundo.entorno, mundo.repo, lambda: 7) == 7
    assert not candado.exists()


def test_en_windows_sin_tarea_programada_se_lanza_el_agente_directo(mundo: Mundo) -> None:
    """Una PC instalada a mano no tiene la tarea: el agente se levanta igual."""
    mundo.instalar()
    mundo.entorno.plataforma = "win32"
    mundo.el_agente_vuelve = False
    mundo.fallan.add("schtasks")
    lanzados: list[tuple] = []
    mundo.entorno.lanzar = lambda comando, cwd, log: lanzados.append((comando, cwd, log))

    assert mundo.correr() == act.SALIDA_OK

    assert len(lanzados) == 1
    comando, cwd, log = lanzados[0]
    assert comando[1:] == ["-m", "agente.main"]
    assert cwd == mundo.repo / "agente"
    assert log.name == "agente.log"
