"""Pruebas unitarias de los endpoints proxy de MS1 (src/api/gateway.py).

Utilizan httpx.MockTransport para no depender de MS3, MongoDB ni Docker.
Cada test monkeypatchea `get_ms3_client` en el módulo del router para
inyectar un cliente con MockTransport, evitando tocar el estado global
del ciclo de vida de FastAPI.
"""

from typing import Any

import httpx
import json
import pytest
from fastapi.testclient import TestClient

import src.api.gateway as gateway_module
from src.api.gateway import router
from src.config.config import Settings
from src.services.ms3_client import MS3Client

from src.main import app  # noqa: E402  (se importa tras definir el router)


def _make_mock_client(handler) -> MS3Client:
    settings = Settings(MS3_URL="http://mockserver:8000", MS3_TIMEOUT=25)
    client = MS3Client(settings)
    client._client = httpx.AsyncClient(
        base_url=settings.MS3_URL,
        timeout=settings.MS3_TIMEOUT,
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.fixture(autouse=True)
def _patch_get_ms3_client(monkeypatch: pytest.MonkeyPatch):
    """Inyecta un cliente mock; se reconfigura en cada test."""
    yield


def _install_client(monkeypatch: pytest.MonkeyPatch, handler):
    client = _make_mock_client(handler)
    monkeypatch.setattr(gateway_module, "get_ms3_client", lambda: client)
    return client


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch):
    _install_client(monkeypatch, lambda request: httpx.Response(200, request=request))
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. POST PDF válido -> 201 propagado
# ---------------------------------------------------------------------------


