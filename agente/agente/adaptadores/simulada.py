"""Una página falsa: WhatsApp Web en memoria, para los tests.

Existe por una razón concreta y no por gusto de abstraer: los casos que hay que
probar del motor de envío **no se pueden montar a pedido en un WhatsApp de
verdad**. Dos contactos con el mismo nombre, un chat archivado, un grupo, un
número que la interfaz no muestra — todos son escenarios que hay que fabricar, y
son justamente los que deciden si el sistema le escribe a la persona equivocada.

Lo que esto NO es: un simulador fiel de WhatsApp. Es un doble que responde las
ocho preguntas que hace `jobs/enviar.py`, y nada más.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agente.adaptadores.pagina import ErrorDeSelector, PaginaNoCargo


@dataclass
class Chat:
    """Un chat, como lo ve el motor de envío."""

    nombre: str
    #  El teléfono tal como lo mostraría la interfaz. `None` = no se puede leer,
    #  que es el caso interesante.
    telefono: str | None
    es_grupo: bool = False
    #  Lo que el vendedor dejó escrito sin mandar.
    borrador_del_vendedor: str = ""
    #  Si el header no se puede leer. Pasa con chats archivados y con la
    #  interfaz a medio cargar.
    header_ilegible: bool = False
    mensajes: list[str] = field(default_factory=list)


class PaginaSimulada:
    """Implementa `Pagina` contra un diccionario de chats."""

    def __init__(
        self,
        chats: dict[str, Chat] | None = None,
        *,
        sesion: bool = True,
        selector_roto: bool = False,
        confirma: bool = True,
        carga: bool = True,
    ) -> None:
        # La clave es lo que se busca. Puede no coincidir con el teléfono real
        # del chat, y ese desajuste es el escenario que importa.
        self.chats = chats or {}
        self._sesion = sesion
        self._selector_roto = selector_roto
        self._confirma = confirma
        #  `carga=False` simula la página que no termina de cargar: red lenta,
        #  Chrome recién abierto. `abrir_whatsapp` lanza `PaginaNoCargo`.
        self._carga = carga
        #  Como la página real: nace sin navegar (about:blank), y ahí no hay ni
        #  QR ni lista de chats. Preguntar por la sesión antes de abrir tiene
        #  que dar `False` — es el orden equivocado que causó el 27/08, y los
        #  tests lo aseveran gracias a esto.
        self.navegada: bool = False

        self.abierto: Chat | None = None
        self.campo: str = ""
        #  Lo que efectivamente se mandó. Los tests miran esto: es la única
        #  forma de verificar que un aborto no escribió nada.
        self.enviados: list[tuple[str, str]] = []

    # -- Lo que pide el Protocol ---------------------------------------------

    async def sesion_iniciada(self) -> bool:
        return self.navegada and self._sesion

    async def abrir_whatsapp(self) -> None:
        self._quejarse_si_esta_roto()
        if not self._carga:
            raise PaginaNoCargo("ni la lista de chats ni el QR aparecieron")
        self.navegada = True

    async def buscar_contacto(self, identificador: str) -> bool:
        self._quejarse_si_esta_roto()
        self.motivo_no_abrio: str | None = None
        chat = self.chats.get(identificador)
        if chat is None:
            self.motivo_no_abrio = "sin_resultados"
            return False
        self.abierto = chat
        self.campo = chat.borrador_del_vendedor
        return True

    async def leer_header(self) -> str | None:
        self._quejarse_si_esta_roto()
        if self.abierto is None or self.abierto.header_ilegible:
            return None
        return self.abierto.nombre

    async def resolver_numero(self) -> str | None:
        self._quejarse_si_esta_roto()
        return self.abierto.telefono if self.abierto else None

    async def es_grupo(self) -> bool:
        return bool(self.abierto and self.abierto.es_grupo)

    async def campo_tiene_texto(self) -> bool:
        return bool(self.campo.strip())

    async def escribir(self, texto: str) -> None:
        self._quejarse_si_esta_roto()
        # Literal. Si esto reformulara algo, el sistema estaría mandando otra
        # cosa que la que una persona aprobó en el panel.
        self.campo = texto

    async def apretar_enviar(self) -> None:
        self._quejarse_si_esta_roto()
        if self.abierto is None:
            raise ErrorDeSelector("no hay ningún chat abierto")
        self.abierto.mensajes.append(self.campo)
        self.enviados.append((self.abierto.telefono or self.abierto.nombre, self.campo))
        self.campo = ""

    async def confirmar_en_hilo(self, texto: str, *, timeout_s: float = 15) -> bool:
        del timeout_s
        if not self._confirma:
            return False
        return bool(self.abierto and texto in self.abierto.mensajes)

    async def limpiar_campo(self) -> None:
        self.campo = ""

    async def cerrar_chat(self) -> None:
        # Como WhatsApp Web: al salir del chat, lo escrito queda como borrador
        # de esa conversación.
        if self.abierto is not None:
            self.abierto.borrador_del_vendedor = self.campo
        self.abierto = None
        self.campo = ""

    # -- Ayudas para los tests ------------------------------------------------

    def _quejarse_si_esta_roto(self) -> None:
        if self._selector_roto:
            raise ErrorDeSelector("el selector no encontró nada: el DOM cambió")

    @property
    def escribio_algo(self) -> bool:
        """¿Quedó algo en el campo de escritura?

        Es lo que verifica que un aborto abortó de verdad. Que el log diga
        "aborté" no alcanza: hay que ver que la pantalla quedó limpia.
        """
        return bool(self.campo.strip())
