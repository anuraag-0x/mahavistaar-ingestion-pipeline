"""Document tracking resource: one row per document and JSON state history."""

from typing import Any, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.models.document import DocumentModel
from backend.app.models.document_tracking import DocumentTrackingModel

router = APIRouter(prefix="/document-tracking", tags=["Document Tracking"])


@router.get("")
async def list_document_tracking(
    instance: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    filters = [DocumentModel.is_disabled.is_(False)]
    if instance:
        filters.append(DocumentModel.instance == instance)
    total = (await db.execute(select(func.count(DocumentModel.workflow_id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(DocumentModel, DocumentTrackingModel)
        .outerjoin(DocumentTrackingModel, DocumentTrackingModel.workflow_id == DocumentModel.workflow_id)
        .where(*filters)
        .order_by(DocumentModel.updated_at.desc())
        .offset(offset).limit(limit)
    )).all()
    items = []
    for document, tracking in rows:
        history = tracking.state_history if tracking else [{"state": document.stage, "performed_by": "system", "timestamp": document.updated_at.isoformat()}]
        items.append({
            "workflow_id": document.workflow_id,
            "document_id": document.document_id,
            "filename": document.filename,
            "instance": document.instance,
            "original_pdf_url": f"/api/documents/{document.workflow_id}/pdf",
            "current_state": document.stage,
            "state_history": history,
            "last_performed_by": tracking.last_performed_by if tracking else "system",
        })
    return {"items": items, "total": total, "limit": limit, "offset": offset}
