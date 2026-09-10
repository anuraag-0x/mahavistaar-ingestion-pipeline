"""
Pydantic Schemas for Audit Logs.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import Field
from backend.app.schemas.common import BaseSchema


class AuditLogResponse(BaseSchema):
    id: int
    workflow_id: str
    document_id: str
    action_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    timestamp: datetime
    actor_user_id: Optional[str] = None
    actor_username: Optional[str] = None
    actor_email: Optional[str] = None
    actor_roles: Optional[List[str]] = None
    filename: Optional[str] = None
    instance: Optional[str] = None
    original_pdf_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata_json")


class AuditLogListResponse(BaseSchema):
    logs: List[AuditLogResponse]
    total: int
    limit: int = 20
    offset: int = 0
