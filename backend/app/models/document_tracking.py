"""One-row-per-document processing trace."""

from typing import Any, Optional
from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin


class DocumentTrackingModel(Base, TimestampMixin):
    __tablename__ = "document_tracking"

    workflow_id: Mapped[str] = mapped_column(String(128), ForeignKey("documents.workflow_id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_pdf_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    current_state: Mapped[str] = mapped_column(String(64), nullable=False)
    state_history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    last_performed_by: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

