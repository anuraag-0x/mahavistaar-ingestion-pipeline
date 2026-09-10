"""
Pydantic Schemas for Vector Search and Querying.
"""

from typing import Any, Dict, List, Literal, Optional
from backend.app.schemas.common import BaseSchema


class SearchRequest(BaseSchema):
    query: str
    limit: int = 20
    alpha: float = 0.6
    instance: Optional[str] = "mh"
    scheme_code: Optional[str] = None
    type: Optional[Literal["document", "video"]] = None
    # Retained for request compatibility. References are no longer indexed.
    exclude_reference: bool = True
    method: str = "HYBRID"  # HYBRID, TENSOR, LEXICAL


class SearchResultItem(BaseSchema):
    chunk_id: str
    workflow_id: str
    document_id: str
    text: str
    score: float
    page_number: Optional[int] = 1
    scheme_code: Optional[str] = None
    scheme_name: Optional[str] = None
    instance: Optional[str] = None
    section_title: Optional[str] = None
    highlights: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class SearchResponse(BaseSchema):
    query: str
    total_results: int
    results: List[SearchResultItem]
    latency_ms: float
