"""
Admin API Router.
Handles audit logs and system settings.
"""

from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.schemas.audit import AuditLogListResponse, AuditLogResponse
from backend.app.services.audit_service import AuditService
from backend.app.models.audit import AuditLogModel
from backend.app.models.document import DocumentModel
from backend.app.models.setting import SettingModel
from backend.app.schemas.auth import AccessRoleCreateRequest
from backend.app.services.keycloak_admin_service import create_user, ensure_role, list_roles, list_users as keycloak_list_users, assign_role

router = APIRouter(prefix="/admin", tags=["Admin"])
public_router = APIRouter(tags=["Admin"])


def _audit_payload(log: AuditLogModel, document: DocumentModel | None = None) -> dict[str, Any]:
    payload = {column.name: getattr(log, column.name) for column in AuditLogModel.__table__.columns}
    payload["metadata_json"] = log.metadata_json
    payload.pop("metadata", None)
    if document:
        payload.update({
            "filename": document.filename,
            "instance": document.instance,
            "original_pdf_url": f"/api/documents/{document.workflow_id}/pdf",
        })
    return payload


@public_router.get("/admin/users")
async def list_users(search: str = "", limit: int = Query(20, ge=1, le=200)):
    return keycloak_list_users(search=search, limit=limit)


@public_router.post("/admin/users")
async def create_user(payload: dict[str, Any]):
    return create_user(payload)


@public_router.put("/admin/users/{user_id}/access")
async def update_user_access(user_id: str, payload: dict[str, Any]):
    # The role used to be hardcoded to super_admin and the payload ignored, so
    # every assignment granted full administration whatever was asked for.
    role = str(payload.get("role") or payload.get("access_type") or "").strip()
    if not role:
        raise HTTPException(400, "role is required")
    return assign_role(user_id, role)


@public_router.get("/admin/roles")
async def get_roles():
    return list_roles()


@public_router.post("/admin/roles")
async def create_role(payload: AccessRoleCreateRequest):
    return ensure_role(payload.name, payload.label, payload.description, payload.permissions)


@public_router.get("/admin/access-options")
async def access_options():
    # Built from the realm rather than a fixed list, so a role created in the
    # console can be assigned without another code change.
    roles = [role for role in list_roles()["roles"] if role["exists"]]
    return {
        "realm": settings.KEYCLOAK_ADMIN_REALM,
        "access_types": [{"id": role["name"], "label": role["label"]} for role in roles],
        "required_fields": {role["name"]: ["email", "first_name", "last_name"] for role in roles},
    }


@router.get("/audit/{workflow_id}", response_model=AuditLogListResponse)
async def get_audit_logs(
    workflow_id: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    logs, total = await AuditService.get_logs_for_document(db, workflow_id, limit, offset)
    document = await db.get(DocumentModel, workflow_id)
    return AuditLogListResponse(
        logs=[AuditLogResponse.model_validate(_audit_payload(l, document)) for l in logs],
        total=total,
        limit=limit,
        offset=offset,
    )


@public_router.get("/audit", response_model=AuditLogListResponse)
async def get_global_audit_logs(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return the workspace audit stream used by the Audit screen."""
    filters = [AuditLogModel.action_type == action_type] if action_type else []
    total = (await db.execute(select(func.count(AuditLogModel.id)).where(*filters))).scalar_one()
    result = await db.execute(
        select(AuditLogModel, DocumentModel)
        .outerjoin(DocumentModel, DocumentModel.workflow_id == AuditLogModel.workflow_id)
        .where(*filters)
        .order_by(AuditLogModel.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    logs = [_audit_payload(log, document) for log, document in result.all()]
    return AuditLogListResponse(logs=[AuditLogResponse.model_validate(log) for log in logs], total=total, limit=limit, offset=offset)


@public_router.get("/settings/search")
async def get_search_settings(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    result = await db.execute(select(SettingModel).where(SettingModel.key.like("search.%")))
    values = {row.key.removeprefix("search."): row.value for row in result.scalars()}
    return {
        "searchMethod": values.get("method", "HYBRID"),
        "limit": int(values.get("limit", "20")),
        "alpha": float(values.get("alpha", "0.6")),
        "rankingMethod": values.get("ranking_method", "rrf"),
        "indexName": values.get("index_name", "local-documents-index"),
        "excludeReference": values.get("exclude_reference", "true").lower() == "true",
    }


@public_router.get("/runs")
async def get_runs(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.app.models.document import DocumentJobModel
    total = (await db.execute(select(func.count(DocumentJobModel.id)))).scalar_one()
    result = await db.execute(
        select(DocumentJobModel, DocumentModel)
        .join(DocumentModel, DocumentModel.workflow_id == DocumentJobModel.workflow_id)
        .order_by(DocumentJobModel.started_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = [
        {
            "id": job.id,
            "workflow_id": job.workflow_id,
            "job_type": job.job_type,
            "temporal_workflow_id": job.temporal_workflow_id,
            "status": job.status,
            "current_stage": job.current_stage,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "error_message": job.error_message,
            "filename": document.filename,
            "display_name": document.display_name,
            "source_filename": document.source_filename,
            "document_stage": document.stage,
            "instance": document.instance,
        }
        for job, document in result.all()
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}
