"""
SQLAlchemy PostgreSQL Model for Audit Logs.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import utc_now


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    field_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Actor Metadata
    actor_user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    actor_username: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    actor_email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    actor_roles: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_audit_logs_workflow_ts", "workflow_id", "timestamp"),
        Index("idx_audit_logs_timestamp_desc", "timestamp", postgresql_using="btree"),
    )
