"""La sesión del panel: una contraseña y una cookie firmada.

Sin Auth.js, sin magic links, sin correo saliente (D22). Entran una o dos
personas; el magic link resuelve el problema de administrar muchos usuarios, que
no tenemos.

**Qué lleva la cookie:** cuándo vence, y nada más. No hay identidad que guardar
—hay una sola contraseña— así que no hay ningún dato del usuario circulando. Lo
que la hace confiable no es que esté cifrada (no lo está, y se puede leer): es
que está **firmada**, y sin el secreto no se puede fabricar una con otra fecha.

Es criptografía escrita a mano, que en general es mala idea. Acá se justifica
porque el problema es del tamaño exacto que resuelven tres líneas de `hmac`:
firmar un número y verificarlo. Si algún día la sesión tuviera que llevar datos,
esto se reemplaza por una biblioteca en vez de crecer.
"""

from __future__ import annotations

import base64
import hmac
import secrets
import time
from dataclasses import dataclass
from hashlib import sha256

NOMBRE_COOKIE = "sesion"

# Ocho horas: una jornada. El dueño entra al mediodía, revisa, aprieta enviar y
# se va; que le pida la contraseña de nuevo al otro día es razonable.
DURACION_SEGUNDOS = 8 * 60 * 60


@dataclass(frozen=True)
class Sesion:
    vence_en: int

    def vencida(self, ahora: float | None = None) -> bool:
        return (ahora or time.time()) >= self.vence_en


def _firmar(secreto: str, cuerpo: str) -> str:
    firma = hmac.new(secreto.encode("utf-8"), cuerpo.encode("utf-8"), sha256).digest()
    return base64.urlsafe_b64encode(firma).decode("ascii").rstrip("=")


def emitir(secreto: str, *, duracion: int = DURACION_SEGUNDOS, ahora: float | None = None) -> str:
    """Una cookie de sesión válida por `duracion` segundos."""
    if not secreto:
        raise ValueError("falta SESION_SECRET: sin secreto no se puede firmar nada")
    vence = int((ahora or time.time()) + duracion)
    cuerpo = str(vence)
    return f"{cuerpo}.{_firmar(secreto, cuerpo)}"


def verificar(secreto: str, cookie: str | None, *, ahora: float | None = None) -> Sesion | None:
    """La sesión si la cookie es válida y no venció; `None` en cualquier otro caso.

    Devuelve `None` y no lanza: una cookie ausente, mal formada, con firma
    inválida o vencida son todas la misma cosa desde afuera —no estás
    autenticado— y distinguirlas en la respuesta le diría a quien prueba cuál se
    acercó más.
    """
    if not secreto or not cookie or "." not in cookie:
        return None

    cuerpo, _, firma = cookie.rpartition(".")

    # `compare_digest` y no `==`: la comparación normal corta en el primer byte
    # distinto, y ese tiempo distinto es una filtración.
    #
    # En bytes y no en str: con strings, `compare_digest` exige ASCII y lanza
    # TypeError con cualquier otra cosa. La cookie la manda el cliente, así que
    # puede tener lo que quiera — y un TypeError acá sería un 500 donde
    # corresponde un 401.
    if not hmac.compare_digest(firma.encode("utf-8"), _firmar(secreto, cuerpo).encode("utf-8")):
        return None

    try:
        sesion = Sesion(vence_en=int(cuerpo))
    except ValueError:
        return None

    return None if sesion.vencida(ahora) else sesion


def clave_correcta(esperada: str, recibida: str) -> bool:
    """¿La contraseña es la del panel?

    `compare_digest` otra vez, por lo mismo. Y una contraseña vacía en la
    configuración **nunca** valida: si `PANEL_PASSWORD` no se cargó en Render,
    el panel queda cerrado en vez de abierto para cualquiera que mande un
    formulario vacío.
    """
    if not esperada:
        return False
    # En bytes: una contraseña con acento haría que `compare_digest` sobre str
    # lance TypeError, y el login devolvería 500 en vez de "contraseña
    # incorrecta". Lo encontró un test con "abracadabrá".
    return hmac.compare_digest(esperada.encode("utf-8"), (recibida or "").encode("utf-8"))


def generar_secreto() -> str:
    """Para el `.env` de alguien que arranca de cero."""
    return secrets.token_hex(32)
