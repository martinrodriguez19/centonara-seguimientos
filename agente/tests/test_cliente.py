"""El cliente HTTP del agente, frente a un backend que todavía no se actualizó.

Las máquinas se actualizan solas desde GitHub, a veces antes de que alguien
despliegue el backend. Un campo nuevo no puede dejar a una máquina sin latido.
"""

from __future__ import annotations

import json

import httpx

from agente.cliente import Cliente


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


async def test_manda_los_detalles_a_un_backend_que_los_conoce() -> None:
    cliente, recibidos = con_backend(lambda cuerpo: httpx.Response(200, json={"ok": True}))

    await cliente.latido({"perfiles": "falla"}, detalles={"perfiles": "falta la extensión"})

    assert recibidos == [
        {"diagnostico": {"perfiles": "falla"}, "detalles": {"perfiles": "falta la extensión"}}
    ]


async def test_un_backend_viejo_los_rechaza_y_se_dejan_de_mandar() -> None:
    def viejo(cuerpo: dict) -> httpx.Response:
        return httpx.Response(422 if "detalles" in cuerpo else 200, json={"ok": True})

    cliente, recibidos = con_backend(viejo)

    respuesta = await cliente.latido({"perfiles": "falla"}, detalles={"perfiles": "x"})
    await cliente.registrar(version="v", diagnostico={}, detalles={"perfiles": "x"})

    assert respuesta == {"ok": True}
    assert ["detalles" in c for c in recibidos] == [True, False, False]


async def test_sin_nada_que_decir_no_manda_el_campo() -> None:
    cliente, recibidos = con_backend(lambda cuerpo: httpx.Response(200, json={"ok": True}))

    await cliente.registrar(version="v", diagnostico={"chrome": "ok"}, detalles={})

    assert recibidos == [{"version": "v", "diagnostico": {"chrome": "ok"}, "modo": ""}]
