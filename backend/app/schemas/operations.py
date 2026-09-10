"""Response schemas for operational queues and dashboard metrics."""

from typing import List, Optional

from backend.app.schemas.common import BaseSchema


class QueueItemResponse(BaseSchema):
    workflow_id: str
    filename: str
    stage: str
    job_id: Optional[int] = None
    job_type: Optional[str] = None
    job_status: Optional[str] = None
    started_at: Optional[str] = None
    error_message: Optional[str] = None
    available_actions: List[str] = []


class QueueResponse(BaseSchema):
    items: List[QueueItemResponse]
    total: int
    limit: int
    offset: int

