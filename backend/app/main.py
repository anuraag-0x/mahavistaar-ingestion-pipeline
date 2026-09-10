"""
FastAPI Application Entry Point for MahaVistaar Backend.
Provides automatic OpenAPI / Swagger UI documentation and route management.
"""

import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.router import api_router
from backend.app.core.config import settings
from backend.app.core.database import init_db_schema
from backend.app.core.logging import describe, new_error_id, setup_logging

setup_logging()
logger = logging.getLogger("mahavistaar.api")

TAGS_METADATA = [
    {
        "name": "Documents",
        "description": "Document ingestion, status querying, multi-tenancy uploads, and stage transitions.",
    },
    {
        "name": "Pages",
        "description": "Page-level OCR extraction markdown, human edits, and multilingual translations.",
    },
    {
        "name": "Chunks",
        "description": "Semantic chunk reviews, boundary editing, and exclusion management.",
    },
    {
        "name": "Search",
        "description": "Hybrid semantic and lexical vector search across Qdrant indexes.",
    },
    {
        "name": "Catalog",
        "description": "Scheme catalog publication and Master Catalog sync for downstream AI tools.",
    },
    {
        "name": "Admin",
        "description": "Audit trail inspection, application parameters, and system management.",
    },
    {
        "name": "Auth",
        "description": "Email OTP authentication, role-based access control (RBAC), and session verification.",
    },
    {
        "name": "System",
        "description": "Health checks, service status, and runtime metadata.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "starting %s %s | db=%s:%s/%s | storage=%s | vectors=%s",
        settings.APP_NAME, settings.APP_VERSION,
        settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB,
        settings.MINIO_ENDPOINT, settings.QDRANT_URL,
    )
    try:
        await init_db_schema()
        logger.info("database schema ready")
    except Exception as exc:
        logger.warning("database schema init skipped: %s", describe(exc))
    yield
    logger.info("shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
# MahaVistaar Document Ingestion & Search API

## Features
- **Pure PostgreSQL Database:** Reliable, transactional persistence replacing SQLite.
- **Multilingual OCR & Translation:** Mistral Cloud OCR, Chandra, and Gemma vLLM.
- **Semantic Chunking & Vector Search:** Qdrant vector database with multilingual embeddings.
- **Master AI Catalog Sync:** Dynamic system prompt catalog synchronization for AI assistants.
- **Keycloak RBAC & Email OTP:** Enterprise authentication and fine-grained access control.

## Documentation Links
- **Interactive Swagger UI:** `/docs`
- **ReDoc UI:** `/redoc`
- **OpenAPI JSON Specification:** `/openapi.json`
    """,
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------- error handling
# Without these an unexpected failure reaches the client as a bare 500 and the
# only record is uvicorn's traceback, with no route, no payload and nothing the
# caller can quote back. Each handler logs the context and returns an error id.

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(
        "%s %s -> %s | %s",
        request.method, request.url.path, exc.status_code, exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "path": request.url.path},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "%s %s -> 422 invalid request | %s",
        request.method, request.url.path, exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": "The request did not match what this endpoint expects.",
                 "errors": exc.errors(), "path": request.url.path},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    error_id = new_error_id()
    logger.exception(
        "%s %s -> 500 [%s] %s",
        request.method, request.url.path, error_id, describe(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{describe(exc)} (error {error_id})",
            "error_id": error_id,
            "path": request.url.path,
        },
    )


@app.get("/health", tags=["System"], summary="Service Health Check")
async def health_check():
    """Returns the operational status of the MahaVistaar backend service."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": "postgresql",
    }


app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=settings.API_HOST_PORT,
        reload=True,
    )
