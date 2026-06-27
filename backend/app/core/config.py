"""Application configuration loaded from environment variables and .env."""

from functools import lru_cache
from typing import List

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Production-like environments require a non-default JWT secret.
_PRODUCTION_ENVIRONMENTS: frozenset[str] = frozenset({"production", "staging"})

# Development-only default secret prefix; values starting with this
# are rejected when APP_ENV is production-like.
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

    # MinIO (legacy; not used by LocalStorageService)
    MINIO_ENDPOINT: str = Field(default="minio:9000")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin")
    MINIO_SECRET_KEY: str = Field(default="minioadmin")
    MINIO_SECURE: bool = Field(default=False)
    MINIO_BUCKET_DATASETS: str = Field(default="datasets")
    MINIO_BUCKET_ARTIFACTS: str = Field(default="artifacts")

    # Local storage. Files live under this root, organized by
    # dataset/version. The directory is created on demand.
    LOCAL_STORAGE_PATH: str = Field(default="./local_storage")

    # Dataset upload limits
    DATASET_MAX_FILE_SIZE_BYTES: int = Field(default=50 * 1024 * 1024)  # 50 MB
    DATASET_MAX_RECORDS: int = Field(default=10_000_000)  # 10M records

    # MLflow (legacy)
    MLFLOW_TRACKING_URI: str = Field(default="http://mlflow:5000")
    MLFLOW_ARTIFACT_ROOT: str = Field(default="s3://artifacts/mlflow")
    MLFLOW_S3_ENDPOINT_URL: str = Field(default="http://minio:9000")

    # Logging
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")

    # JWT
    JWT_SECRET_KEY: str = Field(
        default="change-me-in-production-this-is-a-development-only-secret-key"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60 * 24)  # 24 hours
    JWT_ISSUER: str = Field(default="llm-forge")
    JWT_AUDIENCE: str = Field(default="llm-forge-api")

    # Password policy
    PASSWORD_MIN_LENGTH: int = Field(default=8)
    PASSWORD_MAX_LENGTH: int = Field(default=128)

    BCRYPT_ROUNDS: int = Field(default=12)

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        # Refuse to boot in production-like environments with the dev
        # default secret in place — that string is a known public value
        # and must never be used to sign real tokens.
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
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
