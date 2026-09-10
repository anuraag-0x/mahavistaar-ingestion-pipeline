"""
Pydantic Schemas for Pages, OCR Markdown Edits, and Translations.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import Field

from backend.app.schemas.common import BaseSchema


class PageResponse(BaseSchema):
    id: int
    workflow_id: str
    page_number: int
    original_markdown: Optional[str] = None
    edited_markdown: Optional[str] = None
    is_reviewed: bool = False
    reviewer_notes: Optional[str] = None
    detected_language: Optional[str] = None

    translated_markdown: Optional[str] = None
    edited_translation: Optional[str] = None
    translation_reviewed: bool = False
    translation_notes: Optional[str] = None
    translation_provider: Optional[str] = None
    translation_model: Optional[str] = None
    translation_target_language: Optional[str] = None
    translated_at: Optional[datetime] = None


class PageListResponse(BaseSchema):
    pages: List[PageResponse]
    total: int
    limit: int = 20
    offset: int = 0


class PageUpdateOcrRequest(BaseSchema):
    edited_markdown: Optional[str] = None
    is_reviewed: Optional[bool] = None
    reviewer_notes: Optional[str] = None


class PageUpdateTranslationRequest(BaseSchema):
    edited_translation: Optional[str] = None
    translation_reviewed: Optional[bool] = None
    translation_notes: Optional[str] = None
