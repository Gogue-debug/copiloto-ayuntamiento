"""
Configuración de la aplicación via pydantic-settings.
Lee variables desde .env o entorno del sistema.
"""
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Aplicación
    # -------------------------------------------------------------------------
    app_env: Literal["development", "staging", "production"] = "development"
    app_secret_key: str = "changeme_dev_secret_key_min_32_chars"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "INFO"
    app_allowed_origins: list[str] = ["http://localhost:3000"]

    @field_validator("app_allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # -------------------------------------------------------------------------
    # Base de datos
    # -------------------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://copiloto:changeme_dev@localhost:5432/copiloto"

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    redis_celery_url: str = "redis://localhost:6379/1"

    # -------------------------------------------------------------------------
    # Anthropic / Claude
    # -------------------------------------------------------------------------
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    claude_timeout_chat: int = 30       # segundos para chat ciudadano
    claude_timeout_batch: int = 120     # segundos para OCR y resoluciones

    # -------------------------------------------------------------------------
    # MinIO / Storage
    # -------------------------------------------------------------------------
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "changeme_dev"
    minio_bucket: str = "copiloto"
    minio_secure: bool = False

    # -------------------------------------------------------------------------
    # Keycloak
    # -------------------------------------------------------------------------
    keycloak_url: AnyHttpUrl = "http://localhost:8080"  # type: ignore[assignment]
    keycloak_realm: str = "copiloto"
    keycloak_client_id: str = "copiloto-api"
    keycloak_client_secret: str = "changeme_dev"

    # -------------------------------------------------------------------------
    # Google Cloud Document AI (OCR)
    # -------------------------------------------------------------------------
    google_cloud_project: str = ""
    document_ai_processor_id: str = ""
    document_ai_location: str = "eu"

    # -------------------------------------------------------------------------
    # WhatsApp Business API
    # -------------------------------------------------------------------------
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = "changeme_webhook_verify_token"
    whatsapp_api_version: str = "v19.0"

    # -------------------------------------------------------------------------
    # Email / SMTP
    # -------------------------------------------------------------------------
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@copiloto.es"
    smtp_tls: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def debug(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
