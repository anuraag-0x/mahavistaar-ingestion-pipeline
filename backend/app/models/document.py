"""
SQLAlchemy PostgreSQL Models for Documents, Jobs, Artifacts, Index Status, and Manifests.
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, utc_now


class DocumentModel(Base, TimestampMixin):
    __tablename__ = "documents"

    workflow_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    canonical_document_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False, default="pdf")
    display_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_manifest_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_file_fingerprint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    filepath: Mapped[str] = mapped_column(String(1024), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="registered")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Stage Completion Timestamps
    ocr_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    translation_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    chunks_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Classification & Ingestion Meta
    source_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Written verbatim into the search payload as `source` and `source_mr`.
    # `source` falls back to the filename, which is what the pipeline used
    # before these existed; `source_mr` has no fallback and was always empty.
    source_label: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    source_label_mr: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    # Free-form per-document metadata. Nothing writes to it yet; it exists so
    # fields the search payload grows later have somewhere to live without
    # another schema change.
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    canonical_input_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    stop_after_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    reindex_required: Mapped[bool] = mapped_column(Boolean, default=False)
    reindex_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Foreign Keys / Artifact Pointers
    original_artifact_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    normalized_artifact_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    latest_job_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Multi-tenancy & Catalog
    instance: Mapped[str] = mapped_column(String(64), default="mh", index=True)
    document_kind: Mapped[str] = mapped_column(String(64), default="document")
    scheme_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    scheme_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    scheme_aliases_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tool_routing: Mapped[Optional[str]] = mapped_column(String(64), default="qdrant")
    catalog_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    network_visible: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    pages: Mapped[List["PageModel"]] = relationship(
        "PageModel", back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[List["ChunkModel"]] = relationship(
        "ChunkModel", back_populates="document", cascade="all, delete-orphan"
    )
    jobs: Mapped[List["DocumentJobModel"]] = relationship(
        "DocumentJobModel", back_populates="document", cascade="all, delete-orphan"
    )
    artifacts: Mapped[List["DocumentArtifactModel"]] = relationship(
        "DocumentArtifactModel", back_populates="document", cascade="all, delete-orphan"
    )
    index_statuses: Mapped[List["DocumentIndexStatusModel"]] = relationship(
        "DocumentIndexStatusModel", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_documents_created_desc", "created_at", postgresql_using="btree"),
        Index("idx_documents_instance_stage", "instance", "stage"),
    )


class DocumentJobModel(Base):
    __tablename__ = "document_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("documents.workflow_id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    temporal_workflow_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    temporal_run_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="running")
    current_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="jobs")

    __table_args__ = (
        Index("idx_document_jobs_workflow_started", "workflow_id", "started_at"),
    )


class DocumentArtifactModel(Base):
    __tablename__ = "document_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("documents.workflow_id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="artifacts")

    __table_args__ = (
        Index("idx_document_artifacts_workflow_created", "workflow_id", "created_at"),
    )


class DocumentIndexStatusModel(Base):
    __tablename__ = "document_index_status"

    workflow_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("documents.workflow_id", ondelete="CASCADE"), primary_key=True
    )
    index_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    vector_doc_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    chunk_count_indexed: Mapped[int] = mapped_column(Integer, default=0)
    last_indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    details_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="index_statuses")


class DocumentManifestEntryModel(Base):
    __tablename__ = "document_manifest_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    manifest_filename: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    title_en: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    title_gu: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    doc_language: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    category_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quality_score: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    priority_rank: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ingestion_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_csv_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
