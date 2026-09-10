"""
Chunks API Router.
Handles semantic chunk reviews, exclusions, and text adjustments.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.schemas.chunk import (
    ChunkListResponse,
    ChunkResponse,
    ChunkUpdateRequest,
)
from backend.app.services.chunk_service import ChunkService
from backend.app.models.chunk import ChunkModel
from backend.app.models.document import DocumentModel

router = APIRouter(prefix="/chunks", tags=["Chunks"])


@router.get("/search")
async def search_chunks(
    query: str = "",
    stage: str | None = None,
    include_excluded: bool = False,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if query.strip():
        pattern = f"%{query.strip()}%"
        conditions.append(or_(ChunkModel.original_text.ilike(pattern), ChunkModel.edited_text.ilike(pattern)))
    if stage:
        conditions.append(DocumentModel.stage == stage)
    if not include_excluded:
        conditions.append(ChunkModel.is_excluded.is_(False))
    total = (await db.execute(select(func.count(ChunkModel.id)).join(DocumentModel).where(*conditions))).scalar_one()
    result = await db.execute(
        select(ChunkModel, DocumentModel)
        .join(DocumentModel)
        .where(*conditions)
        .order_by(ChunkModel.workflow_id, ChunkModel.chunk_number)
        .offset(offset)
        .limit(limit)
    )
    items = []
    for chunk, document in result.all():
        item = ChunkResponse.model_validate(chunk).model_dump()
        item.update({"filename": document.filename, "display_name": document.display_name, "stage": document.stage})
        items.append(item)
    return {"items": items, "chunks": items, "total": total, "limit": limit, "offset": offset}


@router.get("/document/{workflow_id}", response_model=ChunkListResponse)
async def get_document_chunks(
    workflow_id: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    chunks, total = await ChunkService.get_chunks_for_document(db, workflow_id, limit, offset)
    return ChunkListResponse(
        chunks=[ChunkResponse.model_validate(c) for c in chunks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{workflow_id}/{chunk_number}", response_model=ChunkResponse)
async def get_chunk(workflow_id: str, chunk_number: int, db: AsyncSession = Depends(get_db)):
    chunk = await ChunkService.get_chunk(db, workflow_id, chunk_number)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return ChunkResponse.model_validate(chunk)


@router.patch("/{workflow_id}/{chunk_number}", response_model=ChunkResponse)
async def update_chunk(
    workflow_id: str,
    chunk_number: int,
    data: ChunkUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    chunk = await ChunkService.update_chunk(db, workflow_id, chunk_number, data)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return ChunkResponse.model_validate(chunk)
