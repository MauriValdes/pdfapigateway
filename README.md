# MS1 — PDF API Gateway

Propósito del MS1
-----------------
El MS1 (PDF API Gateway) es el punto de entrada único para los clientes
externos de la arquitectura de microservicios de gestión de documentos PDF.
Recibe las solicitudes y las deriva al microservicio correspondiente
(actualmente MS3 – PDF CRUD Service), devolviendo las respuestas al cliente.

Los cinco endpoints proxy hacia MS3 ya están implementados:

- POST `/documents/` — crear/subir documento
- GET `/documents` — listar documentos
- GET `/documents/{document_id}` — consultar documento
- PATCH `/documents/{document_id}` — actualizar documento
- DELETE `/documents/{document_id}` — eliminar documento

Además expone `GET /` (información del servicio) y `GET /health` (healthcheck).

Responsabilidades
-----------------
- Ser el punto de entrada único para los clientes.
- Recibir solicitudes externas y enrutarlas al microservicio correspondiente (MS3).
- Devolver las respuestas al cliente sin modificar su contenido de negocio.
- Propagar los códigos de estado y cuerpos de respuesta de MS3 (incluidos 4xx y 5xx).
- Convertir errores de conexión con MS3 en HTTP 502 Bad Gateway.
- Convertir timeouts de MS3 en HTTP 504 Gateway Timeout.
- Eliminar cabeceras hop-by-hop (RFC 7230) antes de reenviar solicitudes y respuestas.
- No implementar lógica de negocio propia (eso corresponde a MS2 y MS3).
- No conectarse directamente a MongoDB.
- No invocar directamente a MS2 para el flujo normal de gestión de documentos
  (MS3 es quien orquesta la extracción con MS2).

Arquitectura
------------
El flujo de procesamiento es síncrono:

```
Cliente → MS1 (API Gateway)
                │
                │ HTTP proxy (httpx) — solo llama a MS3
                ▼
          MS3 (PDF CRUD Service)
                │
                ├─ HTTP (síncrono) → MS2 (extracción de texto PDF)
                │                      MS2 es stateless y no usa MongoDB
                │
                └─ MongoDB (persistencia de documentos)
                   Solo MS3 alcanza a MongoDB (vía db_net, red internal)
```

Relaciones entre servicios:

- **MS1 → MS3**: MS1 reenvía todas las solicitudes de documentos a MS3
  mediante `MS3_URL=http://crud-service:8000` (dentro de Docker).
- **MS3 → MS2**: MS3 invoca a MS2 para extraer texto de PDF mediante
  `EXTRACT_SERVICE_URL=http://extract-service:8000` (flujo síncrono dentro
  del procesamiento).
- **MS3 → MongoDB**: MS3 persiste documentos en MongoDB mediante `MONGO_URL`.
  Solo MS3 alcanza a MongoDB.
- **MS2 → (nada)**: MS2 es stateless, no utiliza MongoDB ni llama a ningún
  otro servicio.
- **MS1 → MongoDB / MS2**: MS1 no tiene conectividad implementada con ninguno
  de los dos; solo alcanza a MS3 mediante `integration_net`.

Nota de red: MS1 y MS2 comparten la red `integration_net`, por lo que existe
conectividad de red técnicamente posible entre ellos. Sin embargo, MS1 **no
implementa llamadas directas a MS2**: todas las operaciones de documentos se
derivan a MS3.

Integración actual
------------------
La integración entre MS1, MS2 y MS3 es **síncrona**. No hay colas de mensajes
ni procesamiento en segundo plano implementado.

Responsabilidades por microservicio
-----------------------------------
- **MS1 (pdfapigateway)**: recepción de solicitudes del cliente y proxy HTTP
  hacia MS3. No contiene lógica de negocio ni acceso a base de datos.
- **MS2 (pdfextractext)**: extracción de texto de PDF. Stateless, sin base de
  datos, expone `POST /extract`.
- **MS3 (pdfcrudservice)**: CRUD de documentos, persistencia en MongoDB y
  coordinación del procesamiento síncrono con MS2.

Tecnologías
-----------
- FastAPI (framework web)
- uvicorn (servidor ASGI)
- httpx (cliente HTTP asíncrono hacia MS3)
- pydantic-settings (configuración mediante variables de entorno)
- python-dotenv (carga de variables de entorno en desarrollo)
- pytest / pytest-asyncio (tests)

