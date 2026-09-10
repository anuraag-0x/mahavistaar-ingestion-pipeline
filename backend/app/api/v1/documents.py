"""
Documents API Router.
Handles document listings, uploads, detail views, and stage updates.
"""

import uuid
import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.adapters.storage.minio_adapter import MinioStorageAdapter
from backend.app.core.database import get_db
from backend.app.schemas.common import StandardResponse
from backend.app.schemas.document import (
    DocumentKind,
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
)
from backend.app.models.document import DocumentModel
from backend.app.models.page import PageModel
from backend.app.models.chunk import ChunkModel
from backend.app.models.document import DocumentIndexStatusModel
from backend.app.models.document import DocumentJobModel
from backend.app.services.document_service import DocumentService
from backend.app.services.progress_service import read_progress
from backend.app.services.document_event_service import DocumentEventService
from backend.app.adapters.vector.qdrant_adapter import QdrantAdapter
from backend.app.core.config import settings
from backend.app.services.ingestion_service import IngestionService
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/documents", tags=["Documents"])
storage = MinioStorageAdapter()


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    instance: Optional[str] = Query(None, description="Filter by tenant instance (e.g. mh)"),
    stage: Optional[str] = Query(None, description="Filter by pipeline stage"),
    kind: Optional[str] = Query(None, description="Filter by document kind (document or video)"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    docs, total = await DocumentService.list_documents(
        db, instance=instance, stage=stage, kind=kind, limit=limit, offset=offset
    )
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in docs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/summary")
async def document_summary(
    instance: Optional[str] = Query(None),
    kind: Optional[str] = Query(None, description="Filter by document kind (document or video)"),
    db: AsyncSession = Depends(get_db),
):
    filters = [DocumentModel.is_disabled.is_(False)]
    if instance:
        filters.append(DocumentModel.instance == instance)
    if kind:
        filters.append(DocumentModel.document_kind == kind)
    rows = await db.execute(
        select(DocumentModel.stage, func.count(DocumentModel.workflow_id))
        .where(*filters)
        .group_by(DocumentModel.stage)
    )
    by_stage = {stage: count for stage, count in rows.all()}
    review_stages = {"ocr_review", "translation_review", "chunk_review", "ready_for_ingestion", "approval_for_prod"}
    return {
        "total_documents": sum(by_stage.values()),
        "completed_documents": sum(by_stage.get(stage, 0) for stage in TERMINAL_STAGES),
        "prod_documents": by_stage.get("prod_completed", 0),
        "failed_documents": by_stage.get("failed", 0),
        "review_queue": sum(by_stage.get(stage, 0) for stage in review_stages),
        "by_stage": by_stage,
    }


@router.get("/{workflow_id}/pdf")
async def get_document_pdf(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """Return the original uploaded document for the authenticated PDF viewer."""
    doc = await DocumentService.get_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.filepath.startswith("minio://"):
        raise HTTPException(status_code=404, detail="Document is not stored in MinIO")

    bucket_and_object = doc.filepath.removeprefix("minio://")
    bucket, separator, object_name = bucket_and_object.partition("/")
    if not separator or bucket != storage.bucket_name or not object_name:
        raise HTTPException(status_code=404, detail="Invalid document storage URI")
    try:
        content = storage.get_object_bytes(object_name)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Document file is unavailable in MinIO") from exc

    media_type = mimetypes.guess_type(doc.filename)[0] or "application/pdf"
    # HTTP headers are Latin-1 encoded by Starlette. Keep an ASCII fallback
    # while preserving the original filename through RFC 5987 filename*.
    ascii_filename = Path(doc.filename).name.encode("ascii", "ignore").decode() or "document.pdf"
    encoded_filename = quote(Path(doc.filename).name, safe="")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'inline; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'
            )
        },
    )


@router.get("/{workflow_id}", response_model=DocumentResponse)
async def get_document(workflow_id: str, db: AsyncSession = Depends(get_db)):
    doc = await DocumentService.get_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.patch("/{workflow_id}", response_model=DocumentResponse)
