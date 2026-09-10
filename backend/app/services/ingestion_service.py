"""Native PostgreSQL-backed document ingestion processing."""

from datetime import datetime, timezone
import hashlib
import logging
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.adapters.ai.mistral_ocr_adapter import MistralOCRAdapter
from backend.app.adapters.storage.minio_adapter import MinioStorageAdapter
from backend.app.adapters.ai.hf_embedding_adapter import HFEmbeddingAdapter
from backend.app.adapters.vector.qdrant_adapter import QdrantAdapter
from backend.app.ports.vector_port import VectorPoint
from backend.app.models.document import DocumentJobModel, DocumentModel
from backend.app.models.page import PageModel
from backend.app.models.chunk import ChunkModel
from backend.app.models.document import DocumentIndexStatusModel
from backend.app.core.config import settings
from backend.app.services.document_service import DocumentService
from backend.app.services.audit_service import AuditService
from backend.app.services.document_event_service import DocumentEventService
from backend.app.services.progress_service import Progress, ProgressReporter
from backend.app.core.logging import describe, new_error_id

logger = logging.getLogger("mahavistaar.pipeline")

_HEX = frozenset("0123456789abcdef")


def _point_hex(source_id: str) -> str:
    """The 32 hex characters `uuid.UUID(hex=...)` needs for a point ID.

    A chunk imported from an existing index carries the ID its point was
    already keyed on, which is 32 hex characters. Hashing that again would
    address a different point and leave the original one behind, so it is used
    as-is; anything else is hashed, which is what database chunk IDs need.
    """
    candidate = source_id.replace("-", "").lower()
    if len(candidate) == 32 and set(candidate) <= _HEX:
        return candidate
    return hashlib.md5(source_id.encode("utf-8")).hexdigest()


