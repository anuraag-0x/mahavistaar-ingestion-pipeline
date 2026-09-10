"""
Document Domain Service.
Manages document lifecycle, database operations, stage transitions, and queries.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.logging import describe
from backend.app.models.document import DocumentArtifactModel, DocumentJobModel, DocumentModel
from backend.app.schemas.document import DocumentCreate, DocumentUpdate


logger = logging.getLogger("mahavistaar.documents")


class DocumentService:
    @staticmethod
    async def create_document(session: AsyncSession, data: DocumentCreate, workflow_id: str) -> DocumentModel:
        now = datetime.now(timezone.utc)
        doc = DocumentModel(
            workflow_id=workflow_id,
            document_id=data.document_id,
            canonical_document_id=data.canonical_document_id,
            filename=data.filename,
            file_type=data.file_type,
            display_name=data.display_name or data.filename,
            source_filename=data.source_filename or data.filename,
            source_label=data.source_label,
            source_label_mr=data.source_label_mr,
            filepath=data.filepath,
            instance=data.instance,
            document_kind=data.document_kind,
            scheme_code=data.scheme_code,
            scheme_name=data.scheme_name,
            scheme_aliases_json=data.scheme_aliases_json,
            tool_routing=data.tool_routing or "qdrant",
            catalog_visible=data.catalog_visible,
            network_visible=data.network_visible,
            source_type=data.source_type,
            canonical_input_type=data.canonical_input_type,
            stop_after_ocr=data.stop_after_ocr,
            is_demo=data.is_demo,
            stage="registered",
            created_at=now,
            updated_at=now,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc

    @staticmethod
    async def get_document(session: AsyncSession, workflow_id: str) -> Optional[DocumentModel]:
        stmt = select(DocumentModel).where(DocumentModel.workflow_id == workflow_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_documents(
        session: AsyncSession,
        instance: Optional[str] = None,
        stage: Optional[str] = None,
        kind: Optional[str] = None,
        is_disabled: Optional[bool] = False,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[DocumentModel], int]:
        stmt = select(DocumentModel)
        count_stmt = select(func.count(DocumentModel.workflow_id))

        if instance:
            stmt = stmt.where(DocumentModel.instance == instance)
            count_stmt = count_stmt.where(DocumentModel.instance == instance)
        if stage:
            stmt = stmt.where(DocumentModel.stage == stage)
            count_stmt = count_stmt.where(DocumentModel.stage == stage)
        if kind:
            stmt = stmt.where(DocumentModel.document_kind == kind)
            count_stmt = count_stmt.where(DocumentModel.document_kind == kind)
        if is_disabled is not None:
            stmt = stmt.where(DocumentModel.is_disabled == is_disabled)
            count_stmt = count_stmt.where(DocumentModel.is_disabled == is_disabled)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = stmt.order_by(DocumentModel.created_at.desc()).offset(offset).limit(limit)
        result = await session.execute(stmt)
        docs = list(result.scalars().all())
        return docs, total

    @staticmethod
    async def update_document(
        session: AsyncSession, workflow_id: str, data: DocumentUpdate
    ) -> Optional[DocumentModel]:
        doc = await DocumentService.get_document(session, workflow_id)
        if not doc:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(doc, key, value)

        doc.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(doc)
        return doc

    @staticmethod
    async def update_stage(
        session: AsyncSession, workflow_id: str, stage: str, error_message: Optional[str] = None
    ) -> Optional[DocumentModel]:
        doc = await DocumentService.get_document(session, workflow_id)
        if not doc:
            return None

        now = datetime.now(timezone.utc)
        doc.stage = stage
        doc.updated_at = now
        if error_message is not None:
            doc.error_message = error_message

        if stage == "ocr_completed":
            doc.ocr_completed_at = now
        elif stage == "translation_completed":
            doc.translation_completed_at = now
        elif stage == "chunks_completed":
            doc.chunks_completed_at = now
        elif stage == "ingested":
            doc.ingested_at = now

        await session.commit()
        await session.refresh(doc)
        return doc

    @staticmethod
    async def delete_document(session: AsyncSession, workflow_id: str) -> bool:
        """Archive a document: the row, its pages, chunks and the stored file
        all stay, but every reference that makes it reachable is withdrawn.

        Concretely that means its vectors leave the search collection. Without
        that step a removed document kept answering search queries, because the
        search path reads Qdrant directly and never consults this table.
        """
        doc = await DocumentService.get_document(session, workflow_id)
        if not doc:
            return False

        removed = await DocumentService._withdraw_from_search(session, doc)

        doc.is_disabled = True
        doc.stage = "archived"
        doc.updated_at = datetime.now(timezone.utc)
        await session.commit()
        logger.info(
            "archived | workflow=%s doc_id=%s file=%s vectors_removed=%d",
            doc.workflow_id, doc.document_id, doc.filename, removed,
        )
        return True

    @staticmethod
    async def _withdraw_from_search(session: AsyncSession, doc) -> int:
        """Drop the document's points and mark its index rows archived.

        A vector store that is unreachable must not block archiving; the index
        row is left saying the points are still out there so a later sweep can
        finish the job.
        """
        from backend.app.adapters.vector.qdrant_adapter import QdrantAdapter
        from backend.app.models.document import DocumentIndexStatusModel

        rows = (
            await session.execute(
                select(DocumentIndexStatusModel).where(
                    DocumentIndexStatusModel.workflow_id == doc.workflow_id
                )
            )
        ).scalars().all()

        collections = {row.index_name for row in rows} or {settings.QDRANT_COLLECTION_NAME}
        adapter = None
        removed_total = 0
        failures: list[str] = []

        for collection in collections:
            try:
                adapter = adapter or QdrantAdapter()
                removed_total += adapter.delete_by_document_id(collection, doc.document_id)
            except Exception as exc:
                failures.append(f"{collection}: {describe(exc)}")
                logger.error(
                    "could not withdraw vectors | workflow=%s collection=%s | %s",
                    doc.workflow_id, collection, describe(exc),
                )

        now = datetime.now(timezone.utc)
        for row in rows:
            if failures:
                row.status = "archive_pending"
                row.details_json = {"archive_error": "; ".join(failures)}
            else:
                row.status = "archived"
                row.chunk_count_indexed = 0
                row.details_json = None
            row.last_verified_at = now

        return removed_total
