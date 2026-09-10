"""
Chunk Domain Service.
Manages semantic text chunks, exclusions, human edits, and chunk reviews.
"""

from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.chunk import ChunkModel
from backend.app.models.document import DocumentModel
from backend.app.schemas.chunk import ChunkUpdateRequest
from backend.app.services.audit_service import AuditService
from backend.app.services.document_event_service import DocumentEventService


class ChunkService:
    @staticmethod
    async def get_chunks_for_document(
        session: AsyncSession, workflow_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[List[ChunkModel], int]:
        count_stmt = select(func.count(ChunkModel.id)).where(ChunkModel.workflow_id == workflow_id)
        total = (await session.execute(count_stmt)).scalar_one()
        stmt = (
            select(ChunkModel)
            .where(ChunkModel.workflow_id == workflow_id)
            .order_by(ChunkModel.chunk_number.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_chunk(session: AsyncSession, workflow_id: str, chunk_number: int) -> Optional[ChunkModel]:
        stmt = select(ChunkModel).where(
            ChunkModel.workflow_id == workflow_id, ChunkModel.chunk_number == chunk_number
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_chunk(
        session: AsyncSession, workflow_id: str, chunk_number: int, data: ChunkUpdateRequest
    ) -> Optional[ChunkModel]:
        chunk = await ChunkService.get_chunk(session, workflow_id, chunk_number)
        if not chunk:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(chunk, key, value)

        # A completed document is already in the index. Changing what it says
        # makes the index stale, so it goes back to chunk review; approving from
        # there re-indexes it, which overwrites the points rather than adding to
        # them. Marking review state alone is not a content change and leaves
        # the document where it is.
        document = await session.get(DocumentModel, workflow_id)
        content_changed = bool({"edited_text", "is_excluded"} & set(update_data))
        reopened = False
        if document and content_changed and document.stage in ("dev_completed", "prod_completed"):
            document.stage = "chunk_review"
            document.reindex_required = True
            document.reindex_reason = f"Chunk {chunk_number} edited after indexing"
            reopened = True

        await session.commit()
        await session.refresh(chunk)
        document_id = document.document_id if document else None
        await AuditService.log_action(session, workflow_id, document_id or workflow_id, "chunk_edit", entity_type="chunk", entity_id=chunk.id, metadata={"chunk_number": chunk_number, "fields": list(update_data)})
        if reopened:
            await AuditService.log_action(
                session, workflow_id, document_id or workflow_id, "stage_change",
                new_value="chunk_review", metadata={"reason": "chunk edited after indexing"},
            )
            await DocumentEventService.publish(session, workflow_id=workflow_id, stage="chunk_review")
        return chunk
