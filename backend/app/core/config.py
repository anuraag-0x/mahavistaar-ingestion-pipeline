"""
Application Settings & Configuration.
Loads from the root .env file with full type validation and sensible defaults.
"""

import os
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Root .env path (one directory above backend/)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App Basics
    APP_NAME: str = "MahaVistaar Backend"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOCAL_ONLY_MODE: bool = True
    DISABLE_PROD_SETTING: bool = True
    # The collection production publishing writes to. Empty means the stack has
    # no production target, and the prod gates are hidden rather than offering
    # an approval that cannot be carried out.
    QDRANT_PROD_COLLECTION_NAME: str = ""
    DEFAULT_INSTANCE: str = "mh"

    # Ports
    API_HOST_PORT: int = 8002

    # PostgreSQL Database Configuration
    POSTGRES_HOST: str = Field(default="localhost", alias="POSTGRES_HOST")
    POSTGRES_PORT: int = Field(default=5432, alias="POSTGRES_PORT")
    POSTGRES_USER: str = Field(default="docs_pipeline", alias="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(default="Kenpath@123", alias="POSTGRES_PASSWORD")
    POSTGRES_DB: str = Field(default="docs-pipeline", alias="POSTGRES_DB")
    DATABASE_URL: Optional[str] = None
    ASYNC_DATABASE_URL: Optional[str] = None

    # Master Catalog Postgres (can share or use separate DB)
    MASTER_CATALOG_PG_HOST: Optional[str] = None
    MASTER_CATALOG_PG_PORT: int = 5432
    MASTER_CATALOG_PG_DB: str = "mahavistaar"
    MASTER_CATALOG_PG_USER: str = "docs_pipeline"
    MASTER_CATALOG_PG_PASSWORD: str = "Kenpath@123"
    MASTER_CATALOG_PG_SSLMODE: str = "disable"

    # Redis (AI Layer snapshot sync)
    AI_LAYER_REDIS_HOST: Optional[str] = None
    AI_LAYER_REDIS_PORT: int = 6379
    AI_LAYER_REDIS_DB: int = 0
    AI_LAYER_REDIS_PASSWORD: Optional[str] = None
    MASTER_CATALOG_REDIS_TTL_SECONDS: int = 172800

    # Storage (MinIO)
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET: str = "documents"
    MINIO_SECURE: bool = False

    # Vector Store (Qdrant)
    VECTOR_BACKEND: str = "qdrant"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = ""
    QDRANT_COLLECTION_NAME: str = "local-documents-index"
    QDRANT_TIMEOUT_SECONDS: int = 30

    # Standalone Hugging Face Embedding Service
    HF_EMBEDDING_SERVICE_URL: str = "http://localhost:8021"
    EMBEDDING_MODEL_NAME: str = "intfloat/multilingual-e5-large"
    EMBEDDING_DIMENSION: int = 1024

    # OCR Settings
    OCR_PROVIDER: str = "mistral"
    OCR_MODEL: str = "mistral-ocr-latest"
    MISTRAL_API_KEY: str = ""
    MISTRAL_OCR_API_URL: str = "https://api.mistral.ai/v1/ocr"
    OCR_SEGMENT_PAGES: int = 20
    OCR_REQUEST_TIMEOUT_SECONDS: int = 300
    # LLM Settings
    LLM_PROVIDER: str = "vllm"
    LLM_AGRINET_MODEL_NAME: str = "agrinet-model"
    VLLM_AGRINET_MODEL_URL: str = "http://205.147.102.109:8082/v1"
    VLLM_AGRINET_MAX_CONCURRENT: int = 100
    CEREBRAS_API_KEY: str = ""
    CEREBRAS_BASE_URL: str = "https://api.cerebras.ai/v1"
    CEREBRAS_MODEL: str = "gemma-4-31b"
    TRANSLATION_PAGE_CONCURRENCY: int = 1
    TRANSLATION_MAX_RETRIES: int = 6
    TRANSLATION_RETRY_BASE_SECONDS: float = 2.0
    TRANSLATION_SCRIPT_GATE_ENABLED: bool = True
    TRANSLATION_SCRIPT_MIN_CHARS: int = 15
    TRANSLATION_SCRIPT_MIN_RATIO: float = 0.05

    # Chunking Settings
    CHUNKING_PROVIDER: str = "deterministic"
    CHUNKING_MODEL: str = "deterministic"
    CHUNKING_TARGET_CHUNK_TOKENS: int = 450
    CHUNKING_MAX_CHUNK_TOKENS: int = 450
    CHUNKING_MIN_CHUNK_TOKENS: int = 100
    CHUNKING_OVERLAP_TOKENS: int = 128
    CHUNKING_MAX_PAGES_PER_CHUNK: int = 8
    CHUNKING_PAGE_WINDOW_SIZE: int = 8

    # Auth & Keycloak
    AUTH_DISABLED: bool = False
    KEYCLOAK_BASE_URL: str = "http://localhost:8181/auth"
    KEYCLOAK_REALM: str = "docs-pipeline"
    KEYCLOAK_ISSUER: str = "http://localhost:8181/auth/realms/docs-pipeline"
    KEYCLOAK_JWKS_URL: str = "http://localhost:8181/auth/realms/docs-pipeline/protocol/openid-connect/certs"
    KEYCLOAK_AUDIENCE: Optional[str] = None
    KEYCLOAK_ADMIN_BASE_URL: str = "http://localhost:8181/auth"
    KEYCLOAK_ADMIN_REALM: str = "docs-pipeline"
    KEYCLOAK_ADMIN_TOKEN_REALM: str = "master"
    KEYCLOAK_ADMIN_USERNAME: str = "admin"
    KEYCLOAK_ADMIN_PASSWORD: str = ""
    KEYCLOAK_CLIENT_ID: str = "docs-pipeline-api"
    KEYCLOAK_CLIENT_SECRET: Optional[str] = ""
    KEYCLOAK_OTP_CLIENT_ID: str = "docs-pipeline-ui"
    KEYCLOAK_TOKEN_URL: Optional[str] = None

    # CORS & Security
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        user = quote(self.POSTGRES_USER, safe="")
        password = quote(self.POSTGRES_PASSWORD, safe="")
        database = quote(self.POSTGRES_DB, safe="")
        return (
            f"postgresql://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{database}"
        )

    @property
    def async_database_url(self) -> str:
        if self.ASYNC_DATABASE_URL:
            return self.ASYNC_DATABASE_URL
        user = quote(self.POSTGRES_USER, safe="")
        password = quote(self.POSTGRES_PASSWORD, safe="")
        database = quote(self.POSTGRES_DB, safe="")
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{database}"
        )


settings = Settings()
