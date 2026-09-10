"""
Catalog API Router.
Handles local scheme catalog queries and Master AI Catalog sync.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.schemas.catalog import (
    MasterCatalogSyncRequest,
    SchemeCatalogEntryResponse,
)
from backend.app.schemas.common import StandardResponse
from backend.app.services.catalog_service import CatalogService

router = APIRouter(prefix="/catalog", tags=["Catalog"])


@router.get("/schemes", response_model=List[SchemeCatalogEntryResponse])
async def list_scheme_catalog(db: AsyncSession = Depends(get_db)):
    entries = await CatalogService.list_scheme_catalog(db)
    return [SchemeCatalogEntryResponse.model_validate(e) for e in entries]


@router.post("/sync", response_model=StandardResponse)
async def sync_master_catalog(
    request: MasterCatalogSyncRequest,
    db: AsyncSession = Depends(get_db),
):
    version = await CatalogService.sync_master_catalog_entry(
        db, workflow_id=request.workflow_id, status_tier=request.status
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Document not found or nothing to sync")
    return StandardResponse(
        success=True, message=f"Master catalog synced successfully (version {version})"
    )