async def update_document(
    workflow_id: str,
    update_data: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
):
    doc = await DocumentService.update_document(db, workflow_id, update_data)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse.model_validate(doc)


ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "docx"}


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    file_type: str = Form(...),
    document_kind: DocumentKind = Form(...),
    # Written into the search payload as `source`, which is how a result says
    # where it came from. Without it the payload falls back to the filename.
    source_label: Optional[str] = Form(None),
    source_label_mr: Optional[str] = Form(None),
    instance: str = Query("mh"),
    scheme_code: Optional[str] = Query(None),
    scheme_name: Optional[str] = Query(None),
    stop_after_ocr: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    normalized_file_type = file_type.strip().lower().lstrip(".")
    normalized_document_kind = document_kind.value
    suffix = Path(file.filename or "").suffix.lower().lstrip(".")
    if not normalized_file_type:
        raise HTTPException(status_code=422, detail="file_type is required")
    if not normalized_document_kind:
        raise HTTPException(status_code=422, detail="document_kind is required")
    normalized_source_label = (source_label or "").strip()
    if not normalized_source_label:
        raise HTTPException(status_code=422, detail="source_label is required")
    if not suffix or normalized_file_type != suffix:
        raise HTTPException(
            status_code=422,
            detail=f"file_type '{file_type}' does not match the uploaded file extension '.{suffix}'",
        )
    if normalized_file_type not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '.{suffix}'. Only PDF and DOCX uploads are accepted.",
        )

    workflow_id = f"doc_{uuid.uuid4().hex[:12]}"
    document_id = f"did_{uuid.uuid4().hex[:8]}"

    # Upload to MinIO
    object_name = f"{instance}/{workflow_id}/{file.filename}"
    file_bytes = await file.read()
    file.file.seek(0)
    storage_uri = storage.upload_file(
        object_name=object_name,
        file_data=file.file,
        length=len(file_bytes),
        content_type=file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream",
    )

    create_data = DocumentCreate(
        document_id=document_id,
        filename=file.filename or "unknown.pdf",
        file_type=normalized_file_type,
        document_kind=normalized_document_kind,
        display_name=file.filename,
        source_label=normalized_source_label,
        source_label_mr=(source_label_mr or "").strip() or None,
        filepath=storage_uri,
        instance=instance,
        scheme_code=scheme_code,
        scheme_name=scheme_name,
        stop_after_ocr=stop_after_ocr,
    )

    doc = await DocumentService.create_document(db, create_data, workflow_id)
    # The document is registered, not started. Every stage runs only once a
    # person approves the one before it, and text extraction is the first of
    # those, so uploading queues nothing.
    await AuditService.log_action(db, workflow_id, document_id, "document_upload", metadata={"filename": doc.filename}, actor_username="system")
    return DocumentResponse.model_validate(doc)


# Every stage waits for a person. Each entry maps the stage being approved to
# the stage it releases, and says whether that stage is work for the ingestion
# worker or another gate for a person. Nothing advances except through here.
STAGE_TRANSITIONS: dict[str, tuple[str, bool]] = {
    "registered": ("ocr_processing", True),
    "ocr_review": ("translation_processing", True),
    "translation_review": ("chunking", True),
    "chunk_review": ("ready_for_ingestion", False),
    "ready_for_ingestion": ("ingesting", True),
    # Publishing to dev ends at dev_completed. Production is a separate request
    # and a separate approval, so a document is never promoted by finishing.
    "dev_completed": ("approval_for_prod", False),
    "approval_for_prod": ("ingesting_prod", True),
}

# The two ends of the pipeline. A document at either is published; which index
# holds it is the difference.
TERMINAL_STAGES = ("dev_completed", "prod_completed")


