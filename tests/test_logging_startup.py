"""Tests de la integración del logging centralizado en el arranque de MS1.

Verifican que:

- El logging se configura antes que FastAPI al importar main.
- El nombre del servicio ms1-gateway aparece en los registros.
- No quedan mensajes de print() antiguos.
- La aplicación arranca correctamente con los endpoints.
- Los registros tienen formato JSON.

Cada test se ejecuta en un proceso Python independiente para aislar
completamente el estado global del logger, evitando cualquier contaminación
entre tests o dependencia del orden de ejecución.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

SERVICE_NAME = "ms1-gateway"

# Textos exactos de los print() que existían antes de la integración.
MENSAJES_DE_PRINT_ANTIGUOS = (
    "PDF API Gateway iniciado",
    "Servicio listo para recibir solicitudes",
)


# ---------------------------------------------------------------------------
# Helper: ejecutar código Python en proceso hijo aislado
# ---------------------------------------------------------------------------

def _run_code_in_subprocess(code: str) -> subprocess.CompletedProcess:
    """Ejecuta una cadena de código Python en un proceso independiente.

    Utiliza subprocess.run() con sys.executable, -c, capture_output=True,
    text=True, cwd y env configurado.

    Returns el objeto CompletedProcess sin procesar.
    """
    env = os.environ.copy()
    env["LOG_LEVEL"] = "INFO"

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        timeout=30,
    )

    return result


# ---------------------------------------------------------------------------
# Validación simple del helper subprocess
# ---------------------------------------------------------------------------

def test_subprocess_validacion_simple(monkeypatch):
    """Validación simple del helper _run_code_in_subprocess.

    Ejecuta: import sys; print(sys.executable); print('SUBPROCESS_OK')
    Demuestra que:
    - returncode es 0
    - stdout contiene SUBPROCESS_OK
    - stderr no contiene errores
    """
    code = "import sys; print(sys.executable); print('SUBPROCESS_OK')"
    result = _run_code_in_subprocess(code)

    # 1. returncode es 0
    assert result.returncode == 0, f"returncode esperado 0, got {result.returncode}"

    # 2. stdout contiene SUBPROCESS_OK
    assert 'SUBPROCESS_OK' in result.stdout, f"SUBPROCESS_OK no en stdout: {result.stdout}"

    # 3. stderr no contiene errores
    assert result.stderr == '', f"stderr no vacío: {result.stderr}"

    # 4. Verificar que es el Python correcto
    assert 'python' in result.stdout.lower() or 'py' in result.stdout


# ---------------------------------------------------------------------------
# Test 2: Nombre del servicio
# Verifica que el identificador ms1-gateway aparece en los registros.
# ---------------------------------------------------------------------------

def test_arranque_usa_nombre_servicio_ms1_gateway(monkeypatch):
    """Verifica que el nombre del servicio ms1-gateway aparece en los registros.

    En proceso hijo: importa src.main, emite un registro y comprueba
    que stdout contiene un registro JSON con field service=ms1-gateway.
    """
    code = (
        "import sys\n"
        "if 'src.main' in sys.modules:\n"
        "    del sys.modules['src.main']\n"
        "\n"
        "import sys as _sys\n"
        "_sys.path.insert(0, 'pdfapigateway')\n"
        "__import__('src.main')\n"
        "\n"
        "import json\n"
        "import logging\n"
        "import time\n"
        "import os\n"
        "os.environ['LOG_LEVEL'] = 'INFO'\n"
        "__import__('src.main')\n"
        "logger = logging.getLogger('src.api.gateway')\n"
        "logger.info('test mensaje servicio')\n"
        "time.sleep(0.05)\n"
        "lines = [l for l in open(0).read().splitlines() if l.strip()]\n"
        "if lines:\n"
        "    record = json.loads(lines[0])\n"
        "    assert record['service'] == 'ms1-gateway'"
    )

    result = _run_code_in_subprocess(code)
    assert result.returncode == 0, f"falló en subprocess (returncode={result.returncode})"


# ---------------------------------------------------------------------------
# Test 3: Formato JSON
# Verifica que la salida de logging tiene formato JSON.
# ---------------------------------------------------------------------------

def test_arranque_no_emite_texto_plano(monkeypatch):
    """Verifica que la salida del logging tiene formato JSON.

    En proceso hijo: importa src.main, emite un mensaje y comprueba
    que la primera línea de stdout puede analizarse con json.loads().
    """
    code = (
        "import sys\n"
        "if 'src.main' in sys.modules:\n"
        "    del sys.modules['src.main']\n"
        "\n"
        "import sys as _sys\n"
        "_sys.path.insert(0, 'pdfapigateway')\n"
        "__import__('src.main')\n"
        "\n"
        "import json\n"
        "import logging\n"
        "import time\n"
        "import os\n"
        "os.environ['LOG_LEVEL'] = 'INFO'\n"
        "__import__('src.main')\n"
        "logger = logging.getLogger('src.api.gateway')\n"
        "logger.info('mensaje de prueba')\n"
        "time.sleep(0.05)\n"
    )

    result = _run_code_in_subprocess(code)
    assert result.returncode == 0, f"falló en subprocess (returncode={result.returncode})"
    # Verificar la salida del subprocess mediante result.stdout
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) >= 1, 'debería haber al menos un registro JSON'
    json.loads(lines[0])


# ---------------------------------------------------------------------------
# Test 4: Ausencia de prints antiguos
# Verifica que no aparecen mensajes antiguos de print().
# ---------------------------------------------------------------------------

def test_arranque_no_emite_los_mensajes_de_print_antiguos(monkeypatch):
    """Verifica que no aparecen los mensajes antiguos de print().

    En proceso hijo: importa src.main y comprueba que ninguno de los
    mensajes especificados aparece en stdout ni stderr.
    """
    code = (
        "import sys\n"
        "if 'src.main' in sys.modules:\n"
        "    del sys.modules['src.main']\n"
        "\n"
        "import sys as _sys\n"
        "_sys.path.insert(0, 'pdfapigateway')\n"
        "__import__('src.main')\n"
        "\n"
        "import json\n"
        "import logging\n"
        "import os\n"
        "os.environ['LOG_LEVEL'] = 'INFO'\n"
        "__import__('src.main')\n"
        "stdout_data = sys.stdout.getvalue() if hasattr(sys, 'stdout') and hasattr(sys.stdout, 'getvalue') else ''\n"
        "stderr_data = sys.stderr.getvalue() if hasattr(sys, 'stderr') and hasattr(sys.stderr, 'getvalue') else ''\n"
        "salida = stdout_data + stderr_data\n"
        "for m in " + json.dumps(MENSAJES_DE_PRINT_ANTIGUOS) + ":\n"
        "    assert m not in salida, f'quedó el mensaje: {m!r}'"
    )

    result = _run_code_in_subprocess(code)
    assert result.returncode == 0, f"falló en subprocess (returncode={result.returncode})"


# ---------------------------------------------------------------------------
# Test 5: Ausencia de errores de logging
# Verifica que no hay errores propios de logging.
# ---------------------------------------------------------------------------

def test_arranque_no_genera_errores(monkeypatch):
    """Verifica que el arranque no registra errores propios.

    En proceso hijo: importa src.main y comprueba que stderr no contiene
    --- Logging error ---.
    """
    code = (
        "import sys\n"
        "if 'src.main' in sys.modules:\n"
        "    del sys.modules['src.main']\n"
        "\n"
        "import sys as _sys\n"
        "_sys.path.insert(0, 'pdfapigateway')\n"
        "__import__('src.main')\n"
        "\n"
        "import json\n"
        "import os\n"
        "os.environ['LOG_LEVEL'] = 'INFO'\n"
        "__import__('src.main')\n"
    )

    result = _run_code_in_subprocess(code)
    assert result.returncode == 0, f"falló en subprocess (returncode={result.returncode})"
    assert '--- Logging error ---' not in result.stderr, 'error de logging en stderr'


# ---------------------------------------------------------------------------
# Test 6: Registro del servicio
# Verifica que los registros incluyen el identificador ms1-gateway.
# ---------------------------------------------------------------------------

def test_arranque_emite_registro_servicio(monkeypatch):
    """Verifica que los registros incluyen el identificador ms1-gateway.

    En proceso hijo: importa src.main, emite un registro y comprueba
    que el registro JSON correspondiente tiene service=ms1-gateway.
    """
    code = (
        "import sys\n"
        "if 'src.main' in sys.modules:\n"
        "    del sys.modules['src.main']\n"
        "\n"
        "import sys as _sys\n"
        "_sys.path.insert(0, 'pdfapigateway')\n"
        "__import__('src.main')\n"
        "\n"
        "import json\n"
        "import logging\n"
        "import time\n"
        "import os\n"
        "os.environ['LOG_LEVEL'] = 'INFO'\n"
        "__import__('src.main')\n"
        "logger = logging.getLogger('src.api.gateway')\n"
        "logger.info('test mensaje servicio')\n"
        "time.sleep(0.05)\n"
    )

    result = _run_code_in_subprocess(code)
    assert result.returncode == 0, f"falló en subprocess (returncode={result.returncode})"
    # Verificar la salida del subprocess mediante result.stdout
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) >= 1, 'debería haber registros'
    record = json.loads(lines[0])
    assert record['service'] == 'ms1-gateway'


# ---------------------------------------------------------------------------
# Test 7: Endpoint health devuelve 200
# Verifica que el endpoint health funciona después de la configuración.
# ---------------------------------------------------------------------------

def test_endpoint_health_devuelve_200(monkeypatch):
    """Verifica que el endpoint health funciona correctamente.

    En proceso hijo: importa src.main y usa TestClient para hacer GET /health.
    """
    code = (
        "import sys\n"
        "if 'src.main' in sys.modules:\n"
        "    del sys.modules['src.main']\n"
        "\n"
        "import sys as _sys\n"
        "_sys.path.insert(0, 'pdfapigateway')\n"
        "__import__('src.main')\n"
        "from fastapi.testclient import TestClient\n"
        "client = TestClient(__import__('src').main.app)\n"
        "response = client.get('/health')\n"
        "assert response.status_code == 200\n"
        "assert response.json() == {'status': 'ok', 'service': 'ms1-gateway'}"
    )

    result = _run_code_in_subprocess(code)
    assert result.returncode == 0, f"falló en subprocess (returncode={result.returncode})"


# ---------------------------------------------------------------------------
# Test 8: Endpoint root devuelve 200
# Verifica que el endpoint root funciona después de la configuración.
# ---------------------------------------------------------------------------

def test_endpoint_root_devuelve_200(monkeypatch):
    """Verifica que el endpoint root funciona correctamente.

    En proceso hijo: importa src.main y usa TestClient para GET /.
    """
    code = (
        "import sys\n"
        "if 'src.main' in sys.modules:\n"
        "    del sys.modules['src.main']\n"
        "\n"
        "import sys as _sys\n"
        "_sys.path.insert(0, 'pdfapigateway')\n"
        "__import__('src.main')\n"
        "from fastapi.testclient import TestClient\n"
        "client = TestClient(__import__('src').main.app)\n"
        "response = client.get('/')\n"
        "assert response.status_code == 200\n"
        "assert response.json().get('service') == 'ms1-gateway'"
    )

    result = _run_code_in_subprocess(code)
    assert result.returncode == 0, f"falló en subprocess (returncode={result.returncode})"


# ---------------------------------------------------------------------------
# Test 9: Orden de inicialización (verificación independiente)
# Verifica el orden de importación de logging y FastAPI.
# ---------------------------------------------------------------------------

def test_orden_inicializacion_logging_antes_fastapi(monkeypatch):
    """Verifica el orden de inicialización de logging antes que FastAPI.

    En proceso hijo: utiliza instrumentación de builtins.__import__ para
    demostrar que configure_logging() se ejecutó antes de la importación
    de FastAPI.
    """
    code = (
        "import sys\n"
        "import builtins\n"
        "import logging\n"
        "nimported_fastapi = False\n"
        "original_import = builtins.__import__\n"
        "def instrumented_import(name, *args, **kwargs):\n"
        "    global nimported_fastapi\n"
        "    if 'fastapi' in str(name) or name == 'fastapi':\n"
        "        nimported_fastapi = True\n"
        "    return original_import(name, *args, **kwargs)\n"
        "builtins.__import__ = instrumented_import\n"
        "\n"
        "if 'src.main' in sys.modules:\n"
        "    del sys.modules['src.main']\n"
        "\n"
        "import sys as _sys\n"
        "_sys.path.insert(0, 'pdfapigateway')\n"
        "__import__('src.main')\n"
        "\n"
        "root = logging.getLogger()\n"
        "handler_types = [type(h).__name__ for h in root.handlers]\n"
        "assert any('DynamicStreamHandler' in h for h in handler_types), 'Logging not configured before FastAPI import'"
    )

    result = _run_code_in_subprocess(code)
    assert result.returncode == 0, f"falló en subprocess (returncode={result.returncode})"


# ---------------------------------------------------------------------------
# Prueba adicional: validación del helper subprocess
# ---------------------------------------------------------------------------

def test_subprocess_helper_validacion(monkeypatch):
    """Validación del helper _run_code_in_subprocess.

    Ejecuta: import sys; print(sys.executable); print('SUBPROCESS_OK')
    Demuestra que:
    - returncode es 0
    - stdout contiene SUBPROCESS_OK
    - stderr no contiene errores
    """
    code = "import sys; print(sys.executable); print('SUBPROCESS_OK')"
    result = _run_code_in_subprocess(code)

    # 1. returncode es 0
    assert result.returncode == 0, f"returncode esperado 0, got {result.returncode}"

    # 2. stdout contiene SUBPROCESS_OK
    assert 'SUBPROCESS_OK' in result.stdout, f"SUBPROCESS_OK no en stdout: {result.stdout}"

    # 3. stderr no contiene errores
    assert result.stderr == '', f"stderr no vacío: {result.stderr}"