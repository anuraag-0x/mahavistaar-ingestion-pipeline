"""Operational queue endpoints for the document processing workspace."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.models.document import DocumentJobModel, DocumentModel
from backend.app.schemas.operations import QueueItemResponse, QueueResponse

router = APIRouter(prefix="/operations", tags=["Operations"])

REVIEW_STAGES = {
    "ocr_review",
    "translation_review",
    "chunk_review",
    "ready_for_ingestion",
    "approval_for_prod",
}


@router.get("/queue", response_model=QueueResponse)
async def list_operations_queue(
    instance: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    # The operations queue is the incomplete-work queue, not only the human
    # review queue. Include processing, failed, and not-yet-started documents.
    # A published document is out of the queue whichever index holds it.
    filters = [
        DocumentModel.is_disabled.is_(False),
        DocumentModel.stage.notin_(("dev_completed", "prod_completed")),
    ]
    if instance:
        filters.append(DocumentModel.instance == instance)

    total = (await db.execute(select(func.count()).select_from(DocumentModel).where(*filters))).scalar_one()
    stmt = (
        select(DocumentModel, DocumentJobModel)
        .outerjoin(
            DocumentJobModel,
            DocumentJobModel.id == DocumentModel.latest_job_id,
        )
        .where(*filters)
        .order_by(DocumentModel.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    items = [
        QueueItemResponse(
            workflow_id=document.workflow_id,
            filename=document.filename,
            stage=document.stage,
            job_id=job.id if job else None,
            job_type=job.job_type if job else None,
            job_status=job.status if job else None,
            started_at=job.started_at.isoformat() if job and job.started_at else None,
            error_message=document.error_message or (job.error_message if job else None),
            available_actions=["review"] if document.stage in REVIEW_STAGES else [],
        )
        for document, job in rows
    ]
    return QueueResponse(items=items, total=total, limit=limit, offset=offset)
