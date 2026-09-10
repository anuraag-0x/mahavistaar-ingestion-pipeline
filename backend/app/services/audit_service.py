"""
Audit Logging Service.
Logs all administrative and workflow state changes into PostgreSQL audit_logs.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.audit import AuditLogModel


class AuditService:
    @staticmethod
    async def log_action(
        session: AsyncSession,
        workflow_id: str,
        document_id: str,
        action_type: str,
        # The audit row and its schema have carried these since the table was
        # created; only this signature was missing them, so every caller that
        # named the edited entity raised TypeError instead of logging.
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        field_name: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        actor_user_id: Optional[str] = None,
        actor_username: Optional[str] = None,
        actor_email: Optional[str] = None,
        actor_roles: Optional[List[str]] = None,
    ) -> AuditLogModel:
        log = AuditLogModel(
            workflow_id=workflow_id,
            document_id=document_id,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            metadata_json=metadata,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            actor_email=actor_email,
            actor_roles=actor_roles,
            timestamp=datetime.now(timezone.utc),
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log

    @staticmethod
    async def get_logs_for_document(
        session: AsyncSession, workflow_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[List[AuditLogModel], int]:
        count_stmt = select(func.count(AuditLogModel.id)).where(AuditLogModel.workflow_id == workflow_id)
        total = (await session.execute(count_stmt)).scalar_one()
        stmt = (
            select(AuditLogModel)
            .where(AuditLogModel.workflow_id == workflow_id)
            .order_by(AuditLogModel.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total
