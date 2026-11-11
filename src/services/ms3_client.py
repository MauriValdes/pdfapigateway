"""Cliente HTTP asíncrono para comunicarse con MS3 (PDF CRUD Service).

Proporciona una instancia reutilizable de httpx.AsyncClient administrada
mediante el ciclo de vida (lifespan) de FastAPI, y un método de reenvío
de solicitudes (proxy) que preserva multipart/form-data, query parameters,
headers y cuerpo.

No levanta excepciones para respuestas funcionales de MS3 (400, 404, 413,
500, etc.): esas respuestas se devuelven tal cual para que la capa superior
las propague al cliente.
"""

from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import FastAPI

from src.config.config import Settings, get_settings


class MS3ClientError(Exception):
    """Error base de comunicación con MS3."""


class MS3ConnectionError(MS3ClientError):
    """No se pudo conectar con MS3 (ConnectError)."""


class MS3TimeoutError(MS3ClientError):
    """Tiempo de espera agotado comunicándose con MS3 (TimeoutException)."""


class MS3Client:
    """Wrapper reutilizable de httpx.AsyncClient hacia MS3.

    El cliente HTTP se crea de forma perezosa (primera solicitud) y se
    reutiliza durante todo el ciclo de vida de la aplicación. No se crea
    ninguna instancia durante la importación del módulo.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.MS3_URL,
                timeout=self._settings.MS3_TIMEOUT,
            )
        return self._client

    async def aclose(self) -> None:
        """Cierra el cliente HTTP y libera sus conexiones."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def proxy_request(
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
        """Reenvía una solicitud a MS3 y devuelve su respuesta HTTP.

        No convierte 4xx/5xx en excepciones: la respuesta se devuelve tal
        cual para que el gateway propague código, cuerpo y headers.
        """
        try:
            response = await self.client.request(
                method=method,
                url=path,
                params=params,
                headers=headers,
                content=content,
                data=data,
                json=json,
                files=files,
                timeout=timeout,
            )
        except httpx.ConnectError as exc:
            raise MS3ConnectionError("No se pudo conectar con MS3") from exc
        except httpx.TimeoutException as exc:
            raise MS3TimeoutError(
                "Tiempo de espera agotado comunicándose con MS3"
            ) from exc
        except httpx.RequestError as exc:
            raise MS3ClientError("Error de comunicación con MS3") from exc
        return response


# ---------------------------------------------------------------------------
# Ciclo de vida (lifespan) de FastAPI
# ---------------------------------------------------------------------------

_client_instance: Optional[MS3Client] = None


def get_ms3_client() -> MS3Client:
    """Retorna la instancia del cliente MS3, creándola si es necesario."""
    global _client_instance
    if _client_instance is None:
        settings = get_settings()
        _client_instance = MS3Client(settings)
    return _client_instance


async def setup_ms3_client() -> None:
    """Crea la instancia del cliente MS3 (se invoca al iniciar la app)."""
    get_ms3_client()


async def close_ms3_client() -> None:
    """Cierra el cliente HTTP de MS3 (se invoca al detener la app)."""
    global _client_instance
    if _client_instance is not None:
        await _client_instance.aclose()
        _client_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan de FastAPI: inicializa y cierra el cliente HTTP de MS3."""
    await setup_ms3_client()
    try:
        yield
    finally:
        await close_ms3_client()
