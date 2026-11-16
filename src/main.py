"""Aplicación FastAPI para MS1 (PDF API Gateway).

Orden de inicialización (deliberado):

1. Se importa la configuración (pydantic-settings) y el módulo de
   logging centralizado (solo biblioteca estándar).
2. Se configura el logging con configure_logging() ANTES de importar
   FastAPI y el resto de dependencias de la aplicación. Esto es necesario
   porque logging.config.dictConfig() cierra los handlers registrados en el
   proceso: si se ejecutara más tarde, cerraría los handlers que hubiera
   registrado cualquier integración externa (APM, OpenTelemetry, etc.).
3. Recién entonces se importan FastAPI y los módulos de la aplicación, que
   ya quedan con el logging configurado.

A partir de este punto, toda la salida de logs del servicio es JSON por
stdout/stderr y no existe ningún mensaje de texto plano.
"""

import logging
from contextlib import asynccontextmanager

from src.config.config import get_settings
from src.core.logging_config import configure_logging

# Nombre del servicio: identifica el origen de cada registro.
SERVICE_NAME = "ms1-gateway"

# 1) Logging centralizado: formato JSON, stdout/stderr y nivel desde Settings.
configure_logging(SERVICE_NAME, level=get_settings().LOG_LEVEL)

# 2) Dependencias de la aplicación (importadas con el logging ya configurado).
from fastapi import FastAPI  # noqa: E402

from src.api.gateway import router as documents_router  # noqa: E402
from src.services.ms3_client import lifespan  # noqa: E402

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