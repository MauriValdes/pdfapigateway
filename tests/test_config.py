"""Pruebas de configuración centralizada de MS1 (src/config/config.py).

Todos los tests son aislados: limpian la caché de `get_settings` y restauran
el entorno mediante `monkeypatch`, por lo que no afectan a otros tests.
"""

import pytest
from pydantic import ValidationError

from src.config.config import Settings, get_settings


def _reset_settings() -> None:
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clear_settings_cache():
    _reset_settings()
    yield
    _reset_settings()


def test_default_values(monkeypatch: pytest.MonkeyPatch):
    for var in ("MS3_URL", "MS3_TIMEOUT", "LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)
    _reset_settings()
    settings = get_settings()
    assert Settings.model_config.get("env_file") is None
    assert settings.MS3_URL == "http://localhost:8001"
    assert settings.MS3_TIMEOUT == 40
    assert settings.LOG_LEVEL == "INFO"
    assert "APP_PORT" not in Settings.model_fields
    assert "HOST_PORT" not in Settings.model_fields


def test_custom_env_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MS3_URL", "http://crud-service:8000")
    monkeypatch.setenv("MS3_TIMEOUT", "60")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    _reset_settings()
    settings = get_settings()
    assert settings.MS3_URL == "http://crud-service:8000"
    assert settings.MS3_TIMEOUT == 60
    assert settings.LOG_LEVEL == "DEBUG"


def test_timeout_zero_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MS3_TIMEOUT", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_timeout_negative_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MS3_TIMEOUT", "-5")
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_url_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MS3_URL", "not-a-url")
    with pytest.raises(ValidationError):
        Settings()


def test_log_level_normalized_to_uppercase(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOG_LEVEL", "info")
    _reset_settings()
    settings = get_settings()
    assert settings.LOG_LEVEL == "INFO"


def test_log_level_debug_normalized(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOG_LEVEL", "Debug")
    _reset_settings()
    settings = get_settings()
    assert settings.LOG_LEVEL == "DEBUG"


def test_invalid_log_level_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOG_LEVEL", "TRACE")
    with pytest.raises(ValidationError):
        Settings()
