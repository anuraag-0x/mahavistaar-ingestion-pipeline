"""
SQLAlchemy PostgreSQL Models for Scheme Catalogs and Master AI Catalog.
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, utc_now


class SchemeCatalogEntryModel(Base):
    __tablename__ = "scheme_catalog_entries"

    scheme_code: Mapped[str] = mapped_column(String(128), primary_key=True)
    scheme_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    scheme_aliases_json: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    instances_json: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    workflow_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    collection_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(64), default="disabled", nullable=False, index=True)
    network_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class SchemeCatalogMetaModel(Base):
    __tablename__ = "scheme_catalog_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class MasterCatalogModel(Base, TimestampMixin):
    __tablename__ = "master_catalog"

    code: Mapped[str] = mapped_column(String(128), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(64), default="scheme", nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    doc_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aliases: Mapped[List[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    status: Mapped[List[str]] = mapped_column(ARRAY(String), default=lambda: ["dev"], nullable=False)
    workflow_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    instance: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    instance_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("idx_master_catalog_status", "status", postgresql_using="gin"),
        Index("idx_master_catalog_aliases", "aliases", postgresql_using="gin"),
    )


class MasterCatalogMetaModel(Base):
    __tablename__ = "master_catalog_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