Estructura del proyecto
-----------------------
pdfapigateway/
├── Dockerfile
├── pyproject.toml
├── uv.lock
├── .env.example
├── README.md
└── src/
    ├── __init__.py
    ├── main.py              # App FastAPI, GET / y GET /health
    ├── config/
    │   ├── __init__.py
    │   └── config.py        # Configuración (pydantic-settings)
    ├── api/
    │   ├── __init__.py
    │   └── gateway.py       # Router de proxy hacia MS3
    ├── services/
    │   ├── __init__.py
    │   └── ms3_client.py    # Cliente HTTP reutilizable hacia MS3 (lifespan)
    └── exceptions/
        └── __init__.py      # Paquete de excepciones (vacío)

Endpoints
---------

| Método | Ruta | Descripción | Deriva a MS3 |
|--------|------|-------------|--------------|
| GET | `/` | Información del servicio | No (propio de MS1) |
| GET | `/health` | Healthcheck básico de MS1 | No (propio de MS1) |
| POST | `/documents/` | Crear/subir documento | `POST /documents/` |
| GET | `/documents` | Listar documentos | `GET /documents` |
| GET | `/documents/{document_id}` | Consultar documento | `GET /documents/{id}` |
| PATCH | `/documents/{document_id}` | Actualizar documento parcialmente | `PATCH /documents/{id}` |
| DELETE | `/documents/{document_id}` | Eliminar documento | `DELETE /documents/{id}` |

### Detalle de operaciones proxy

**POST `/documents/`** — Crear/subir documento
- Cuerpo: `multipart/form-data` con campo `file` (archivo PDF).
- Deriva a: `POST /documents/` de MS3.
- Códigos de estado propagados desde MS3: `201` (creado), `400` (archivo no PDF o vacío), `413` (archivo demasiado grande), `500` (error interno de MS3).
- Ejemplo con curl (PowerShell):
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8003/documents/" -Method Post -Form @{ file = Get-Item ".\document.pdf" }
  ```

**GET `/documents`** — Listar documentos
- Deriva a: `GET /documents` de MS3.
- Códigos de estado propagados: `200` (éxito), `500` (error interno de MS3).
- Ejemplo con curl (PowerShell):
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8003/documents" -Method Get
  ```

**GET `/documents/{document_id}`** — Consultar documento
- Deriva a: `GET /documents/{id}` de MS3.
- Códigos de estado propagados: `200` (encontrado), `404` (no encontrado), `500` (error interno de MS3).

**PATCH `/documents/{document_id}`** — Actualizar documento parcialmente
- Cuerpo: JSON con los campos a actualizar (status, content, page_count, error_message).
- Deriva a: `PATCH /documents/{id}` de MS3.
- Códigos de estado propagados: `200` (actualizado), `404` (no encontrado), `500` (error interno de MS3).

**DELETE `/documents/{document_id}`** — Eliminar documento
- Deriva a: `DELETE /documents/{id}` de MS3.
- Códigos de estado propagados: `204` (eliminado, sin cuerpo), `404` (no encontrado), `500` (error interno de MS3).

### Diferencia entre rutas `/documents` y `/documents/`

- `GET /documents` (sin slash final) se usa para listar documentos.
- `POST /documents/` (con slash final) se usa para crear un documento.

Esta distinción se mantiene exactamente como está implementada en MS3 y replicada en MS1. No modificar rutas ni contratos.

### Propagación de errores y cabeceras

- Las respuestas de MS3 (código de estado, cuerpo y Content-Type) se propagan tal cual al cliente, incluidos los errores `4xx` y `5xx`.
- Errores de conexión con MS3 (`httpx.ConnectError`) se convierten en **HTTP 502 Bad Gateway** con detalle "No se pudo conectar con el servicio de documentos".
- Timeouts de MS3 (`httpx.TimeoutException`) se convierten en **HTTP 504 Gateway Timeout** con detalle "El servicio de documentos no respondió a tiempo".
- Las cabeceras hop-by-hop (`connection`, `keep-alive`, `proxy-authenticate`, `proxy-authorization`, `te`, `trailer`, `transfer-encoding`, `upgrade`) se eliminan antes de reenviar la solicitud a MS3 y antes de devolver la respuesta al cliente. También se eliminan `host` y `content-length`.

Variables de entorno
--------------------
| Variable | Valor por defecto (ejemplo) | Descripción | Obligatoria |
|----------|----------------------------|-------------|-------------|
| `MS3_URL` | `http://localhost:8001` | URL base de MS3 (solo la base, sin `/documents`) | No |
| `MS3_TIMEOUT` | `40` | Timeout (s) para llamadas a MS3. Debe ser mayor que `EXTRACT_SERVICE_TIMEOUT` de MS3 (30s) | No |
| `APP_PORT` | `8000` | Puerto interno del contenedor MS1 | No |
| `HOST_PORT` | `8003` | Puerto publicado en el host | No |
| `LOG_LEVEL` | `INFO` | Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL) | No |

