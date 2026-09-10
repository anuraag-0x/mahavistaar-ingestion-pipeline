"""Native search-index health endpoints."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from backend.app.adapters.vector.qdrant_adapter import QdrantAdapter
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.document import DocumentIndexStatusModel, DocumentModel

router = APIRouter(prefix="/indexes", tags=["Indexes"])


@router.get("/summary")
async def index_summary() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        documents = (await db.execute(select(func.count(DocumentModel.workflow_id)))).scalar_one()
        indexed_chunks = (await db.execute(select(func.coalesce(func.sum(DocumentIndexStatusModel.chunk_count_indexed), 0)))).scalar_one()
        last_indexed = (await db.execute(select(func.max(DocumentIndexStatusModel.last_indexed_at)))).scalar_one()
    live_error = None
    try:
        QdrantAdapter().client.get_collection(settings.QDRANT_COLLECTION_NAME)
    except Exception as exc:
        live_error = str(exc)
    return [{
        "index_name": settings.QDRANT_COLLECTION_NAME,
        "documents": documents,
        "indexed_chunks": indexed_chunks,
        "stale_documents": 0,
        "last_indexed_at": last_indexed or datetime.now(timezone.utc),
        "live_error": live_error,
    }]
