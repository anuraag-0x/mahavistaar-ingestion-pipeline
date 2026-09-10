"""
Pydantic Schemas for Local Scheme Catalog and Master AI Catalog.
"""

from datetime import datetime
from typing import List, Optional
from backend.app.schemas.common import BaseSchema


class SchemeCatalogEntryResponse(BaseSchema):
    scheme_code: str
    scheme_name: Optional[str] = None
    scheme_aliases: List[str] = []
    instances: List[str] = []
    workflow_ids: List[str] = []
    collection_name: Optional[str] = None
    chunk_count: int = 0
    status: str = "disabled"
    network_visible: bool = False
    promoted_at: Optional[datetime] = None
    updated_at: datetime


class MasterCatalogEntryResponse(BaseSchema):
    code: str
    content_type: str
    name: str
    tool_name: str
    doc_id: Optional[str] = None
    prompt_snippet: Optional[str] = None
    aliases: List[str] = []
    status: List[str] = []
    workflow_id: Optional[str] = None
    instance: Optional[str] = None
    instance_name: Optional[str] = None
    updated_at: datetime


class MasterCatalogSyncRequest(BaseSchema):
    workflow_id: str
    status: str = "dev"  # dev | live