**Diferencia entre URL local y URL interna de Docker:**
- Ejecución local (fuera de Docker): `MS3_URL=http://localhost:8001` (puerto publicado de MS3 en el host).
- Dentro de Docker: `MS3_URL=http://crud-service:8000` (nombre del servicio + puerto interno de MS3).

No incluir credenciales ni secretos en este archivo. Las credenciales de MongoDB residen en el `.env` de la raíz de integración y solo se usan por MS3.

Archivo de ejemplo: `pdfapigateway/.env.example` (contiene todos los valores de ejemplo).

Instalación y ejecución
-----------------------

### Ejecución local (fuera de Docker)

Desde la carpeta `pdfapigateway/`:

```powershell
uv sync --dev
Copy-Item .env.example .env
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

La aplicación estará disponible en `http://localhost:8000`.
Endpoint de verificación: `GET http://localhost:8000/health`

### Ejecución de la integración con Docker Compose

Desde la carpeta raíz `Integracion/`:

```powershell
docker compose -f docker-compose.integration.yml up -d
```

MS1 estará publicado en el host en el puerto `8003` (contenedor interno `8000`).
Endpoint de verificación: `GET http://localhost:8003/health`

### Ejecución de pruebas

Desde la carpeta `pdfapigateway/`:

```powershell
uv run pytest -q
```

Resultado de referencia registrado el 09/11/2026: 43 pruebas aprobadas. Este
resultado puede cambiar con modificaciones futuras del código.

Puertos, redes y volúmenes
--------------------------

| Servicio | Puerto interno (contenedor) | Puerto publicado (host) |
|----------|----------------------------|-------------------------|
| MS1 (gateway-service) | 8000 | 8003 |
| MS3 (crud-service) | 8000 | 8001 |
| MS2 (extract-service) | 8000 | 8002 |
| MongoDB (db) | 27017 | 27018 |

### Redes Docker

| Red | Driver | Servicios | Nota |
|-----|--------|-----------|------|
| `integration_net` | bridge | MS1, MS3, MS2 | Comunicación síncrona entre servicios de aplicación |
| `db_net` | bridge (internal: true) | MongoDB, MS3 | Solo persistencia; MS1 y MS2 no alcanzan a MongoDB |

Nota: MS1 y MS2 comparten `integration_net`, por lo que existe conectividad de red técnicamente posible entre ellos. Sin embargo, MS1 no implementa llamadas directas a MS2.

### Volúmenes

| Volumen | Usado por | Propósito |
|---------|-----------|-----------|
| `mongo_data` | MongoDB (`db`) | Persistencia de datos de MongoDB (`/data/db`) |

MS1 no declara ningún volumen propio.

Healthcheck
-----------

`GET /health` devuelve el estado básico de MS1 (`{"status": "ok", "service": "ms1-gateway"}`). Es un healthcheck de **liveness** básico: solo verifica que el proceso de MS1 arranca y responde. **No verifica** la disponibilidad de MS3, MS2 ni MongoDB.

Parámetros del healthcheck en Docker (`docker-compose.integration.yml`):

| Parámetro | Valor |
|-----------|-------|
| `test` | `["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]` |
| `interval` | 10s |
| `timeout` | 5s |
| `retries` | 5 |
| `start_period` | 10s |

MS1 depende de que `crud-service` (MS3) esté sano antes de arrancar (`condition: service_healthy`).

Recursos Docker
---------------

Límites y reservas declarados en `docker-compose.integration.yml` para MS1:

| Recurso | Límite | Reserva |
|---------|--------|---------|
| CPU | 1 | 0.25 |
| Memoria | 256M | 64M |

Para referencia de los demás servicios en el mismo compose:

| Servicio | Límite CPU | Límite Memoria | Reserva CPU | Reserva Memoria |
|----------|------------|----------------|-------------|-----------------|
| MongoDB | 2 | 1G | 0.5 | 256M |
| MS3 | 2 | 512M | 0.5 | 128M |
| MS2 | No declara límites | No declara límites | — | — |
| MS1 | 1 | 256M | 0.25 | 64M |

MS2 (`extract-service`) no tiene bloque `deploy.resources` en la configuración actual de `docker-compose.integration.yml`, por tanto no declara límites ni reservas de CPU/memoria.

Notas
-----
- Este documento refleja el estado implementado de MS1 (etapas 9.1 a 10.9). Los endpoints proxy hacia MS3 ya están completos.
- No modificar MS2 ni MS3. No incorporar MongoDB, Redis, RabbitMQ, Kafka ni workers en MS1.
- No realizar commits ni push hasta aprobación correspondiente.
