"""Configuración centralizada del microservicio MS1 (PDF API Gateway).

Utiliza Pydantic Settings para leer variables de entorno y, en desarrollo,
un archivo `.env`. Todas las validaciones se declaran como validadores de
campo para garantizar valores correctos antes de que la aplicación arranque.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación MS1."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MS3_URL: str = "http://localhost:8001"
    MS3_TIMEOUT: int = 40
    APP_PORT: int = 8000
    HOST_PORT: int = 8003
    LOG_LEVEL: str = "INFO"

    @field_validator("MS3_URL")
    @classmethod
    def _validate_ms3_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError(
                "MS3_URL debe ser una URL válida que comience con http:// o https://"
            )
        return value

    @field_validator("MS3_TIMEOUT")
    @classmethod
    def _validate_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MS3_TIMEOUT debe ser mayor que cero")
        return value

    @field_validator("APP_PORT", "HOST_PORT")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("El puerto debe estar entre 1 y 65535")
        return value

    @field_validator("LOG_LEVEL")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in valid_levels:
            raise ValueError(
                f"LOG_LEVEL debe ser uno de: {', '.join(sorted(valid_levels))}"
            )
        return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna la configuración cargada, cacheada para evitar instancias duplicadas."""
    return Settings()
