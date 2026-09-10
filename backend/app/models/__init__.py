"""
Model Exports for Alembic and Application Access.
"""

from backend.app.core.database import Base
from backend.app.models.audit import AuditLogModel
from backend.app.models.auth import AccessRoleModel, EmailOTPModel
from backend.app.models.catalog import (
    MasterCatalogMetaModel,
    MasterCatalogModel,
    SchemeCatalogEntryModel,
    SchemeCatalogMetaModel,
)
from backend.app.models.chunk import ChunkModel
from backend.app.models.document import (
    DocumentArtifactModel,
    DocumentIndexStatusModel,
    DocumentJobModel,
    DocumentManifestEntryModel,
    DocumentModel,
)
from backend.app.models.page import PageModel
from backend.app.models.document_tracking import DocumentTrackingModel
from backend.app.models.setting import SettingModel

__all__ = [
    "Base",
    "DocumentModel",
    "DocumentJobModel",
    "DocumentArtifactModel",
    "DocumentIndexStatusModel",
    "DocumentManifestEntryModel",
    "PageModel",
    "ChunkModel",
    "DocumentTrackingModel",
    "AuditLogModel",
    "SettingModel",
    "EmailOTPModel",
    "AccessRoleModel",
    "SchemeCatalogEntryModel",
    "SchemeCatalogMetaModel",
    "MasterCatalogModel",
    "MasterCatalogMetaModel",
]
