"""
Pydantic Schemas for Documents, Jobs, and Ingestion Workflows.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field

from backend.app.schemas.common import BaseSchema


class DocumentKind(str, Enum):
    ADVISORY = "advisory"
    SCHEME = "scheme"
    VIDEO = "video"


class DocumentBase(BaseSchema):
    document_id: str
    filename: str
    file_type: str
    display_name: Optional[str] = None
    source_filename: Optional[str] = None
    instance: str = "mh"
    document_kind: str = "document"
    scheme_code: Optional[str] = None
    scheme_name: Optional[str] = None
    scheme_aliases_json: Optional[Any] = None
    tool_routing: Optional[str] = "qdrant"
    catalog_visible: bool = True
    network_visible: bool = True


class DocumentCreate(DocumentBase):
    filepath: str
    source_label: Optional[str] = None
    source_label_mr: Optional[str] = None
    canonical_document_id: Optional[str] = None
    source_type: Optional[str] = None
    canonical_input_type: Optional[str] = None
    stop_after_ocr: bool = False
    is_demo: bool = False


class DocumentUpdate(BaseSchema):
    display_name: Optional[str] = None
    scheme_code: Optional[str] = None
    scheme_name: Optional[str] = None
    scheme_aliases_json: Optional[Any] = None
    tool_routing: Optional[str] = None
    catalog_visible: Optional[bool] = None
    network_visible: Optional[bool] = None
    is_disabled: Optional[bool] = None
    reindex_required: Optional[bool] = None
    reindex_reason: Optional[str] = None


class DocumentResponse(DocumentBase):
    workflow_id: str
    canonical_document_id: Optional[str] = None
    filepath: str
    source_type: Optional[str] = None
    stage: str
    page_count: int = 0
    chunk_count: int = 0
    error_message: Optional[str] = None
    is_demo: bool = False
    is_disabled: bool = False
    stop_after_ocr: bool = False
    reindex_required: bool = False
    reindex_reason: Optional[str] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    ocr_completed_at: Optional[datetime] = None
    translation_completed_at: Optional[datetime] = None
    chunks_completed_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None


class DocumentListResponse(BaseSchema):
    documents: List[DocumentResponse]
    total: int
    offset: int = 0
    limit: int = 20


class DocumentJobResponse(BaseSchema):
    id: int
    workflow_id: str
    job_type: str
    temporal_workflow_id: Optional[str] = None
    temporal_run_id: Optional[str] = None
    status: str
    current_stage: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None


class DocumentArtifactResponse(BaseSchema):
    id: int
    workflow_id: str
    job_id: Optional[int] = None
    artifact_type: str
    stage: Optional[str] = None
    storage_uri: str
    mime_type: Optional[str] = None
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