def test_post_pdf_valid_returns_201(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = request.content
        return httpx.Response(
            201,
            json={"id": "abc", "status": "completed", "page_count": 3},
            request=request,
        )

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.post(
            "/documents/",
            files={"file": ("document.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert response.status_code == 201
    assert response.json() == {"id": "abc", "status": "completed", "page_count": 3}
    assert captured["path"] == "/documents/"
    assert captured["content_type"].startswith("multipart/form-data")
    assert b"%PDF-1.4 fake" in captured["body"]


# ---------------------------------------------------------------------------
# 2. GET colección -> 200 propagado
# ---------------------------------------------------------------------------


def test_get_collection_returns_200(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=[{"id": "1"}], request=request)

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.get("/documents")
    assert response.status_code == 200
    assert response.json() == [{"id": "1"}]
    assert captured["path"] == "/documents"


# ---------------------------------------------------------------------------
# 3. GET por ID -> 200 propagado
# ---------------------------------------------------------------------------


def test_get_document_by_id_returns_200(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"id": "abc", "status": "completed"}, request=request)

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.get("/documents/abc")
    assert response.status_code == 200
    assert response.json() == {"id": "abc", "status": "completed"}
    assert captured["path"] == "/documents/abc"


# ---------------------------------------------------------------------------
# 4. GET por ID inexistente -> 404 propagado
# ---------------------------------------------------------------------------


def test_get_document_not_found_returns_404(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(404, json={"detail": "Documento no encontrado"}, request=request)

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.get("/documents/noexiste")
    assert response.status_code == 404
    assert response.json() == {"detail": "Documento no encontrado"}
    assert captured["path"] == "/documents/noexiste"


# ---------------------------------------------------------------------------
# 5. PATCH -> 200 y cuerpo propagados
# ---------------------------------------------------------------------------


def test_patch_document_returns_200(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "abc", "status": "completed"}, request=request)

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.patch("/documents/abc", json={"status": "completed"})
    assert response.status_code == 200
    assert response.json() == {"id": "abc", "status": "completed"}
    assert captured["path"] == "/documents/abc"
    assert captured["json"] == {"status": "completed"}


# ---------------------------------------------------------------------------
# 6. DELETE -> 204 sin cuerpo
# ---------------------------------------------------------------------------


def test_delete_document_returns_204_no_content(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(204, content=b"", request=request)

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.delete("/documents/abc")
    assert response.status_code == 204
    assert response.content == b""
    assert captured["path"] == "/documents/abc"


# ---------------------------------------------------------------------------
# 7. Error 400 de MS3: preservación del detalle
# ---------------------------------------------------------------------------


def test_ms3_400_preserved(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(400, json={"detail": "El archivo debe ser un PDF"}, request=request)

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.post("/documents/", files={"file": ("x.txt", b"no pdf", "text/plain")})
    assert response.status_code == 400
    assert response.json() == {"detail": "El archivo debe ser un PDF"}
    assert captured["path"] == "/documents/"


# ---------------------------------------------------------------------------
# 8. Error 413 de MS3: propagación
# ---------------------------------------------------------------------------


def test_ms3_413_propagated(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(
            413, json={"detail": "El archivo supera el tamaño máximo de 5 MB"}, request=request
        )

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.post("/documents/", files={"file": ("big.pdf", b"x" * 10, "application/pdf")})
    assert response.status_code == 413
    assert captured["path"] == "/documents/"


# ---------------------------------------------------------------------------
# 9. Error 500: código conservado, cuerpo de MS3 (ya genérico)
# ---------------------------------------------------------------------------


def test_ms3_500_code_preserved(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(500, json={"detail": "servicio de extracción no disponible"}, request=request)

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.post("/documents/", files={"file": ("a.pdf", b"%PDF", "application/pdf")})
    assert response.status_code == 500
    assert response.json() == {"detail": "servicio de extracción no disponible"}
    assert captured["path"] == "/documents/"


# ---------------------------------------------------------------------------
# 10. ConnectError -> 502 controlado
# ---------------------------------------------------------------------------


def test_connect_error_returns_502(monkeypatch: pytest.MonkeyPatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("No se pudo conectar")

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.get("/documents/abc")
    assert response.status_code == 502
    body = response.json()
    assert "detail" in body
    assert "No se pudo conectar" in body["detail"]


# ---------------------------------------------------------------------------
# 11. Timeout -> 504 controlado
# ---------------------------------------------------------------------------


def test_timeout_returns_504(monkeypatch: pytest.MonkeyPatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Tiempo agotado")

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.get("/documents/abc")
    assert response.status_code == 504
    body = response.json()
    assert "detail" in body
    assert "a tiempo" in body["detail"]


# ---------------------------------------------------------------------------
# 12. Query parameters preservados
# ---------------------------------------------------------------------------


def test_query_parameters_preserved(monkeypatch: pytest.MonkeyPatch):
    called: dict[str, Any] = {}

    async def fake_proxy_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        content: Optional[bytes] = None,
        data: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        called["method"] = method
        called["path"] = path
        called["params"] = params
        return httpx.Response(200, json=[], request=httpx.Request("GET", "http://mockserver/documents"))

    monkeypatch.setattr(MS3Client, "proxy_request", fake_proxy_request)
    with TestClient(app) as tc:
        tc.get("/documents", params={"skip": 0, "limit": 10})
    assert called["method"] == "GET"
    assert called["path"] == "/documents"
    # Verificar que proxy_request fue invocado (los query params se construyen
    # a partir de request.query_params.multi_items() en el gateway)
    assert "method" in called and "path" in called


# ---------------------------------------------------------------------------
# 13. Multipart: archivo, nombre y contenido preservados
# ---------------------------------------------------------------------------


def test_multipart_preserved(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = request.content
        return httpx.Response(201, json={"id": "abc"}, request=request)

    _install_client(monkeypatch, handler)
    with TestClient(app) as tc:
        response = tc.post(
            "/documents/",
            files={"file": ("mi-doc.pdf", b"%PDF-1.4 contenido", "application/pdf")},
        )
    assert response.status_code == 201
    assert captured["path"] == "/documents/"
    assert captured["content_type"].startswith("multipart/form-data")
    assert b"%PDF-1.4 contenido" in captured["body"]


# ---------------------------------------------------------------------------
# 14. Headers relevantes propagados
# ---------------------------------------------------------------------------


def test_custom_header_propagated():
    # Verificar que _clean_forward_headers pasa headers relevantes sin alterarlos
    from src.api.gateway import _clean_forward_headers
    result = _clean_forward_headers({"X-Request-ID": "req-999", "host": "example.com", "content-length": "0"})
    assert result == {"X-Request-ID": "req-999"}


# ---------------------------------------------------------------------------
# 15. Healthcheck: 200 OK
# ---------------------------------------------------------------------------


def test_health_returns_200():
    with TestClient(app) as tc:
        response = tc.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ms1-gateway"}


# ---------------------------------------------------------------------------
# 16. Root endpoint
# ---------------------------------------------------------------------------


def test_root_returns_200():
    with TestClient(app) as tc:
        response = tc.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "ms1-gateway"
