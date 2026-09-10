#!/usr/bin/env python3
"""El actualizador del agente (D45, D46). Corre solo; no pregunta nada.

Un solo archivo, sólo biblioteca estándar, para que ande con cualquier Python
3 y no dependa del entorno que está por reemplazar. Lo corre el sistema al
iniciar sesión y cada hora (`com.centonara.actualizador` en Mac, la tarea
programada en Windows), y también una persona con `actualizar.sh` / `.ps1`.

Seis pasos, cada uno con su salida temprana:

  1. Preguntar al backend qué commit toca (`GET /api/agente/version-esperada`).
     Sin respuesta → no se toca nada: seguir con lo instalado es mejor que
     saltar a algo que nadie fijó.
  2. Comparar con `agente/VERSION`. Igual → salir. Es el camino de todos los días.
  3. Bajar ESE sha de GitHub (un commit exacto, no una rama).
  4. Respaldar el árbol y sincronizar el nuevo encima, borrando lo que arriba
     ya no existe. `.env`, `.venv`, `.git` y `node_modules` no se tocan.
  5. `uv sync`, una prueba de humo (`python -m agente.main --version`) y
     escribir `agente/VERSION`. El agente ve el cambio entre dos jobs y se
     reinicia solo (`agente/reinicio.py`).
  6. Esperar a que vuelva con el sha nuevo. Si estaba vivo y no vuelve, se
     restaura el respaldo: una máquina en la casa de un vendedor no puede
     quedar rota esperando a que alguien la mire.

Vive en `~/.centonara/bin/` —fuera del árbol que reemplaza— y se copia a sí
mismo ahí después de cada actualización buena. Un script no puede pisarse
mientras corre; una copia sí.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Lo que nunca se sincroniza ni se respalda: es de esta máquina, no del commit.
EXCLUIDOS = frozenset(
    {
        ".env",
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
    }
)
ARCHIVO_VERSION = Path("agente") / "VERSION"
ETIQUETA_AGENTE_MAC = "com.centonara.agente"
TAREA_AGENTE_WINDOWS = "Centonara Agente"

# Una marca de vida más vieja que esto es un agente que no está corriendo.
# El agente la refresca en cada latido (30 s); cuatro latidos de margen.
SEGUNDOS_VIVO = 120
# Cuánto se espera a que el agente vuelva con el sha nuevo, contando desde
# que quedó libre: el bucle mira el disco cada 10 s, en Windows la tarea lo
# relanza al minuto, y arrancar y registrarse lleva unos segundos más.
ESPERA_VUELTA_S = 180
# Techo absoluto de la espera, por si el agente está en el medio de una
# tanda: una dura hasta 35 min. Pasado esto se da por no vuelto.
ESPERA_MAXIMA_S = 50 * 60
TIMEOUT_BACKEND_S = 120  # Render dormido tarda un minuto en despertar
TIMEOUT_GITHUB_S = 300
RESPALDOS_QUE_SE_GUARDAN = 2

SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_DESHECHO = 2


# ---------------------------------------------------------------------------
# El entorno: todo lo que toca el mundo, en un solo lugar, reemplazable
# ---------------------------------------------------------------------------


@dataclass
class Entorno:
    casa: Path
    plataforma: str
    fetch: Callable[[str, dict[str, str], float], bytes]
    correr: Callable[[list[str], Path | None], int]
    dormir: Callable[[float], None]
    ahora: Callable[[], datetime]
    log: Callable[[str], None]
    #  Lanzar un proceso que sobreviva a éste (Windows sin tarea). `None` = el real.
    lanzar: Callable[[list[str], Path, Path], None] | None = None


def _fetch_real(url: str, encabezados: dict[str, str], timeout: float) -> bytes:
    pedido = urllib.request.Request(
        url, headers={"User-Agent": "centonara-actualizador", **encabezados}
    )
    with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
        return respuesta.read()


def _correr_real(log: Callable[[str], None]) -> Callable[[list[str], Path | None], int]:
    def correr(comando: list[str], cwd: Path | None) -> int:
        try:
            hecho = subprocess.run(
                comando, cwd=cwd, capture_output=True, text=True, timeout=20 * 60, check=False
            )
        except (OSError, subprocess.SubprocessError) as error:
            log(f"    no se pudo correr {comando[0]}: {error}")
            return 127
        salida = (hecho.stdout + hecho.stderr).strip().splitlines()
        for linea in salida[-8:]:
            log(f"    | {linea[:200]}")
        return hecho.returncode

    return correr


def carpeta_logs(casa: Path, plataforma: str) -> Path:
    if plataforma == "darwin":
        return casa / "Library" / "Logs" / "centonara"
    if plataforma == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else casa) / "Centonara" / "logs"
    return casa / ".centonara" / "logs"


def _log_real(casa: Path, plataforma: str) -> Callable[[str], None]:
    carpeta = carpeta_logs(casa, plataforma)
    archivo = carpeta / "actualizador.log"
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        #  Que no crezca para siempre: pasado el mega, se queda la última mitad.
        if archivo.exists() and archivo.stat().st_size > 1_000_000:
            cola = archivo.read_bytes()[-500_000:]
            archivo.write_bytes(cola)
    except OSError:
        pass

    def log(mensaje: str) -> None:
        linea = f"{datetime.now(UTC).isoformat(timespec='seconds')} {mensaje}"
        print(linea, flush=True)
        try:
            with archivo.open("a", encoding="utf-8") as f:
                f.write(linea + "\n")
        except OSError:
            pass

    return log


def entorno_real() -> Entorno:
    casa = Path.home()
    log = _log_real(casa, sys.platform)
    return Entorno(
        casa=casa,
        plataforma=sys.platform,
        fetch=_fetch_real,
        correr=_correr_real(log),
        dormir=time.sleep,
        ahora=lambda: datetime.now(UTC),
        log=log,
    )


# ---------------------------------------------------------------------------
# Piezas
# ---------------------------------------------------------------------------


def leer_env(archivo: Path) -> dict[str, str]:
    """`CLAVE=valor` por línea, sin comentarios. Lo justo para el `.env` del agente."""
    valores: dict[str, str] = {}
    try:
        #  `utf-8-sig`: un .env escrito desde PowerShell puede traer BOM.
        lineas = archivo.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return valores
    for linea in lineas:
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valor = valor.strip()
        if valor[:1] in {'"', "'"} and valor[-1:] == valor[:1]:
            valor = valor[1:-1]
        valores[clave.strip()] = valor
    return valores


def normalizar_sha(valor: object) -> str:
    texto = str(valor or "").strip().lower()
    if 7 <= len(texto) <= 40 and all(c in "0123456789abcdef" for c in texto):
        return texto
    return ""


def mismo_sha(a: str, b: str) -> bool:
    """El abreviado y el entero del mismo commit son el mismo commit."""
    a, b = a.lower(), b.lower()
    largo = min(len(a), len(b))
    return largo >= 7 and a[:largo] == b[:largo]


def sha_instalado(repo: Path) -> str:
    """El sha de `agente/VERSION`, o vacío."""
    try:
        primera = (repo / ARCHIVO_VERSION).read_text(encoding="utf-8").strip().splitlines()[0]
    except (OSError, IndexError):
        return ""
    return normalizar_sha(primera.split()[0] if primera.split() else "")


def escribir_version(repo: Path, sha: str, ahora: datetime) -> None:
    (repo / ARCHIVO_VERSION).write_text(f"{sha[:12]} {ahora:%Y-%m-%d}\n", encoding="utf-8")


def pedir_esperada(entorno: Entorno, backend: str, token: str) -> dict:
    """Lo que dice el backend, o `{}` si no contesta. Nunca levanta."""
    url = backend.rstrip("/") + "/api/agente/version-esperada"
    try:
        crudo = entorno.fetch(url, {"Authorization": f"Bearer {token}"}, TIMEOUT_BACKEND_S)
        datos = json.loads(crudo.decode("utf-8"))
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError, urllib.error.URLError) as error:
        entorno.log(f"  el backend no contestó: {str(error)[:200]}")
        return {}


def bajar_arbol(entorno: Entorno, repo_github: str, sha: str, destino: Path) -> Path:
    """Baja `archive/<sha>.tar.gz` y lo extrae. Devuelve la raíz del árbol nuevo."""
    url = f"https://github.com/{repo_github}/archive/{sha}.tar.gz"
    entorno.log(f"  bajando {url}")
    crudo = entorno.fetch(url, {}, TIMEOUT_GITHUB_S)
    destino.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(crudo), mode="r:gz") as tar:
        miembros = tar.getmembers()
        raices = {
            m.name.split("/", 1)[0] for m in miembros if m.name and not m.name.startswith("/")
        }
        if len(raices) != 1:
            raise ValueError(f"el tarball no tiene una sola raíz: {sorted(raices)[:3]}")
        for miembro in miembros:
            #  Sin `..` ni rutas absolutas: un tarball es de afuera aunque venga de GitHub.
            if ".." in Path(miembro.name).parts or miembro.name.startswith("/"):
                raise ValueError(f"ruta sospechosa en el tarball: {miembro.name}")
        tar.extractall(destino, filter="data")
    raiz = destino / next(iter(raices))
    if not (raiz / "agente" / "pyproject.toml").exists():
        raise ValueError("el árbol bajado no tiene agente/pyproject.toml")
    return raiz


def _excluido(nombre: str) -> bool:
    return nombre in EXCLUIDOS


def sincronizar(origen: Path, destino: Path) -> tuple[int, int]:
    """Deja `destino` igual a `origen`, salvo lo excluido. Devuelve (copiados, borrados).

    Es el `rsync --delete` en Python: lo que arriba se borró o renombró
    desaparece abajo. Es la diferencia con extraer un tarball encima del árbol,
    que dejaba archivos fantasma para siempre.
    """
    copiados = borrados = 0
    destino.mkdir(parents=True, exist_ok=True)

    for raiz, carpetas, archivos in os.walk(origen):
        carpetas[:] = [c for c in carpetas if not _excluido(c)]
        relativa = Path(raiz).relative_to(origen)
        (destino / relativa).mkdir(parents=True, exist_ok=True)
        for nombre in archivos:
            if _excluido(nombre):
                continue
            de = Path(raiz) / nombre
            a = destino / relativa / nombre
            if a.is_dir():
                shutil.rmtree(a)
            try:
                igual = (
                    a.exists()
                    and a.stat().st_size == de.stat().st_size
                    and a.read_bytes() == de.read_bytes()
                )
            except OSError:
                igual = False
            if not igual:
                shutil.copy2(de, a)
                copiados += 1

    for raiz, carpetas, archivos in os.walk(destino, topdown=True):
        carpetas[:] = [c for c in carpetas if not _excluido(c)]
        relativa = Path(raiz).relative_to(destino)
        for nombre in archivos:
            if _excluido(nombre) or (origen / relativa / nombre).exists():
                continue
            (Path(raiz) / nombre).unlink()
            borrados += 1
        for carpeta in list(carpetas):
            if not (origen / relativa / carpeta).exists():
                shutil.rmtree(Path(raiz) / carpeta)
                carpetas.remove(carpeta)
                borrados += 1
    return copiados, borrados


def respaldar(repo: Path, carpeta_respaldos: Path, etiqueta: str) -> Path:
    """Copia el árbol (sin lo excluido) a `carpeta_respaldos/<etiqueta>`."""
    destino = carpeta_respaldos / (etiqueta or "sin-version")
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(repo, destino, ignore=shutil.ignore_patterns(*EXCLUIDOS))
    #  Se guardan los últimos: el de antes y el de antes de ése.
    viejos = sorted(carpeta_respaldos.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for sobrante in viejos[RESPALDOS_QUE_SE_GUARDAN:]:
        shutil.rmtree(sobrante, ignore_errors=True)
    return destino


def encontrar_uv(entorno: Entorno) -> str | None:
    encontrado = shutil.which("uv")
    if encontrado:
        return encontrado
    candidatos = [
        entorno.casa / ".local" / "bin" / "uv",
        entorno.casa / ".local" / "bin" / "uv.exe",
        Path("/opt/homebrew/bin/uv"),
        Path("/usr/local/bin/uv"),
    ]
    return next((str(c) for c in candidatos if c.exists()), None)


def python_del_agente(repo: Path, plataforma: str) -> Path:
    if plataforma == "win32":
        return repo / "agente" / ".venv" / "Scripts" / "python.exe"
    return repo / "agente" / ".venv" / "bin" / "python"


def uv_sync(entorno: Entorno, repo: Path) -> bool:
    uv = encontrar_uv(entorno)
    if uv is None:
        entorno.log("  no se encontró uv")
        return False
    entorno.log("  uv sync")
    return entorno.correr([uv, "sync", "--directory", str(repo / "agente")], repo) == 0


def prueba_de_humo(entorno: Entorno, repo: Path) -> bool:
    """`python -m agente.main --version`: si el paquete no importa, no se instala."""
    python = python_del_agente(repo, entorno.plataforma)
    entorno.log("  prueba de humo: agente.main --version")
    return entorno.correr([str(python), "-m", "agente.main", "--version"], repo / "agente") == 0


def leer_vivo(entorno: Entorno) -> dict | None:
    archivo = entorno.casa / ".centonara" / "estado" / "vivo.json"
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else None
    except (OSError, ValueError):
        return None


def _edad_s(entorno: Entorno, marca: dict | None) -> float | None:
    if not marca or not marca.get("cuando"):
        return None
    try:
        cuando = datetime.fromisoformat(str(marca["cuando"]))
    except ValueError:
        return None
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=UTC)
    return (entorno.ahora() - cuando).total_seconds()


def agente_vivo(entorno: Entorno) -> bool:
    edad = _edad_s(entorno, leer_vivo(entorno))
    return edad is not None and edad < SEGUNDOS_VIVO


def esperar_vuelta(entorno: Entorno, sha: str) -> bool:
    """¿El agente volvió a levantarse con `sha`? Espera, con paciencia si está ocupado."""
    inicio = entorno.ahora()
    libre_desde = inicio
    while True:
        marca = leer_vivo(entorno)
        if marca and mismo_sha(str(marca.get("sha") or ""), sha):
            return True
        transcurrido = (entorno.ahora() - inicio).total_seconds()
        if transcurrido > ESPERA_MAXIMA_S:
            return False
        edad = _edad_s(entorno, marca)
        ocupado = bool(marca and marca.get("ocupado")) and edad is not None and edad < SEGUNDOS_VIVO
        if ocupado:
            #  En el medio de un job: el reloj de los 180 s arranca cuando termine.
            libre_desde = entorno.ahora()
        elif (entorno.ahora() - libre_desde).total_seconds() > ESPERA_VUELTA_S:
            return False
        entorno.dormir(5)


def _lanzar_desacoplado(comando: list[str], cwd: Path, log_archivo: Path) -> None:
    """Un proceso que sobrevive a este: para levantar el agente en una PC sin tarea."""
    log_archivo.parent.mkdir(parents=True, exist_ok=True)
    salida = log_archivo.open("ab")
    banderas = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    subprocess.Popen(
        comando,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=salida,
        stderr=salida,
        creationflags=banderas,
        close_fds=False,
    )


def arrancar_agente(entorno: Entorno, repo: Path) -> None:
    """Si el agente no estaba corriendo, se intenta levantarlo. Sin drama si no se puede.

    En Windows, primero la tarea programada; si no existe —una PC instalada a
    mano— se lanza el agente directo, desacoplado, con la salida en el log.
    """
    if entorno.plataforma == "darwin":
        uid = os.getuid() if hasattr(os, "getuid") else 501
        entorno.correr(["launchctl", "kickstart", "-k", f"gui/{uid}/{ETIQUETA_AGENTE_MAC}"], None)
    elif entorno.plataforma == "win32":
        if entorno.correr(["schtasks", "/Run", "/TN", TAREA_AGENTE_WINDOWS], None) == 0:
            return
        entorno.log("  sin tarea programada: se lanza el agente directo")
        comando = [str(python_del_agente(repo, "win32")), "-m", "agente.main"]
        try:
            (entorno.lanzar or _lanzar_desacoplado)(
                comando, repo / "agente", carpeta_logs(entorno.casa, "win32") / "agente.log"
            )
        except (OSError, subprocess.SubprocessError) as error:
            entorno.log(f"  no se pudo lanzar el agente: {error}")


def autocopiarse(entorno: Entorno, repo: Path) -> None:
    """La copia que corre el sistema se renueva con la del commit recién instalado."""
    origen = repo / "agente" / "instalador" / "actualizar.py"
    destino = entorno.casa / ".centonara" / "bin" / "actualizar.py"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        if origen.exists() and (
            not destino.exists() or destino.read_bytes() != origen.read_bytes()
        ):
            shutil.copy2(origen, destino)
            entorno.log(f"  actualizador copiado a {destino}")
    except OSError as error:
        entorno.log(f"  no se pudo copiar el actualizador: {error}")


# ---------------------------------------------------------------------------
# El recorrido entero
# ---------------------------------------------------------------------------


def actualizar(
    entorno: Entorno,
    repo: Path,
    *,
    sha_forzado: str = "",
    verificar: bool = True,
) -> int:
    log = entorno.log
    log(f"actualizador · repo {repo} · plataforma {entorno.plataforma}")

    env = leer_env(repo / ".env")
    backend = env.get("AGENTE_BACKEND_URL", "")
    token = env.get("AGENTE_TOKEN", "")
    repo_github = env.get("AGENTE_REPO_GITHUB", "martinrodriguez19/centonara-seguimientos")
    instalado = sha_instalado(repo)
    log(f"  instalado: {instalado or 'sin VERSION'}")

    # 1. Qué toca
    if sha_forzado:
        sha = normalizar_sha(sha_forzado)
        if not sha:
            log(f"  {sha_forzado!r} no es un sha")
            return SALIDA_ERROR
        log(f"  sha forzado por línea de comando: {sha}")
    else:
        if not backend or not token:
            log("  falta AGENTE_BACKEND_URL o AGENTE_TOKEN en el .env: no hay a quién preguntar")
            return SALIDA_ERROR
        respuesta = pedir_esperada(entorno, backend, token)
        sha = normalizar_sha(respuesta.get("sha"))
        if respuesta.get("repo"):
            repo_github = str(respuesta["repo"])
        if not sha:
            origen = respuesta.get("origen") or "sin respuesta"
            log(f"  no se sabe qué versión toca ({origen}): no se toca nada")
            return SALIDA_OK
        log(f"  esperado: {sha} (origen: {respuesta.get('origen')})")

    # 2. ¿Ya está?
    if instalado and mismo_sha(instalado, sha):
        log("  al día")
        return SALIDA_OK

    # 3. Bajar
    temporal = Path(tempfile.mkdtemp(prefix="centonara-"))
    try:
        try:
            nuevo = bajar_arbol(entorno, repo_github, sha, temporal)
        except (OSError, ValueError, tarfile.TarError, urllib.error.URLError) as error:
            log(f"  no se pudo bajar el commit: {str(error)[:200]}. No se toca nada.")
            return SALIDA_ERROR

        # 4. Respaldar y aplicar
        vivo_antes = agente_vivo(entorno)
        respaldos = entorno.casa / ".centonara" / "respaldo"
        respaldos.mkdir(parents=True, exist_ok=True)
        respaldo = respaldar(repo, respaldos, instalado or "sin-version")
        log(f"  respaldo en {respaldo}")
        copiados, borrados = sincronizar(nuevo, repo)
        log(f"  aplicado: {copiados} archivos copiados, {borrados} borrados")

        def deshacer(motivo: str) -> int:
            log(f"  DESHACIENDO: {motivo}")
            sincronizar(respaldo, repo)
            uv_sync(entorno, repo)
            if instalado:
                escribir_version(repo, instalado, entorno.ahora())
            else:
                (repo / ARCHIVO_VERSION).unlink(missing_ok=True)
            log(f"  restaurado {instalado or 'el árbol anterior'}")
            return SALIDA_DESHECHO

        # 5. Dependencias, humo, VERSION
        if not uv_sync(entorno, repo):
            return deshacer("uv sync falló")
        if not prueba_de_humo(entorno, repo):
            return deshacer("el agente nuevo no arranca ni para decir su versión")
        escribir_version(repo, sha, entorno.ahora())
        log(f"  VERSION escrita: {sha[:12]}")

        # 6. Que vuelva
        if not verificar:
            log("  sin verificación (pedido por línea de comando)")
        elif vivo_antes:
            log("  esperando a que el agente vuelva con la versión nueva...")
            if not esperar_vuelta(entorno, sha):
                return deshacer("el agente no volvió con la versión nueva")
            log("  el agente volvió con la versión nueva")
        else:
            log("  el agente no estaba corriendo: se intenta levantarlo")
            arrancar_agente(entorno, repo)

        autocopiarse(entorno, repo)
        log(f"  LISTO: {instalado or 'sin versión'} → {sha[:12]}")
        return SALIDA_OK
    finally:
        shutil.rmtree(temporal, ignore_errors=True)


def con_candado(entorno: Entorno, repo: Path, tarea: Callable[[], int]) -> int:
    """Una corrida a la vez: el arranque y la hora pueden pisarse."""
    candado = entorno.casa / ".centonara" / "actualizador.lock"
    candado.parent.mkdir(parents=True, exist_ok=True)
    try:
        if candado.exists() and time.time() - candado.stat().st_mtime > 60 * 60:
            candado.unlink()  # de una corrida que murió
        descriptor = os.open(candado, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        entorno.log("  ya hay un actualizador corriendo")
        return SALIDA_OK
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        return tarea()
    finally:
        candado.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Actualiza el agente al commit que fija el panel.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="carpeta del proyecto (default: la de este archivo, o ~/centonara-seguimientos)",
    )
    parser.add_argument("--sha", default="", help="instalar este commit sin preguntarle al backend")
    parser.add_argument(
        "--sin-verificar", action="store_true", help="no esperar a que el agente vuelva"
    )
    args = parser.parse_args(argv)

    entorno = entorno_real()
    repo = args.repo
    if repo is None:
        aqui = Path(__file__).resolve()
        candidata = (
            aqui.parents[2]
            if aqui.parent.name == "instalador"
            else entorno.casa / "centonara-seguimientos"
        )
        repo = (
            candidata
            if (candidata / "agente" / "pyproject.toml").exists()
            else entorno.casa / "centonara-seguimientos"
        )
    repo = repo.resolve()
    if not (repo / "agente" / "pyproject.toml").exists():
        entorno.log(f"  no hay un proyecto en {repo}")
        return SALIDA_ERROR
    try:
        return con_candado(
            entorno,
            repo,
            lambda: actualizar(
                entorno, repo, sha_forzado=args.sha, verificar=not args.sin_verificar
            ),
        )
    except Exception as error:  # el sistema lo corre sin nadie mirando: que quede en el log
        entorno.log(f"  ERROR inesperado: {type(error).__name__}: {str(error)[:300]}")
        return SALIDA_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
