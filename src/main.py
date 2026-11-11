"""Aplicación FastAPI para MS1 (PDF API Gateway).

Punto de entrada único para la gestión de documentos PDF. Deriva las
solicitudes hacia MS3 (PDF CRUD Service) mediante el router de proxy
implementado en src.api.gateway.

La lógica de negocio permanece en MS3; este gateway no valida PDFs, no
calcula hashes, no consulta MongoDB y no invoca directamente a MS2.
"""

from fastapi import FastAPI

from src.api.gateway import router as documents_router
from src.services.ms3_client import lifespan

app = FastAPI(
    title="PDF API Gateway (MS1)",
    version="0.1.0",
    description="Punto de entrada único para la gestión de documentos PDF.",
    lifespan=lifespan,
)

# Añadir las rutas del router directamente (evitando el envoltorio
# _IncludedRouter de include_router que puede interferir con el matching
# de rutas cuando hay GET y POST en paths similares).
app.include_router(documents_router)


@app.get("/health", status_code=200, summary="Healthcheck del gateway")
async def health():
    """Healthcheck básico del gateway."""
    return {"status": "ok", "service": "ms1-gateway"}


@app.get("/", status_code=200, summary="Información del servicio")
async def root():
    """Endpoint raíz para verificar que el servicio arranca."""
    return {
        "service": "ms1-gateway",
        "message": "PDF API Gateway - proxy hacia MS3",
    }
