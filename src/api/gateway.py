"""Router de proxy hacia MS3 (PDF CRUD Service).

Los endpoints de MS1 son transparentes: reciben solicitudes externas y las
derivan a MS3 sin transformar los DTO, sin validar el contenido del PDF,
sin calcular hashes y sin invocar directamente a MS2. Toda esa lógica
permanece en MS3.

Sigue el mismo patrón de enrutado que MS3:
- GET  /documents     → @router.get("")   (sin slash final)
- POST /documents/    → @router.post("/") (con slash final)

Starlette 1.10.0 no permite dos rutas independientes en el mismo path exacto
con métodos diferentes; al compilar el enrutador, solo uno de los métodos
sobrevive. Por ello se usan rutas con path distinto (con/sin slash final),
idéntico al enfoque de MS3.
"""

import logging
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from src.services.ms3_client import (
    MS3Client,
    MS3ClientError,
    MS3ConnectionError,
    MS3TimeoutError,
    get_ms3_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Cabeceras hop-by-hop que no se reenvían ni al cliente ni a MS3 (RFC 7230).
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _clean_forward_headers(headers: dict[str, str]) -> dict[str, str]:
    """Elimina cabeceras de transporte y de host antes de reenviar a MS3."""
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
        and key.lower() not in {"host", "content-length"}
    }


def _clean_response_headers(headers: dict[str, str]) -> dict[str, str]:
    """Elimina cabeceras de transporte antes de devolver al cliente."""
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
        and key.lower() != "content-length"
    }


def _forward_response(response) -> Response:
    """Construye una respuesta de FastAPI preservando código, cuerpo y Content-Type."""
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=_clean_response_headers(dict(response.headers)),
        media_type=response.headers.get("content-type"),
    )


def _raise_transport_error(exc: MS3ClientError) -> None:
    """Convierte errores de transporte en respuestas HTTP controladas del Gateway."""
    if isinstance(exc, MS3TimeoutError):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="El servicio de documentos no respondió a tiempo",
        )
    if isinstance(exc, MS3ConnectionError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo conectar con el servicio de documentos",
        )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Error al comunicarse con el servicio de documentos",
    )


# ---------------------------------------------------------------------------
# Endpoints proxy
# ---------------------------------------------------------------------------


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Subir y registrar un PDF",
    description=(
        "Recibe un archivo PDF en multipart/form-data (campo 'file') y lo "
        "deriva a MS3 para su registro y extracción de texto."
    ),
)
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    client: MS3Client = get_ms3_client()
    try:
        files = {
            "file": (
                file.filename or "document.pdf",
                file.file,
                file.content_type or "application/pdf",
            )
        }
        response = await client.proxy_request(
            "POST",
            "/documents/",
            headers=_clean_forward_headers(dict(request.headers)),
            files=files,
        )
    except MS3ClientError as exc:
        _raise_transport_error(exc)
    return _forward_response(response)


@router.get(
    "",
    summary="Listar documentos",
    description="Devuelve la lista de documentos registrados en MS3.",
)
async def list_documents():
    client: MS3Client = get_ms3_client()
    try:
        response = await client.proxy_request(
            "GET",
            "/documents",
        )
    except MS3ClientError as exc:
        _raise_transport_error(exc)
    return _forward_response(response)


@router.get(
    "/{document_id}",
    summary="Obtener un documento por ID",
    description="Devuelve el documento identificado por document_id.",
)
async def get_document(document_id: str, request: Request):
    client: MS3Client = get_ms3_client()
    try:
        response = await client.proxy_request(
            "GET",
            f"/documents/{document_id}",
            headers=_clean_forward_headers(dict(request.headers)),
        )
    except MS3ClientError as exc:
        _raise_transport_error(exc)
    return _forward_response(response)


@router.patch(
    "/{document_id}",
    summary="Actualizar un documento parcialmente",
    description="Envía los campos a actualizar (JSON) a MS3 sin modificar su estructura.",
)
async def update_document(document_id: str, request: Request):
    client: MS3Client = get_ms3_client()
    body = await request.json()
    try:
        response = await client.proxy_request(
            "PATCH",
            f"/documents/{document_id}",
            json=body,
            headers=_clean_forward_headers(dict(request.headers)),
        )
    except MS3ClientError as exc:
        _raise_transport_error(exc)
    return _forward_response(response)


@router.delete(
    "/{document_id}",
    summary="Eliminar un documento",
    description="Elimina el documento identificado por document_id (204 sin cuerpo).",
)
async def delete_document(document_id: str, request: Request):
    client: MS3Client = get_ms3_client()
    try:
        response = await client.proxy_request(
            "DELETE",
            f"/documents/{document_id}",
            headers=_clean_forward_headers(dict(request.headers)),
        )
    except MS3ClientError as exc:
        _raise_transport_error(exc)
    return _forward_response(response)
