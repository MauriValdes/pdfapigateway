"""Pruebas unitarias del cliente HTTP hacia MS3 (src/services/ms3_client.py).

Utilizan httpx.MockTransport para no depender de MS3, MongoDB ni Docker.
Cada test instancia su propio cliente y limpia el estado global.
"""

from typing import Any

import httpx
import pytest

from src.config.config import Settings
from src.services.ms3_client import (
    MS3Client,
    MS3ClientError,
    MS3ConnectionError,
    MS3TimeoutError,
    get_ms3_client,
    close_ms3_client,
)


def _make_client(
    transport: httpx.MockTransport | None = None,
    ms3_url: str = "http://mockserver:8000",
    timeout: int = 25,
) -> MS3Client:
    settings = Settings(MS3_URL=ms3_url, MS3_TIMEOUT=timeout)
    client = MS3Client(settings)
    if transport is not None:
        client._client = httpx.AsyncClient(
            base_url=settings.MS3_URL,
            timeout=settings.MS3_TIMEOUT,
            transport=transport,
        )
    return client


def _handler_factory(status_code: int = 200, json_body: Any = None):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json=json_body,
            request=request,
        )

    return handler


@pytest.mark.asyncio
async def test_client_base_url_and_timeout():
    client = _make_client()
    assert str(client.client.base_url) == "http://mockserver:8000"
    assert client.client.timeout.connect == 25.0
    assert client.client.timeout.read == 25.0
    await client.aclose()


@pytest.mark.asyncio
async def test_proxy_get():
    transport = httpx.MockTransport(_handler_factory(200, {"ok": True}))
    client = _make_client(transport)
    response = await client.proxy_request("GET", "/documents/")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert str(response.url).endswith("/documents/")
    await client.aclose()


@pytest.mark.asyncio
async def test_proxy_post_json():
    transport = httpx.MockTransport(_handler_factory(201, {"id": "abc"}))
    client = _make_client(transport)
    response = await client.proxy_request(
        "POST", "/documents/", json={"filename": "a.pdf"}
    )
    assert response.status_code == 201
    assert response.json() == {"id": "abc"}
    await client.aclose()


@pytest.mark.asyncio
async def test_proxy_patch_json():
    transport = httpx.MockTransport(_handler_factory(200, {"status": "completed"}))
    client = _make_client(transport)
    response = await client.proxy_request(
        "PATCH", "/documents/abc", json={"status": "completed"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    await client.aclose()


@pytest.mark.asyncio
async def test_proxy_delete():
    transport = httpx.MockTransport(_handler_factory(204, None))
    client = _make_client(transport)
    response = await client.proxy_request("DELETE", "/documents/abc")
    assert response.status_code == 204
    await client.aclose()


@pytest.mark.asyncio
async def test_query_parameters_preserved():
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, request=request)

    transport = httpx.MockTransport(handler)
    client = _make_client(transport)
    await client.proxy_request(
        "GET", "/documents/", params={"skip": 0, "limit": 10}
    )
    assert "skip=0" in captured["url"]
    assert "limit=10" in captured["url"]
    await client.aclose()


@pytest.mark.asyncio
async def test_headers_preserved():
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, request=request)

    transport = httpx.MockTransport(handler)
    client = _make_client(transport)
    await client.proxy_request(
        "GET", "/documents/abc", headers={"X-Request-ID": "req-123"}
    )
    assert captured["headers"].get("x-request-id") == "req-123"
    await client.aclose()


@pytest.mark.asyncio
async def test_multipart_form_data_preserved():
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = request.content
        return httpx.Response(201, json={"id": "abc"}, request=request)

    transport = httpx.MockTransport(handler)
    client = _make_client(transport)
    files = {"file": ("document.pdf", b"%PDF-1.4 fake", "application/pdf")}
    response = await client.proxy_request(
        "POST", "/documents/", files=files
    )
    assert response.status_code == 201
    assert response.json() == {"id": "abc"}
    assert captured["content_type"].startswith("multipart/form-data")
    assert b"%PDF-1.4 fake" in captured["body"]
    await client.aclose()


@pytest.mark.asyncio
async def test_response_400_not_raised():
    transport = httpx.MockTransport(_handler_factory(400, {"detail": "bad request"}))
    client = _make_client(transport)
    response = await client.proxy_request("POST", "/documents/", json={})
    assert response.status_code == 400
    assert response.json() == {"detail": "bad request"}
    await client.aclose()


@pytest.mark.asyncio
async def test_response_404_not_raised():
    transport = httpx.MockTransport(_handler_factory(404, {"detail": "not found"}))
    client = _make_client(transport)
    response = await client.proxy_request("GET", "/documents/noexiste")
    assert response.status_code == 404
    await client.aclose()


@pytest.mark.asyncio
async def test_response_500_not_raised():
    transport = httpx.MockTransport(_handler_factory(500, {"detail": "error"}))
    client = _make_client(transport)
    response = await client.proxy_request("GET", "/documents/abc")
    assert response.status_code == 500
    await client.aclose()


@pytest.mark.asyncio
async def test_connect_error_raises_ms3_connection_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("No se pudo conectar")

    transport = httpx.MockTransport(handler)
    client = _make_client(transport)
    with pytest.raises(MS3ConnectionError):
        await client.proxy_request("GET", "/documents/")
    await client.aclose()


@pytest.mark.asyncio
async def test_timeout_error_raises_ms3_timeout_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Tiempo agotado")

    transport = httpx.MockTransport(handler)
    client = _make_client(transport)
    with pytest.raises(MS3TimeoutError):
        await client.proxy_request("GET", "/documents/")
    await client.aclose()


@pytest.mark.asyncio
async def test_aclose_closes_client():
    transport = httpx.MockTransport(_handler_factory(200, {"ok": True}))
    client = _make_client(transport)
    assert client.client.is_closed is False
    await client.aclose()
    # MS3Client.aclose descarta la referencia al cliente HTTP
    assert client._client is None


def test_get_ms3_client_returns_instance():
    # Limpia posible estado previo
    import src.services.ms3_client as ms3_mod

    ms3_mod._client_instance = None
    client = get_ms3_client()
    assert isinstance(client, MS3Client)
    # Segundo llamado retorna la misma instancia
    assert get_ms3_client() is client


def test_close_ms3_client_clears_instance():
    import src.services.ms3_client as ms3_mod

    ms3_mod._client_instance = None
    client = get_ms3_client()
    assert ms3_mod._client_instance is client
    import asyncio

    asyncio.run(close_ms3_client())
    assert ms3_mod._client_instance is None
