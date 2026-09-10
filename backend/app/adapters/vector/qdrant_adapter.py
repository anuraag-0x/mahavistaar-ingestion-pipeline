"""
Qdrant Vector Database Adapter.
"""

import logging
from typing import Any, Dict, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from backend.app.core.config import settings
from backend.app.ports.vector_port import (
    VectorPoint,
    VectorSearchResult,
    VectorStorePort,
)

logger = logging.getLogger("mahavistaar.vectors")


class QdrantAdapter(VectorStorePort):
    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.url = url or settings.QDRANT_URL
        self.api_key = api_key or (settings.QDRANT_API_KEY or None)
        self.timeout = timeout or settings.QDRANT_TIMEOUT_SECONDS
        self.client = QdrantClient(
            url=self.url,
            api_key=self.api_key,
            timeout=self.timeout,
            check_compatibility=False,
        )

    def ensure_collection(self, collection_name: str, vector_size: int = 1024) -> None:
        collections = self.client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)
        if not exists:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=qmodels.VectorParams(
                    size=vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )
        # Payload indexes are also required when the collection already exists.
        # Qdrant rejects duplicate index creation, so existing indexes are safe.
        for field in ["doc_id", "type", "chunk_id", "source", "source_mr"]:
            try:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass

    def upsert_points(self, collection_name: str, points: List[VectorPoint]) -> bool:
        self.ensure_collection(collection_name, vector_size=len(points[0].vector) if points else 1024)
        qdrant_points = [
            qmodels.PointStruct(
                id=p.id,
                vector=p.vector,
                payload=p.payload,
            )
            for p in points
        ]
        self.client.upsert(collection_name=collection_name, points=qdrant_points)
        return True

    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        must_conditions = []
        if filters:
            for key, value in filters.items():
                if value is not None:
                    must_conditions.append(
                        qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))
                    )

        q_filter = qmodels.Filter(must=must_conditions) if must_conditions else None

        results = self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            query_filter=q_filter,
            with_payload=True,
        ).points

        return [
            VectorSearchResult(
                id=str(r.id),
                score=float(r.score),
                payload=r.payload or {},
            )
            for r in results
        ]

    def _document_filter(self, document_id: str) -> qmodels.Filter:
        return qmodels.Filter(
            must=[qmodels.FieldCondition(key="doc_id", match=qmodels.MatchValue(value=document_id))]
        )

    def count_by_document_id(self, collection_name: str, document_id: str) -> int:
        """How many points this document currently has in the collection."""
        try:
            return int(
                self.client.count(
                    collection_name=collection_name,
                    count_filter=self._document_filter(document_id),
                    exact=True,
                ).count
            )
        except Exception as exc:
            logger.warning(
                "could not count points | collection=%s doc_id=%s | %s",
                collection_name, document_id, exc,
            )
            return 0

    def delete_by_document_id(self, collection_name: str, document_id: str) -> int:
        """Remove every point belonging to a document. Returns how many went.

        Points are matched on the `doc_id` payload key, which is what the
        indexer writes. The previous implementation filtered on `workflow_id`,
        a key that appears in no payload, so it matched nothing while reporting
        success.
        """
        removed = self.count_by_document_id(collection_name, document_id)
        if not removed:
            logger.info(
                "nothing to remove | collection=%s doc_id=%s", collection_name, document_id
            )
            return 0
        self.client.delete(
            collection_name=collection_name,
            points_selector=qmodels.FilterSelector(filter=self._document_filter(document_id)),
            wait=True,
        )
        logger.info(
            "removed %d points | collection=%s doc_id=%s", removed, collection_name, document_id
        )
        return removed

    def delete_document_points_except(
        self, collection_name: str, document_id: str, keep_ids: list[str]
    ) -> int:
        """Drop the document's points that the latest index run did not write.

        Re-indexing an edited document rewrites each chunk under the same point
        ID, so an edit updates in place. Chunks that were removed or excluded
        since the last run have no new point to overwrite them and would stay in
        the index as stale copies. Deleting after the upsert rather than before
        it means the document is never briefly absent from search.
        """
        must_not = [qmodels.HasIdCondition(has_id=list(keep_ids))] if keep_ids else []
        selector = qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="doc_id", match=qmodels.MatchValue(value=document_id))],
                must_not=must_not,
            )
        )
        before = self.count_by_document_id(collection_name, document_id)
        self.client.delete(collection_name=collection_name, points_selector=selector, wait=True)
        removed = before - self.count_by_document_id(collection_name, document_id)
        if removed:
            logger.info(
                "removed %d stale points | collection=%s doc_id=%s",
                removed, collection_name, document_id,
            )
        return removed

    def delete_by_workflow_id(self, collection_name: str, workflow_id: str) -> int:
        """Kept for the port interface. Points carry no workflow id, so callers
        must use delete_by_document_id instead."""
        raise NotImplementedError(
            "Vector points are keyed by document_id, not workflow_id. "
            "Use delete_by_document_id."
        )
