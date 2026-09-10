"""Rebuild pipeline records from an existing search collection.

The collection this imports from predates the current pipeline: its points
carry `doc_id`, `chunk_id`, `name`, `source`, `source_mr` and `text`, but no
`workflow_id` and no page structure, so the console has nothing to show for
them. This walks the collection, groups points by `doc_id`, and writes one
`documents` row and one `chunks` row per point, which is what the console
reads. The points already exist in the collection, so the documents land in
`dev_completed` with an index-status row recording that, rather than in a
review stage that would claim they are still waiting to be published. Editing a chunk
moves one back into `chunk_review` on its own.

The original `chunk_id` is kept on each chunk. The indexer reuses it as the
point ID, so re-indexing an imported document overwrites its existing points
instead of writing a second copy under freshly generated IDs.

No PDF is created: these documents have no source file, so the page-level OCR
and translation screens stay empty and "Open source PDF" will not resolve.

    python -m scripts.import_index_collection --source mh-dev-index-hybrid --dry-run
    python -m scripts.import_index_collection --source mh-dev-index-hybrid
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal, async_engine
from backend.app.models.chunk import ChunkModel
from backend.app.models.document import DocumentIndexStatusModel, DocumentModel

SCROLL_PAGE = 512


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.QDRANT_API_KEY:
        headers["api-key"] = settings.QDRANT_API_KEY
    return headers


async def scroll_points(collection: str) -> list[dict]:
    """Every point's payload, without vectors — only the text is needed here."""
    url = f"{settings.QDRANT_URL.rstrip('/')}/collections/{collection}/points/scroll"
    points: list[dict] = []
    offset = None
    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            body: dict = {"limit": SCROLL_PAGE, "with_payload": True, "with_vector": False}
            if offset is not None:
                body["offset"] = offset
            response = await client.post(url, headers=_headers(), json=body)
            response.raise_for_status()
            result = response.json()["result"]
            batch = result.get("points", [])
            points.extend(batch)
            offset = result.get("next_page_offset")
            print(f"  scrolled {len(points)} points", flush=True)
            if offset is None or not batch:
                return points


def group_by_document(points: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for point in points:
        payload = point.get("payload") or {}
        doc_id = payload.get("doc_id")
        if not doc_id:
            continue
        grouped[doc_id].append({
            "point_id": point.get("id"),
            "chunk_id": str(payload.get("chunk_id") or point.get("id")),
            "name": payload.get("name") or doc_id,
            "source": payload.get("source") or "",
            "source_mr": payload.get("source_mr") or "",
            "type": payload.get("type") or "document",
            "text": payload.get("text") or "",
        })
    # Stable chunk numbering: the collection has no ordering key, so the point
    # ID is used to make repeated imports produce the same numbering.
    for rows in grouped.values():
        rows.sort(key=lambda row: str(row["point_id"]))
    return grouped


async def import_collection(collection: str, dry_run: bool, instance: str) -> None:
    print(f"reading {collection} at {settings.QDRANT_URL}", flush=True)
    grouped = group_by_document(await scroll_points(collection))
    print(f"{len(grouped)} documents, {sum(len(v) for v in grouped.values())} chunks", flush=True)

    async with AsyncSessionLocal() as session:
        existing = set(
            (await session.execute(select(DocumentModel.document_id))).scalars().all()
        )
        now = datetime.now(timezone.utc)
        created = skipped = 0

        for doc_id, rows in sorted(grouped.items()):
            if doc_id in existing:
                skipped += 1
                continue
            first = rows[0]
            workflow_id = f"doc_{uuid.uuid4().hex[:12]}"
            name = first["name"]
            print(f"  + {name[:56]:58} {len(rows):>5} chunks  {workflow_id}", flush=True)
            if dry_run:
                created += 1
                continue

            session.add(DocumentModel(
                workflow_id=workflow_id,
                document_id=doc_id,
                filename=name,
                display_name=name,
                file_type="pdf",
                # No source file exists for imported records; this is a label,
                # not a path that resolves in object storage.
                filepath=f"imported/{collection}/{doc_id}",
                stage="dev_completed",
                page_count=0,
                chunk_count=len(rows),
                source_type="imported",
                source_label=first["source"],
                source_label_mr=first["source_mr"],
                # The payload's own type, so an advisory stays an advisory.
                document_kind=first["type"] or "document",
                instance=instance,
                chunks_completed_at=now,
                ingested_at=now,
            ))
            session.add(DocumentIndexStatusModel(
                workflow_id=workflow_id,
                index_name=collection,
                vector_doc_id=doc_id,
                chunk_count_indexed=len(rows),
                last_indexed_at=now,
                last_verified_at=now,
                status="indexed",
            ))
            for number, row in enumerate(rows, start=1):
                session.add(ChunkModel(
                    workflow_id=workflow_id,
                    chunk_number=number,
                    source_chunk_id=row["chunk_id"],
                    original_text=row["text"],
                    token_count=len(row["text"].split()),
                    page_start=1,
                    page_end=1,
                    chunking_provider="imported",
                ))
            created += 1

        if dry_run:
            print(f"\ndry run: would create {created}, skip {skipped} already present")
            return
        await session.commit()
        print(f"\ncreated {created} documents, skipped {skipped} already present")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="collection to read from")
    parser.add_argument("--instance", default=settings.DEFAULT_INSTANCE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        await import_collection(args.source, args.dry_run, args.instance)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
