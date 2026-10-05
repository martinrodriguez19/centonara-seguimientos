"""Cómo el agente se entera de que lo actualizaron, y cómo avisa que está vivo (D46).

El actualizador no reinicia al agente: **el agente se reinicia solo** cuando ve
que `agente/VERSION` cambió, entre un job y el siguiente, nunca en el medio de
uno. Así el reinicio es el mismo en Mac y en Windows, y no depende de que el
actualizador sepa hablar con launchd o con el Programador de tareas.

Dos archivos en `~/.centonara/estado/`, los dos escritos por el agente:

- `vivo.json` — la versión que corre, el pid y la hora del último latido. Lo
  lee el actualizador para saber si el agente estaba vivo antes de actualizar
  (si no lo estaba, no puede esperar que "vuelva") y para confirmar que volvió
  con la versión nueva. Si no vuelve, deshace.
- lo demás lo agrega quien lo necesite; esta carpeta es del agente.

La carpeta vive fuera del repositorio a propósito: el actualizador reemplaza
el árbol entero, y lo que el agente sabe de sí mismo tiene que sobrevivir a eso.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from agente import version as version_mod
from agente.logging import obtener_logger

log = obtener_logger(__name__)

# Con qué código sale el agente cuando pide que lo vuelvan a levantar. En
# macOS no hace falta —se reemplaza a sí mismo con `execv`—; en Windows sale
# con esto y la tarea programada, configurada para reintentar ante un fallo,
# lo vuelve a arrancar.
SALIDA_REINICIO = 75

ARCHIVO_VIVO = "vivo.json"


def carpeta_estado(casa: Path | None = None) -> Path:
    """`~/.centonara/estado`, creada si no existe. Igual en los tres sistemas."""
    carpeta = (casa or Path.home()) / ".centonara" / "estado"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def marcar_vivo(
    version: str,
    *,
    ocupado: bool = False,
    casa: Path | None = None,
    ahora: datetime | None = None,
) -> None:
    """Escribe `vivo.json`. Se llama al registrarse y en cada latido.

    `ocupado` dice si hay un job en curso: el actualizador espera a que el
    agente vuelva con la versión nueva, y una tanda de borradores dura hasta
    35 minutos — sin esto, la daría por muerta y desharía una actualización
    sana.

    Atómico —se escribe a un temporal y se renombra— para que el actualizador
    nunca lea un JSON a medias. Y nunca levanta: un disco lleno no puede
    tumbar el agente por un archivo que sólo mira el actualizador.
    """
    destino = carpeta_estado(casa) / ARCHIVO_VIVO
    temporal = destino.with_suffix(".tmp")
    datos = {
        "version": version,
        "sha": version_mod.sha(version),
        "pid": os.getpid(),
        "ocupado": bool(ocupado),
        "cuando": (ahora or datetime.now(UTC)).isoformat(),
    }
    try:
        temporal.write_text(json.dumps(datos), encoding="utf-8")
        os.replace(temporal, destino)
    except OSError as error:
        log.warning("marca_de_vida_no_escrita", error=str(error)[:200])


def leer_vivo(casa: Path | None = None) -> dict | None:
    """Lo último que el agente dijo de sí mismo, o `None`."""
    try:
        return json.loads((carpeta_estado(casa) / ARCHIVO_VIVO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cambio_la_version(carpeta_agente: Path, version_al_arrancar: str) -> bool:
    """¿`agente/VERSION` dice otra cosa que cuando este proceso arrancó?

    Es la señal de que el actualizador ya aplicó un commit nuevo: el código en
    disco es otro, y este proceso sigue corriendo el viejo. Se compara con lo
    que se leyó al arrancar y no con `__version__`, que es lo mismo pero deja
    explícito de dónde sale cada lado.
    """
    return version_mod.leer(carpeta_agente) != version_al_arrancar


def carpeta_logs_windows() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home()) / "Centonara" / "logs"


TAREA_AGENTE_WINDOWS = "Centonara Agente"


def _hay_tarea_windows() -> bool:
    import subprocess

    try:
        hecho = subprocess.run(
            ["schtasks", "/Query", "/TN", TAREA_AGENTE_WINDOWS],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return hecho.returncode == 0


def guion_del_relevo(pid: int) -> str:
    """El PowerShell que espera a que este proceso termine y arranca la tarea (D62).

    Reintenta un rato: entre que el agente sale y que la tarea pasa a *Ready*
    hay un instante en que sigue *Running* (el `powershell` que lo envolvía
    todavía no cerró), y con `-MultipleInstances IgnoreNew` un arranque en ese
    instante se ignoraría.
    """
    tarea = TAREA_AGENTE_WINDOWS
    return (
        f"Wait-Process -Id {pid} -Timeout 120 -ErrorAction SilentlyContinue; "
        "for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Seconds 2; "
        f"if ((Get-ScheduledTask -TaskName '{tarea}').State -ne 'Running') "
        f"{{ Start-ScheduledTask -TaskName '{tarea}'; break }} }}"
    )


def _relevar_con_la_tarea() -> bool:
    """Deja lanzado el relevo y devuelve `True`; `False` si no se pudo."""
    import subprocess

    banderas = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-Command",
                guion_del_relevo(os.getpid()),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=banderas,
            close_fds=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        log.warning("relevo_no_lanzado", error=str(error)[:200])
        return False
    log.info("agente_relevado_por_la_tarea", tarea=TAREA_AGENTE_WINDOWS)
    return True


def _relanzar_en_windows(argumentos: list[str]) -> int:
    """Que vuelva el agente con el código nuevo, y este proceso se va.

    Con la tarea programada (lo normal desde el instalador), por el relevo de
    D62: la tarea vuelve a arrancarlo y queda *Running*, dueña del proceso.
    Antes se lanzaba un hijo desacoplado y la tarea quedaba *Ready*: si ese
    hijo moría, nadie lo levantaba hasta el próximo inicio de sesión.

    Sin tarea —una PC instalada a mano, el agente en una consola—, o si el
    relevo no se pudo lanzar, el hijo desacoplado de siempre. Si tampoco se
    puede, se sale con `SALIDA_REINICIO`.
    """
    import subprocess

    if _hay_tarea_windows() and _relevar_con_la_tarea():
        return 0

    try:
        carpeta = carpeta_logs_windows()
        carpeta.mkdir(parents=True, exist_ok=True)
        salida = (carpeta / "agente.log").open("ab")
        banderas = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        subprocess.Popen(
            argumentos,
            cwd=os.getcwd(),
            stdin=subprocess.DEVNULL,
            stdout=salida,
            stderr=salida,
            creationflags=banderas,
            close_fds=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        log.warning("agente_no_pudo_relanzarse", error=str(error)[:200], codigo=SALIDA_REINICIO)
        return SALIDA_REINICIO
    log.info("agente_relanzado_en_windows", argumentos=argumentos[1:])
    return 0


def reejecutar() -> int:
    """Vuelve a arrancar el agente con el código que hay en disco.

    En POSIX, `execv` reemplaza este proceso por uno nuevo con el mismo pid:
    launchd no ve nada y el agente vuelve al instante con el código nuevo. En
    Windows no hay `execv` de verdad: se lanza un hijo desacoplado con la
    salida en `%LOCALAPPDATA%\\Centonara\\logs\\agente.log` y este proceso se
    va con 0 — sirve tanto para una PC instalada a mano como para la tarea
    programada. Sólo si el hijo no se puede crear se sale con
    `SALIDA_REINICIO`, para que la tarea, si existe, lo reintente.

    Devuelve el código de salida sólo en Windows; en POSIX no vuelve.
    """
    argumentos = [sys.executable, "-m", "agente.main", *sys.argv[1:]]
    if sys.platform == "win32":
        sys.stdout.flush()
        sys.stderr.flush()
        return _relanzar_en_windows(argumentos)
    log.info("agente_se_reejecuta", argumentos=argumentos[1:])
    #  Sin buffers a medio escribir en el proceso que se va.
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, argumentos)
    return SALIDA_REINICIO  # pragma: no cover - execv no vuelve
