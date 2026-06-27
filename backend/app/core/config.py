"""Application configuration using Pydantic Settings.

Loads configuration from environment variables and .env file.
Follows the explicit configuration principle from engineering guardrails.
"""

from functools import lru_cache
from typing import List

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments that require a real, non-default JWT secret.
# In these environments, the application MUST refuse to boot if the
# development-only default secret is still in use.
_PRODUCTION_ENVIRONMENTS: frozenset[str] = frozenset({"production", "staging"})

# The development-only default secret. Any value that starts with this
# prefix is treated as a placeholder and rejected in production-like
# environments.
_DEV_JWT_SECRET_PREFIX: str = "change-me-in-production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "LLM Forge"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    API_V1_PREFIX: str = "/api/v1"

    # Server
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    WORKERS: int = Field(default=1)

    # CORS
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    CORS_ALLOW_CREDENTIALS: bool = True

    # PostgreSQL
    POSTGRES_HOST: str = Field(default="postgres")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_USER: str = Field(default="llmforge")
    POSTGRES_PASSWORD: str = Field(default="llmforge")
    POSTGRES_DB: str = Field(default="llmforge")

    # Redis
    REDIS_HOST: str = Field(default="redis")
    REDIS_PORT: int = Field(default=6379)
    REDIS_DB: int = Field(default=0)

    # MinIO
    MINIO_ENDPOINT: str = Field(default="minio:9000")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin")
    MINIO_SECRET_KEY: str = Field(default="minioadmin")
    MINIO_SECURE: bool = Field(default=False)
    MINIO_BUCKET_DATASETS: str = Field(default="datasets")
    MINIO_BUCKET_ARTIFACTS: str = Field(default="artifacts")

    # Local storage (Phase 2 - Dataset Service)
    # Replaces MinIO for dataset file storage in this phase.
    # Files are stored under this directory, organized by dataset id /
    # version id. The directory is created on demand by the storage
    # service.
    LOCAL_STORAGE_PATH: str = Field(default="./local_storage")

    # Dataset upload limits (Phase 2)
    # Phase 2.1: tightened default to 50 MB to prevent OOM on large
    # uploads. Configurable via env (DATASET_MAX_FILE_SIZE_BYTES).
    DATASET_MAX_FILE_SIZE_BYTES: int = Field(default=50 * 1024 * 1024)  # 50 MB
    DATASET_MAX_RECORDS: int = Field(default=10_000_000)  # 10M records

    # MLflow
    MLFLOW_TRACKING_URI: str = Field(default="http://mlflow:5000")
    MLFLOW_ARTIFACT_ROOT: str = Field(default="s3://artifacts/mlflow")
    MLFLOW_S3_ENDPOINT_URL: str = Field(default="http://minio:9000")

    # Logging
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")

    # JWT / Authentication (Phase 1)
    JWT_SECRET_KEY: str = Field(
        default="change-me-in-production-this-is-a-development-only-secret-key"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60 * 24)  # 24 hours
    JWT_ISSUER: str = Field(default="llm-forge")
    JWT_AUDIENCE: str = Field(default="llm-forge-api")

    # Password policy (Phase 1)
    PASSWORD_MIN_LENGTH: int = Field(default=8)
    PASSWORD_MAX_LENGTH: int = Field(default=128)

    # Bcrypt rounds (Phase 1)
    BCRYPT_ROUNDS: int = Field(default=12)

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """Refuse to boot in production-like environments with a dev secret.

        The ``JWT_SECRET_KEY`` field has a development-only default so that
        local development and the test suite work out of the box. That
        default is a known public string and MUST NOT be used to sign real
        tokens. If the application is started with ``APP_ENV`` set to
        ``production`` or ``staging`` while the default secret is still in
        place, we raise ``ValueError`` so the process exits immediately
        rather than silently issuing tokens signed with a public secret.

        Returns:
            The validated ``Settings`` instance.

        Raises:
            ValueError: If a production-like environment is detected and
                ``JWT_SECRET_KEY`` still starts with the development-only
                prefix.
        """
        env = self.APP_ENV.strip().lower()
        if env in _PRODUCTION_ENVIRONMENTS:
            if self.JWT_SECRET_KEY.startswith(_DEV_JWT_SECRET_PREFIX):
                raise ValueError(
                    "JWT_SECRET_KEY is set to the development-only default "
                    f"(starts with '{_DEV_JWT_SECRET_PREFIX}'). This is "
                    f"not allowed when APP_ENV='{self.APP_ENV}'. Generate "
                    "a strong random secret (e.g. `openssl rand -hex 32`) "
                    "and set it in the environment before starting the "
                    "service."
                )
        return self

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL async URL."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url_sync(self) -> str:
        """Construct PostgreSQL sync URL for Alembic."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        """Construct Redis URL."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()
