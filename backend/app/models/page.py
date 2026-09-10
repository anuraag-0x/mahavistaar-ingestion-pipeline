"""
SQLAlchemy PostgreSQL Model for Pages (OCR Text, Reviews, and Multilingual Translations).
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class PageModel(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("documents.workflow_id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # OCR Markdown & Review
    original_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Multilingual Translation
    translated_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    translation_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    translation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    translation_provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    translation_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    translation_target_language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    translated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="pages")  # type: ignore

    __table_args__ = (
        UniqueConstraint("workflow_id", "page_number", name="uq_page_workflow_number"),
        Index("idx_pages_workflow_page", "workflow_id", "page_number"),
    )
