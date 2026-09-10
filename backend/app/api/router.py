"""
Root API Router for MahaVistaar Backend.
Mounts all v1 domain routers.
"""

from fastapi import APIRouter
from backend.app.api.v1.admin import router as admin_router, public_router as public_admin_router
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.catalog import router as catalog_router
from backend.app.api.v1.chunks import router as chunks_router
from backend.app.api.v1.documents import router as documents_router
from backend.app.api.v1.pages import router as pages_router
from backend.app.api.v1.operations import router as operations_router
from backend.app.api.v1.indexes import router as indexes_router
from backend.app.api.v1.search import router as search_router
from backend.app.api.v1.tracking import router as tracking_router
from backend.app.api.v1.events import router as events_router

api_router = APIRouter()

# Include all sub-routers under /api/v1 (and direct aliases for frontend backwards compatibility)
api_router.include_router(documents_router, prefix="/api/v1")
api_router.include_router(pages_router, prefix="/api/v1")
api_router.include_router(chunks_router, prefix="/api/v1")
api_router.include_router(search_router, prefix="/api/v1")
api_router.include_router(catalog_router, prefix="/api/v1")
api_router.include_router(admin_router, prefix="/api/v1")
api_router.include_router(public_admin_router, prefix="/api/v1")
api_router.include_router(auth_router, prefix="/api/v1")
api_router.include_router(operations_router, prefix="/api/v1")
api_router.include_router(indexes_router, prefix="/api/v1")
api_router.include_router(tracking_router, prefix="/api/v1")
api_router.include_router(events_router, prefix="/api/v1")

# Direct aliases without /api/v1 prefix for frontend compatibility
api_router.include_router(documents_router)
api_router.include_router(pages_router)
api_router.include_router(chunks_router)
api_router.include_router(search_router)
api_router.include_router(catalog_router)
api_router.include_router(admin_router)
api_router.include_router(public_admin_router)
api_router.include_router(auth_router)
api_router.include_router(operations_router)
api_router.include_router(indexes_router)
api_router.include_router(tracking_router)
api_router.include_router(events_router)
