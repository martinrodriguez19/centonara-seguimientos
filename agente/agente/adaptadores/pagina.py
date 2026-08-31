"""Lo que el motor de envío necesita de un navegador. Nada más.

Playwright implementa estas operaciones contra WhatsApp Web real, y una página
falsa las implementa en memoria para los tests. Desde el plan de cascadas, la
apertura del chat son varios escalones (`buscar_*`, `abrir_por_url`): el motor
los prueba en orden y el primero que abre gana — ninguno exime de la
comparación de identidad ni del chequeo de campo vacío.

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


class PaginaNoCargo(Exception):
    """WhatsApp Web no terminó de cargar: ni el QR ni la lista aparecieron.

    Se distingue de `ErrorDeSelector` a propósito, porque las consecuencias son
    opuestas. `SELECTOR_ROTO` frena la corrida entera —el DOM cambió para
    todos—; una página que no cargó es red lenta, un Chrome recién abierto, una
    pestaña suspendida: transitorio, y el job se reintenta como `TIMEOUT`.
    Confundirlos convierte una demora en un freno total, o un DOM roto en
    reintentos inútiles.
    """


@runtime_checkable
class Pagina(Protocol):
    """WhatsApp Web, reducido a lo que hace falta para mandar un mensaje."""

    async def abrir_whatsapp(self) -> None:
        """Navega si hace falta y deja la página decidida: lista de chats o QR.

        **Se llama antes que cualquier otra pregunta**, incluida
        `sesion_iniciada` — sobre una página sin navegar no hay ni QR ni lista,
        y preguntar por la sesión ahí devuelve un "sesión caída" falso.
        Lanza `PaginaNoCargo` si no aparece ninguna de las dos cosas.
        """
        ...

    async def sesion_iniciada(self) -> bool:
        """¿Está la sesión activa, o pide escanear el código?

        Presupone `abrir_whatsapp()` ya corrido: es quien garantiza que la
        página está en WhatsApp Web y decidida entre el QR y la lista.
        """
        ...

    async def buscar_contacto(self, identificador: str) -> bool:
        """Busca y abre el chat. `False` si no aparece ninguno.

        Es el primer escalón de la cascada de apertura: los de abajo corren
        sólo cuando éste (y los anteriores en la lista) devolvieron `False`.
        Ningún escalón exime de lo que sigue después de abrir — la comparación
        de identidad por número y el campo vacío corren igual para todos.
        """
        ...

    async def buscar_verificado(self, termino: str, numero: str | None = None) -> bool:
        """A3: sólo clickea filas cuyo texto CONTENGA lo buscado.

        Dígito a dígito cuando lo buscado es un número. Si ninguna fila lo
        contiene, `False` — «no está», nunca un click a ciegas. En `RESOLVER`
        no es un escalón opcional sino la regla: ahí no existe la comparación
        de identidad que protege a `ENVIAR`, y un número mal resuelto queda
        guardado como el del contacto.
        """
        ...

    async def buscar_limpiando_filtros(self, termino: str) -> bool:
        """A4: en WhatsApp Business, volver el filtro a «Todos» y rebuscar."""
        ...

    async def buscar_tipeando_distinto(self, termino: str) -> bool:
        """A5: otra forma de escribir el término, para cuando el texto entra
        al buscador pero no dispara el filtrado."""
        ...

    async def buscar_con_teclado(self, termino: str) -> bool:
        """A6: abrir el primer resultado con el teclado, sin selector de lista."""
        ...

    async def buscar_con_otra_ancla(self, termino: str) -> bool:
        """A7: las filas por anclas alternativas, logueando cuál devolvió."""
        ...

    async def abrir_por_url(self, numero: str) -> bool:
        """A8: el chat por URL directa, sin buscador. Recarga la página, y con
        un número sin WhatsApp detecta el cartel de error y devuelve `False`."""
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
