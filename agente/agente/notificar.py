"""Una notificación del sistema en la computadora del vendedor (D70).

Cuando se abre la ventana del QR o el inicio de sesión de Claude, el vendedor
tiene que mirarla. Un aviso del sistema operativo es lo que se ve aunque esté
en otra cosa, y no pide instalar nada:

- macOS: `osascript … display notification`;
- Windows: una notificación de Windows hecha desde PowerShell, con el
  identificador de aplicación de PowerShell (no hace falta registrar uno).

Nunca puede frenar nada: si no se puede mostrar, se loguea y se sigue. El
texto viaja por variables de entorno y no armado dentro del comando, así un
nombre con comillas no rompe ni inyecta nada.
"""

from __future__ import annotations

import os
import subprocess
import sys

from agente.logging import obtener_logger

log = obtener_logger(__name__)

_MAC = (
    "on run argv",
    'display notification (item 2 of argv) with title (item 1 of argv) sound name "Glass"',
    "end run",
)

_WINDOWS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$plantilla = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textos = $plantilla.GetElementsByTagName("text")
$textos.Item(0).AppendChild($plantilla.CreateTextNode($env:CENTONARA_TITULO)) | Out-Null
$textos.Item(1).AppendChild($plantilla.CreateTextNode($env:CENTONARA_TEXTO)) | Out-Null
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($plantilla))
"""  # noqa: E501


def _correr(comando: list[str], entorno: dict[str, str] | None = None) -> None:
    subprocess.run(
        comando,
        capture_output=True,
        timeout=15,
        check=False,
        env={**os.environ, **(entorno or {})},
    )


def avisar(titulo: str, texto: str, *, plataforma: str | None = None, correr=_correr) -> bool:
    """Muestra el aviso. `True` si se pudo pedir; nunca lanza."""
    destino = plataforma or sys.platform
    try:
        if destino == "darwin":
            lineas = [parte for linea in _MAC for parte in ("-e", linea)]
            correr(["osascript", *lineas, titulo[:80], texto[:240]])
        elif destino == "win32":
            correr(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS],
                {"CENTONARA_TITULO": titulo[:80], "CENTONARA_TEXTO": texto[:240]},
            )
        else:
            log.info("aviso_sin_sistema", titulo=titulo)
            return False
    except (OSError, subprocess.SubprocessError) as error:
        log.warning("aviso_no_mostrado", error=str(error)[:200])
        return False
    log.info("aviso_mostrado", titulo=titulo)
    return True
