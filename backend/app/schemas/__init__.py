"""
Schema Exports for MahaVistaar Backend.
"""

from backend.app.schemas.audit import AuditLogListResponse, AuditLogResponse
from backend.app.schemas.auth import (
    AccessRoleCreateRequest,
    AccessRoleResponse,
    EmailOTPRequest,
    EmailOTPVerifyRequest,
    TokenResponse,
    UserProfileResponse,
)
from backend.app.schemas.catalog import (
    MasterCatalogEntryResponse,
    MasterCatalogSyncRequest,
    SchemeCatalogEntryResponse,
)
from backend.app.schemas.chunk import (
    ChunkListResponse,
    ChunkResponse,
    ChunkUpdateRequest,
)
from backend.app.schemas.common import (
    BaseSchema,
    PaginatedResponse,
    StandardResponse,
)
from backend.app.schemas.document import (
    DocumentArtifactResponse,
    DocumentCreate,
    DocumentJobResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
)
from backend.app.schemas.page import (
    PageListResponse,
    PageResponse,
    PageUpdateOcrRequest,
    PageUpdateTranslationRequest,
)
from backend.app.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)

__all__ = [
    "BaseSchema",
    "StandardResponse",
    "PaginatedResponse",
    "DocumentCreate",
    "DocumentUpdate",
    "DocumentResponse",
    "DocumentListResponse",
    "DocumentJobResponse",
    "DocumentArtifactResponse",
    "PageResponse",
    "PageListResponse",
    "PageUpdateOcrRequest",
    "PageUpdateTranslationRequest",
    "ChunkResponse",
    "ChunkListResponse",
    "ChunkUpdateRequest",
    "SearchRequest",
    "SearchResponse",
    "SearchResultItem",
    "SchemeCatalogEntryResponse",
    "MasterCatalogEntryResponse",
    "MasterCatalogSyncRequest",
    "AuditLogResponse",
    "AuditLogListResponse",
    "UserProfileResponse",
    "AccessRoleResponse",
    "AccessRoleCreateRequest",
    "EmailOTPRequest",
    "EmailOTPVerifyRequest",
    "TokenResponse",
]
