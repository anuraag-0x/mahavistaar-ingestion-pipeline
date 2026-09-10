"""
Pydantic Schemas for Chunks and Chunk Editing.
"""

from typing import Any, List, Optional
from backend.app.schemas.common import BaseSchema


class ChunkResponse(BaseSchema):
    id: int
    workflow_id: str
    chunk_number: int
    original_text: Optional[str] = None
    edited_text: Optional[str] = None
    token_count: int = 0
    page_start: int = 1
    page_end: int = 1
    source_page_numbers_json: Optional[List[int]] = None
    source_spans_json: Optional[Any] = None
    section_title: Optional[str] = None
    content_type: Optional[str] = None
    is_reference: bool = False
    chunking_provider: Optional[str] = None
    chunking_model: Optional[str] = None
    chunk_version: int = 1
    is_reviewed: bool = False
    is_excluded: bool = False
    reviewer_notes: Optional[str] = None


class ChunkListResponse(BaseSchema):
    chunks: List[ChunkResponse]
    total: int
    limit: int = 20
    offset: int = 0


class ChunkUpdateRequest(BaseSchema):
    edited_text: Optional[str] = None
    is_reviewed: Optional[bool] = None
    is_excluded: Optional[bool] = None
    reviewer_notes: Optional[str] = None
    is_reference: Optional[bool] = None
    section_title: Optional[str] = None