async def _approve_stage(workflow_id: str, stage: str, db: AsyncSession) -> dict:
    doc = await DocumentService.get_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    transition = STAGE_TRANSITIONS.get(stage)
    if not transition:
        raise HTTPException(status_code=400, detail="Unsupported approval stage")

    # The approval names the stage it is approving, so a stale browser tab or a
    # replayed request cannot skip a gate by calling a later endpoint directly.
    if doc.stage != stage:
        raise HTTPException(
            status_code=409,
            detail=f"This document is at '{doc.stage}', not '{stage}'. Approve the stage it is actually waiting on.",
        )

    next_stage, runs_worker = transition

    if stage == "ocr_review":
        pages = (await db.execute(select(PageModel).where(PageModel.workflow_id == workflow_id))).scalars().all()
        for page in pages:
            page.is_reviewed = True
    elif stage == "translation_review":
        pages = (await db.execute(select(PageModel).where(PageModel.workflow_id == workflow_id))).scalars().all()
        for page in pages:
            page.translation_reviewed = True
    elif stage == "chunk_review":
        chunks = (await db.execute(select(ChunkModel).where(ChunkModel.workflow_id == workflow_id))).scalars().all()
        for chunk in chunks:
            chunk.is_reviewed = True

    doc.stage = next_stage
    await db.commit()
    if runs_worker:
        await IngestionService.enqueue(db, doc, stage=next_stage, job_type=next_stage)
    # Approval moves the stage inside this request, so broadcast it here. Without
    # this the browser only learns of the transition when the worker next
    # publishes, which can be seconds later or never for a stage that is a gate.
    await DocumentEventService.publish(db, workflow_id=workflow_id, stage=next_stage, job_status="queued" if runs_worker else "waiting_review")
    await AuditService.log_action(db, workflow_id, doc.document_id, "approval", old_value=stage, new_value=next_stage, metadata={"approved_stage": stage}, actor_username="system")
    return {"workflow_id": workflow_id, "status": "started" if runs_worker else "ready", "stage": next_stage}


