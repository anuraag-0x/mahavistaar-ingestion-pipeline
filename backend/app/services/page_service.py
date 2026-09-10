"""
Page Domain Service.
Manages page OCR text, human edits, and multilingual translations.
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.page import PageModel
from backend.app.models.document import DocumentModel
from backend.app.schemas.page import PageUpdateOcrRequest, PageUpdateTranslationRequest
from backend.app.services.audit_service import AuditService


class PageService:
    @staticmethod
    async def get_pages_for_document(
        session: AsyncSession, workflow_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[List[PageModel], int]:
        count_stmt = select(func.count(PageModel.id)).where(PageModel.workflow_id == workflow_id)
        total = (await session.execute(count_stmt)).scalar_one()
        stmt = (
            select(PageModel)
            .where(PageModel.workflow_id == workflow_id)
            .order_by(PageModel.page_number.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_page(session: AsyncSession, workflow_id: str, page_number: int) -> Optional[PageModel]:
        stmt = select(PageModel).where(
            PageModel.workflow_id == workflow_id, PageModel.page_number == page_number
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_page_ocr(
        session: AsyncSession, workflow_id: str, page_number: int, data: PageUpdateOcrRequest
    ) -> Optional[PageModel]:
        page = await PageService.get_page(session, workflow_id, page_number)
        if not page:
            return None

        if data.edited_markdown is not None:
            page.edited_markdown = data.edited_markdown
        if data.is_reviewed is not None:
            page.is_reviewed = data.is_reviewed
        if data.reviewer_notes is not None:
            page.reviewer_notes = data.reviewer_notes

        await session.commit()
        await session.refresh(page)
        document_id = await session.scalar(select(DocumentModel.document_id).where(DocumentModel.workflow_id == workflow_id))
        await AuditService.log_action(session, workflow_id, document_id or workflow_id, "page_edit", entity_type="page", entity_id=page.id, metadata={"page_number": page_number, "kind": "ocr"})
        return page

    @staticmethod
    async def update_page_translation(
        session: AsyncSession, workflow_id: str, page_number: int, data: PageUpdateTranslationRequest
    ) -> Optional[PageModel]:
        page = await PageService.get_page(session, workflow_id, page_number)
        if not page:
            return None

        if data.edited_translation is not None:
            page.edited_translation = data.edited_translation
        if data.translation_reviewed is not None:
            page.translation_reviewed = data.translation_reviewed
        if data.translation_notes is not None:
            page.translation_notes = data.translation_notes

        await session.commit()
        await session.refresh(page)
        document_id = await session.scalar(select(DocumentModel.document_id).where(DocumentModel.workflow_id == workflow_id))
        await AuditService.log_action(session, workflow_id, document_id or workflow_id, "page_edit", entity_type="page", entity_id=page.id, metadata={"page_number": page_number, "kind": "translation"})
        return page
