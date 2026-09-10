"""
SQLAlchemy PostgreSQL Model for Semantic Text Chunks.
"""

from typing import List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class ChunkModel(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("documents.workflow_id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Set only for chunks imported from an existing index. The indexer keys
    # search points off this when present, so a re-index overwrites the
    # imported point rather than writing a second one under a new id.
    source_chunk_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    # Content & Edits
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    # Source Mapping
    page_start: Mapped[int] = mapped_column(Integer, default=1)
    page_end: Mapped[int] = mapped_column(Integer, default=1)
    source_page_numbers_json: Mapped[Optional[List[int]]] = mapped_column(JSONB, nullable=True)
    source_spans_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    section_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_reference: Mapped[bool] = mapped_column(Boolean, default=False)

    # Lineage / Chunking Provider metadata
    chunking_provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    chunking_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    chunking_config_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    chunking_run_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    chunk_version: Mapped[int] = mapped_column(Integer, default=1)

    # Review & Exclusions
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="chunks")  # type: ignore

    __table_args__ = (
        UniqueConstraint("workflow_id", "chunk_number", name="uq_chunk_workflow_number"),
        Index("idx_chunks_workflow_chunk", "workflow_id", "chunk_number"),
    )