class IngestionService:
    # The stages this worker knows how to run. Everything else in the lifecycle
    # is a gate waiting on a person, and is never handed to a job.
    WORKER_STAGES = frozenset({"ocr_processing", "translation_processing", "chunking", "ingesting", "ingesting_prod"})

    @staticmethod
    async def enqueue(session: AsyncSession, document: DocumentModel, *, stage: str = "registered", job_type: str = "pipeline") -> DocumentJobModel:
        job = DocumentJobModel(
            workflow_id=document.workflow_id,
            job_type=job_type,
            status="queued",
            current_stage=stage,
            config_json={"stop_after_ocr": document.stop_after_ocr},
        )
        session.add(job)
        await session.flush()
        document.latest_job_id = job.id
        await session.commit()
        await session.refresh(job)
        return job

    @staticmethod
    async def process_job(session: AsyncSession, job_id: int) -> None:
        job = await session.get(DocumentJobModel, job_id)
        if not job or job.status not in {"queued", "claimed", "retry"}:
            return
        document = await session.get(DocumentModel, job.workflow_id)
        if not document:
            job.status = "failed"
            job.error_message = "Document not found"
            await session.commit()
            return

        # A job only ever asks for one of the four stages the worker can run.
        # Anything else is a job written before this mapping existed, and text
        # extraction is the safe place to start.
        target_stage = job.current_stage if job.current_stage in IngestionService.WORKER_STAGES else "ocr_processing"
        logger.info(
            "job %s start | workflow=%s file=%s stage=%s",
            job.id, document.workflow_id, document.filename, target_stage,
        )
        job.status = "running"
        job.current_stage = target_stage
        document.stage = target_stage
        document.error_message = None
        await session.commit()
        # The stage moved from queued to running inside the worker, so say so
        # now. Without this the console shows "queued" until the first progress
        # report, which for a slow provider is a long silence.
        await DocumentEventService.publish(session, workflow_id=document.workflow_id, stage=target_stage, job_status=job.status)

        try:
            if target_stage == "translation_processing":
                await IngestionService._process_translation(session, document, job)
                return
            if target_stage == "chunking":
                await IngestionService._process_chunking(session, document, job)
                return
            if target_stage == "ingesting":
                await IngestionService._process_indexing(session, document, job)
            if target_stage == "ingesting_prod":
                await IngestionService._process_indexing(session, document, job, target="prod")
                return
            reporter = ProgressReporter(session, workflow_id=document.workflow_id, job=job)
            storage = MinioStorageAdapter()
            uri = document.filepath.removeprefix("minio://")
            _, _, object_name = uri.partition("/")
            file_bytes = storage.get_object_bytes(object_name)

            # OCR is one call to the provider, so there is nothing to count until
            # it returns. Say so rather than showing a bar stuck at zero.
            await reporter.report(Progress(
                stage="ocr_processing", label="Reading the document", processed=0, total=0, unit="pages",
            ), force=True)

            pages = await MistralOCRAdapter().process_pdf(file_bytes, document.filename)
            await session.execute(
                PageModel.__table__.delete().where(PageModel.workflow_id == document.workflow_id)
            )
            total_pages = len(pages)
            for index, page in enumerate(pages, 1):
                session.add(PageModel(
                    workflow_id=document.workflow_id,
                    page_number=page.page_number,
                    original_markdown=page.markdown,
                    detected_language=page.detected_language,
                ))
                logger.info(
                    "stored page %d/%d | workflow=%s chars=%d lang=%s",
                    index, total_pages, document.workflow_id,
                    len(page.markdown or ""), page.detected_language or "unknown",
                )
                await reporter.report(Progress(
                    stage="ocr_processing", label="Storing extracted pages",
                    processed=index, total=total_pages, unit="pages",
                ))
            document.page_count = total_pages
            await reporter.finish(Progress(
                stage="ocr_processing", label="Text extracted",
                processed=total_pages, total=total_pages, unit="pages",
            ))
            logger.info(
                "extracted %d pages | workflow=%s file=%s",
                total_pages, document.workflow_id, document.filename,
            )
            document.stage = "ocr_review"
            document.ocr_completed_at = datetime.now(timezone.utc)
            job.status = "waiting_review"
            job.current_stage = "ocr_review"
            job.completed_at = datetime.now(timezone.utc)
            await session.commit()
            await DocumentEventService.publish(session, workflow_id=document.workflow_id, stage=document.stage, job_status=job.status)
            await AuditService.log_action(session, document.workflow_id, document.document_id, "stage_change", new_value="ocr_review", metadata={"job_id": job.id}, actor_username="system")
        except Exception as exc:
            # The stored message is what an operator reads in the console, so it
            # carries the exception type and an id that ties back to the full
            # traceback in the log.
            error_id = new_error_id()
            message = f"{describe(exc)} (error {error_id})"
            logger.exception(
                "job %s failed at %s [%s] | workflow=%s file=%s | %s",
                job.id, target_stage, error_id,
                document.workflow_id, document.filename, describe(exc),
            )
            document.stage = "failed"
            document.error_message = message
            job.status = "failed"
            job.current_stage = "failed"
            job.error_message = message
            job.completed_at = datetime.now(timezone.utc)
            await session.commit()
            await DocumentEventService.publish(session, workflow_id=document.workflow_id, stage=document.stage, job_status=job.status)

    @staticmethod
    async def _process_translation(session: AsyncSession, document: DocumentModel, job: DocumentJobModel) -> None:
        from backend.app.services.translation_service import translate_pages
        result = await session.execute(select(PageModel).where(PageModel.workflow_id == document.workflow_id).order_by(PageModel.page_number))
        pages = [page for page in result.scalars().all()]
        payload = [{"page_number": p.page_number, "original_markdown": p.original_markdown or "", "edited_markdown": p.edited_markdown, "detected_language": p.detected_language} for p in pages]

        reporter = ProgressReporter(session, workflow_id=document.workflow_id, job=job)
        await reporter.report(Progress(
            stage="translation_processing", label="Translating pages",
            processed=0, total=len(payload), unit="pages",
        ), force=True)

        async def on_page_translated(done: int, total: int, page: dict) -> None:
            logger.info(
                "translated page %s (%d/%d) | workflow=%s lang=%s",
                page.get("page_number"), done, total, document.workflow_id,
                page.get("detected_language") or "unknown",
            )
            await reporter.report(Progress(
                stage="translation_processing", label="Translating pages",
                processed=done, total=total, unit="pages",
            ))

        translated = await translate_pages(payload, progress_callback=on_page_translated)
        await reporter.finish(Progress(
            stage="translation_processing", label="Translation complete",
            processed=len(payload), total=len(payload), unit="pages",
        ))
        needs_translation = any(
            value.get("detected_language") not in {None, "en"}
            and (value.get("edited_markdown") or value.get("original_markdown") or "").strip()
            for value in translated
        )
        for page, value in zip(pages, translated):
            page.detected_language = value.get("detected_language")
            page.translated_markdown = value.get("translated_markdown") or value.get("original_markdown")
            page.translation_provider = "native"
        document.translation_completed_at = datetime.now(timezone.utc)

        # An English-only document has nothing to translate, but the review is a
        # gate rather than a chore: no stage moves without a person approving it,
        # so this one stops here too and the audit records why it was empty.
        document.stage = "translation_review"
        job.status = "waiting_review"
        job.current_stage = "translation_review"
        job.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await DocumentEventService.publish(session, workflow_id=document.workflow_id, stage=document.stage, job_status=job.status)
        await AuditService.log_action(
            session, document.workflow_id, document.document_id, "stage_change",
            new_value="translation_review",
            metadata={"job_id": job.id, "translation_needed": needs_translation},
            actor_username="system",
        )

    @staticmethod
    async def _process_chunking(session: AsyncSession, document: DocumentModel, job: DocumentJobModel) -> None:
        result = await session.execute(select(PageModel).where(PageModel.workflow_id == document.workflow_id).order_by(PageModel.page_number))
        pages = list(result.scalars().all())
        await session.execute(ChunkModel.__table__.delete().where(ChunkModel.workflow_id == document.workflow_id))
        reporter = ProgressReporter(session, workflow_id=document.workflow_id, job=job)
        total_pages = len(pages)
        await reporter.report(Progress(
            stage="chunking", label="Preparing search units",
            processed=0, total=total_pages, unit="pages",
        ), force=True)
        chunk_number = 0
        for page_index, page in enumerate(pages, 1):
            text = page.edited_translation or page.translated_markdown or page.edited_markdown or page.original_markdown or ""
            paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
            current = ""
            for paragraph in paragraphs:
                if current and len(current) + len(paragraph) + 2 > 1800:
                    chunk_number += 1
                    session.add(ChunkModel(workflow_id=document.workflow_id, chunk_number=chunk_number, original_text=current, token_count=len(current.split()), page_start=page.page_number, page_end=page.page_number, source_page_numbers_json=[page.page_number], content_type="body", chunking_provider="deterministic", chunking_model="native"))
                    current = ""
                current = f"{current}\n\n{paragraph}".strip()
            if current:
                chunk_number += 1
                session.add(ChunkModel(workflow_id=document.workflow_id, chunk_number=chunk_number, original_text=current, token_count=len(current.split()), page_start=page.page_number, page_end=page.page_number, source_page_numbers_json=[page.page_number], content_type="body", chunking_provider="deterministic", chunking_model="native"))
            logger.info(
                "chunked page %d/%d | workflow=%s chunks_so_far=%d",
                page_index, total_pages, document.workflow_id, chunk_number,
            )
            await reporter.report(Progress(
                stage="chunking", label=f"Preparing search units ({chunk_number} so far)",
                processed=page_index, total=total_pages, unit="pages",
            ))
        await reporter.finish(Progress(
            stage="chunking", label=f"{chunk_number} search units prepared",
            processed=total_pages, total=total_pages, unit="pages",
        ))
        logger.info(
            "chunked into %d pieces from %d pages | workflow=%s",
            chunk_number, len(pages), document.workflow_id,
        )
        document.chunk_count = chunk_number
        document.stage = "chunk_review"
        document.chunks_completed_at = datetime.now(timezone.utc)
        job.status = "waiting_review"
        job.current_stage = "chunk_review"
        job.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await DocumentEventService.publish(session, workflow_id=document.workflow_id, stage=document.stage, job_status=job.status)
        await AuditService.log_action(session, document.workflow_id, document.document_id, "stage_change", new_value="chunk_review", metadata={"job_id": job.id}, actor_username="system")

    @staticmethod
    async def _process_indexing(
        session: AsyncSession, document: DocumentModel, job: DocumentJobModel, target: str = "dev",
    ) -> None:
        """Embed the approved chunks and write them to one of the two indexes.

        Dev and production differ only in the collection written to and the
        stage the document lands on, so publishing to production cannot drift
        from publishing to dev.
        """
        prod = target == "prod"
        collection = settings.QDRANT_PROD_COLLECTION_NAME if prod else settings.QDRANT_COLLECTION_NAME
        if prod and not collection:
            raise RuntimeError("QDRANT_PROD_COLLECTION_NAME is not set; production publishing is unavailable")
        stage_name = "ingesting_prod" if prod else "ingesting"
        done_stage = "prod_completed" if prod else "dev_completed"
        result = await session.execute(select(ChunkModel).where(ChunkModel.workflow_id == document.workflow_id).order_by(ChunkModel.chunk_number))
        # A chunk excluded during review is noise the operator chose to drop, and
        # an empty one carries nothing to match on. Neither belongs in the index.
        chunks = [chunk for chunk in result.scalars().all() if not chunk.is_excluded and (chunk.edited_text or chunk.original_text or "").strip()]
        texts = [chunk.edited_text or chunk.original_text or "" for chunk in chunks]
        if not chunks:
            logger.warning("no indexable chunks | workflow=%s", document.workflow_id)
        reporter = ProgressReporter(session, workflow_id=document.workflow_id, job=job)
        await reporter.report(Progress(
            stage=stage_name, label="Embedding search units",
            processed=0, total=len(chunks), unit="chunks",
        ), force=True)
        vectors = await HFEmbeddingAdapter().generate_embeddings(texts)
        await reporter.report(Progress(
            stage=stage_name, label="Writing to the search index",
            processed=len(chunks), total=len(chunks), unit="chunks",
        ), force=True)
        # The payload type mirrors document_kind rather than collapsing
        # everything that is not a video into "document", which would undo an
        # advisory's type on its next index run.
        document_type = document.document_kind or "document"
        document_name = document.display_name or document.filename
        source = document.source_label or document.source_filename or document.filename
        source_mr = document.source_label_mr or ""
        points = []
        for chunk, text, vector in zip(chunks, texts, vectors):
            # The database chunk ID is the source ID. Hash it to the 32 hex
            # characters required by uuid.UUID(hex=...) while keeping the
            # original source ID available in the payload.
            #
            # A chunk imported from an existing index already has a point in
            # that index. Reusing its ID overwrites that point instead of
            # leaving it behind next to a new one.
            source_id = chunk.source_chunk_id or str(chunk.id)
            marqo_id = _point_hex(source_id)
            point_id = str(uuid.UUID(hex=marqo_id))
            points.append(VectorPoint(
                id=point_id,
                vector=vector,
                payload={
                    "doc_id": document.document_id,
                    "type": document_type,
                    "chunk_id": source_id,
                    "name": document_name,
                    "source": source,
                    "source_mr": source_mr,
                    "text": text,
                },
            ))
        logger.info(
            "embedded %d chunks | workflow=%s collection=%s",
            len(points), document.workflow_id, collection,
        )
        if points:
            try:
                IngestionService._upsert_in_batches(document.workflow_id, collection, points)
                # An edited chunk overwrites its own point, but one that was
                # removed or excluded since the last run has nothing to
                # overwrite it and would linger. Sweeping after the upsert keeps
                # the document searchable throughout.
                QdrantAdapter().delete_document_points_except(
                    collection,
                    document.document_id,
                    [point.id for point in points],
                )
            except Exception as exc:
                logger.error(
                    "vector upsert failed | workflow=%s collection=%s url=%s | %s",
                    document.workflow_id, collection,
                    settings.QDRANT_URL, describe(exc),
                )
                raise RuntimeError(
                    f"Could not write {len(points)} vectors to Qdrant at "
                    f"{settings.QDRANT_URL}: {describe(exc)}"
                ) from exc
        status = await session.get(DocumentIndexStatusModel, {"workflow_id": document.workflow_id, "index_name": collection})
        if not status:
            status = DocumentIndexStatusModel(workflow_id=document.workflow_id, index_name=collection)
            session.add(status)
        status.chunk_count_indexed = len(points)
        status.last_indexed_at = datetime.now(timezone.utc)
        status.last_verified_at = status.last_indexed_at
        status.status = "indexed"
        document.stage = done_stage
        document.ingested_at = datetime.now(timezone.utc)
        job.status = "completed"
        job.current_stage = done_stage
        job.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await DocumentEventService.publish(session, workflow_id=document.workflow_id, stage=document.stage, job_status=job.status)
        await AuditService.log_action(session, document.workflow_id, document.document_id, "stage_change", new_value=done_stage, metadata={"job_id": job.id, "collection": collection}, actor_username="system")

    @staticmethod
    def _upsert_in_batches(workflow_id: str, collection: str, points: list[VectorPoint], batch_size: int = 64) -> None:
        """Write vectors in batches so a large document reports as it goes.

        One upsert of two thousand points is a single silent call that either
        works or does not. Batching gives the log a heartbeat and keeps any one
        request small enough to retry cheaply.
        """
        adapter = QdrantAdapter()
        total = len(points)
        for start in range(0, total, batch_size):
            batch = points[start:start + batch_size]
            adapter.upsert_points(collection, batch)
            logger.info(
                "indexed %d/%d vectors | workflow=%s collection=%s",
                min(start + len(batch), total), total, workflow_id, collection,
            )

    @staticmethod
    async def claim_job(session: AsyncSession) -> int | None:
        result = await session.execute(
            select(DocumentJobModel.id)
            .where(DocumentJobModel.status.in_(["queued", "retry"]))
            .order_by(DocumentJobModel.started_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job_id = result.scalar_one_or_none()
        if job_id is not None:
            job = await session.get(DocumentJobModel, job_id)
            job.status = "claimed"
            await session.commit()
            logger.debug("claimed job %s (%s)", job_id, job.current_stage)
        return job_id
