"""
SQLAlchemy PostgreSQL Models for Email OTPs and Access Roles.
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, utc_now


class EmailOTPModel(Base):
    __tablename__ = "email_otps"

    email: Mapped[str] = mapped_column(String(256), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AccessRoleModel(Base, TimestampMixin):
    __tablename__ = "access_roles"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    permissions: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
