"""Lo que el motor de envío necesita de un navegador. Nada más.

Ocho operaciones. Playwright las implementa contra WhatsApp Web real, y una
página falsa las implementa en memoria para los tests.

**Por qué existe esta costura.** No es una abstracción por si algún día
cambiamos de canal — eso sería inventar trabajo. Es porque el paso más
importante del proyecto —verificar a quién le estamos escribiendo antes de
escribir— tiene que poder probarse contra los casos que importan: dos contactos
con el mismo nombre, un grupo, un chat archivado, un número que no se puede
leer. Ninguno de esos se puede montar a pedido en un WhatsApp de verdad.

La lista es corta a propósito. Cada operación que se agregue acá es una que
después hay que implementar dos veces y mantener sincronizada.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class ErrorDeSelector(Exception):
    """Un selector no encontró lo que buscaba: el DOM cambió.

    Se distingue de "no está" a propósito. Que un chat no exista es un dato del
    mundo; que el selector del campo de escritura no matchee es que WhatsApp
    Web cambió, y eso frena la corrida entera porque los envíos siguientes van a
    fallar igual.
    """


@runtime_checkable
class Pagina(Protocol):
    """WhatsApp Web, reducido a lo que hace falta para mandar un mensaje."""

    async def abrir_whatsapp(self) -> None:
        """Deja la lista de chats a la vista. Lanza si pide QR."""
        ...

    async def sesion_iniciada(self) -> bool:
        """¿Está la sesión activa, o pide escanear el código?"""
        ...

    async def buscar_contacto(self, identificador: str) -> bool:
        """Busca y abre el chat. `False` si no aparece ninguno."""
        ...

    async def leer_header(self) -> str | None:
        """El encabezado del chat abierto. `None` si no se puede leer.

        `None` **no** es "está vacío": es "no sé qué dice", y con eso no se
        escribe nada.
        """
        ...

    async def resolver_numero(self) -> str | None:
        """El teléfono del chat abierto, tal como lo muestra WhatsApp.

        `None` si no se puede determinar con certeza. Devolver algo aproximado
        acá sería peor que devolver nada: lo que sigue es una comparación, y una
        comparación contra un dato inventado da falsos positivos.
        """
        ...

    async def es_grupo(self) -> bool:
        """Un grupo nunca recibe un seguimiento comercial."""
        ...

    async def campo_tiene_texto(self) -> bool:
        """¿Hay algo escrito en el campo de mensaje?

        Si lo hay, alguien está usando ese chat en este momento.
        """
        ...

    async def escribir(self, texto: str) -> None:
        """Pone el texto en el campo. **Literal**: no reformula ni completa."""
        ...

    async def apretar_enviar(self) -> None:
        """El único método que hace que un mensaje salga."""
        ...

    async def confirmar_en_hilo(self, texto: str, *, timeout_s: float = 15) -> bool:
        """¿Apareció el mensaje en la conversación?

        `False` no significa que no salió: significa que no se pudo verificar.
        Son cosas distintas y el sistema las trata distinto.
        """
        ...

    async def limpiar_campo(self) -> None:
        """Borra lo que se haya escrito, sin enviar."""
        ...

    async def cerrar_chat(self) -> None:
        """Cierra el chat abierto y vuelve a la lista.

        Es el paso final del modo borradores (D30): lo escrito queda guardado
        por WhatsApp como borrador de ese chat, listo para que el vendedor lo
        mande con un click.
        """
        ...