@router.post("/{workflow_id}/approve-upload")
async def approve_upload(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """Release a freshly uploaded document into text extraction."""
    return await _approve_stage(workflow_id, "registered", db)


@router.post("/{workflow_id}/approve-ocr")
async def approve_ocr(workflow_id: str, db: AsyncSession = Depends(get_db)):
    return await _approve_stage(workflow_id, "ocr_review", db)


@router.post("/{workflow_id}/approve-translation")
async def approve_translation(workflow_id: str, db: AsyncSession = Depends(get_db)):
    return await _approve_stage(workflow_id, "translation_review", db)


@router.post("/{workflow_id}/approve-chunks")
async def approve_chunks(workflow_id: str, db: AsyncSession = Depends(get_db)):
    return await _approve_stage(workflow_id, "chunk_review", db)


@router.post("/{workflow_id}/approve-ingestion")
async def approve_ingestion(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """The last gate: publishing the approved chunks to the search index."""
    return await _approve_stage(workflow_id, "ready_for_ingestion", db)


@router.post("/{workflow_id}/request-prod-approval")
async def request_prod_approval(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """Put a document published to dev in front of whoever approves production."""
    if not settings.QDRANT_PROD_COLLECTION_NAME:
        raise HTTPException(status_code=409, detail="No production index is configured for this deployment.")
    return await _approve_stage(workflow_id, "dev_completed", db)


@router.post("/{workflow_id}/approve-prod")
async def approve_prod(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """Publish an approved document to the production index.

    The API does not yet authenticate requests, so this gate is enforced in the
    console only. Anything that can reach the API can call it.
    """
    if not settings.QDRANT_PROD_COLLECTION_NAME:
        raise HTTPException(status_code=409, detail="No production index is configured for this deployment.")
    return await _approve_stage(workflow_id, "approval_for_prod", db)


@router.post("/{workflow_id}/retry-ocr")
async def retry_ocr(workflow_id: str, db: AsyncSession = Depends(get_db)):
    doc = await DocumentService.get_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.stage = "ocr_processing"
    doc.error_message = None
    await db.commit()
    await IngestionService.enqueue(db, doc, stage="ocr_processing", job_type="ocr_retry")
    await DocumentEventService.publish(db, workflow_id=workflow_id, stage="ocr_processing", job_status="queued")
    await AuditService.log_action(db, workflow_id, doc.document_id, "retry_ocr", metadata={"action": "retry_ocr"}, actor_username="system")
    return {"workflow_id": workflow_id, "status": "started", "stage": "ocr_processing"}


@router.post("/{workflow_id}/retry-translation")
async def retry_translation(workflow_id: str, db: AsyncSession = Depends(get_db)):
    doc = await DocumentService.get_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.stage = "translation_processing"
    doc.error_message = None
    await db.commit()
    await IngestionService.enqueue(db, doc, stage="translation_processing", job_type="translation_retry")
    await DocumentEventService.publish(db, workflow_id=workflow_id, stage="translation_processing", job_status="queued")
    await AuditService.log_action(db, workflow_id, doc.document_id, "retry_translation", metadata={"action": "retry_translation"}, actor_username="system")
    return {"workflow_id": workflow_id, "status": "started", "stage": "translation_processing"}


@router.post("/{workflow_id}/retry-chunking")
async def retry_chunking(workflow_id: str, db: AsyncSession = Depends(get_db)):
    doc = await DocumentService.get_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.stage = "chunking"
    doc.error_message = None
    await db.commit()
    await IngestionService.enqueue(db, doc, stage="chunking", job_type="chunking_retry")
    await DocumentEventService.publish(db, workflow_id=workflow_id, stage="chunking", job_status="queued")
    await AuditService.log_action(db, workflow_id, doc.document_id, "retry_chunking", metadata={"action": "retry_chunking"}, actor_username="system")
    return {"workflow_id": workflow_id, "status": "started", "stage": "chunking"}


@router.post("/{workflow_id}/reingest")
@router.post("/{workflow_id}/retry-ingestion")
async def reingest_document(workflow_id: str, db: AsyncSession = Depends(get_db)):
    doc = await DocumentService.get_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.stage = "ingesting"
    doc.error_message = None
    await db.commit()
    await IngestionService.enqueue(db, doc, stage="ingesting", job_type="reingest")
    await DocumentEventService.publish(db, workflow_id=workflow_id, stage="ingesting", job_status="queued")
    await AuditService.log_action(db, workflow_id, doc.document_id, "reingest", metadata={"action": "reingest"}, actor_username="system")
    return {"workflow_id": workflow_id, "status": "started", "stage": "ingesting"}


@router.delete("/{workflow_id}")
async def archive_document(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """Archive a document.

    Nothing is destroyed: the row, its pages and chunks, the stored file and the
    audit trail all remain. What goes is every reference that keeps it in
    circulation, which today means its vectors leave the search collection.
    """
    doc = await DocumentService.get_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    before = 0
    try:
        before = QdrantAdapter().count_by_document_id(
            settings.QDRANT_COLLECTION_NAME, doc.document_id
        )
    except Exception:
        pass  # the count is for the audit entry only, never a reason to fail

    success = await DocumentService.delete_document(db, workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")

    statuses = (await db.execute(
        select(DocumentIndexStatusModel).where(DocumentIndexStatusModel.workflow_id == workflow_id)
    )).scalars().all()
    pending = [row.index_name for row in statuses if row.status == "archive_pending"]

    await AuditService.log_action(
        db, workflow_id, doc.document_id, "archive_document",
        old_value=doc.stage, new_value="archived",
        metadata={"action": "archive", "vectors_removed": before, "search_withdrawal_pending": pending},
        actor_username="system",
    )
    return {
        "workflow_id": workflow_id,
        "status": "archived",
        "vectors_removed": before,
        "search_withdrawal_pending": pending,
        "retained": ["document row", "pages", "chunks", "stored file", "audit history"],
    }


@router.get("/{workflow_id}/qdrant")
async def get_document_qdrant_status(workflow_id: str, db: AsyncSession = Depends(get_db)):
    doc = await DocumentService.get_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = (await db.execute(select(ChunkModel).where(ChunkModel.workflow_id == workflow_id))).scalars().all()
    indexed_chunks = [c for c in chunks if not c.is_excluded]
    return {
        "workflow_id": workflow_id,
        "indexed_chunks": len(indexed_chunks),
        "total_chunks": len(chunks),
        "status": "indexed" if doc.stage in TERMINAL_STAGES else "pending",
    }


@router.get("/{workflow_id}/runtime")
async def get_document_runtime(workflow_id: str, db: AsyncSession = Depends(get_db)):
    doc = await DocumentService.get_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "workflow_id": doc.workflow_id,
        "document_id": doc.document_id,
        "stage": doc.stage,
        "error_message": doc.error_message,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


@router.get("/{workflow_id}/jobs")
async def get_document_jobs(workflow_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(DocumentJobModel).where(DocumentJobModel.workflow_id == workflow_id).order_by(DocumentJobModel.started_at.desc())
    jobs = (await db.execute(stmt)).scalars().all()
    return [
        {
            "job_id": j.id,
            "job_type": j.job_type,
            "status": j.status,
            "current_stage": j.current_stage,
            "created_at": j.started_at.isoformat() if j.started_at else None,
            # The last sub-stage snapshot the worker wrote, so a page opened
            # part way through a long stage shows where it got to rather than
            # waiting for the next event.
            "progress": read_progress(j),
        }
        for j in jobs
    ]
