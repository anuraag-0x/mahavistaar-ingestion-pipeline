"""
Search Domain Service.
Orchestrates vector embedding generation and Qdrant semantic/hybrid search.
"""

import time
from typing import List, Optional
from backend.app.adapters.ai.hf_embedding_adapter import HFEmbeddingAdapter
from backend.app.adapters.vector.qdrant_adapter import QdrantAdapter
from backend.app.core.config import settings
from backend.app.ports.ai_ports import EmbeddingPort
from backend.app.ports.vector_port import VectorStorePort
from backend.app.schemas.search import SearchRequest, SearchResponse, SearchResultItem


class SearchService:
    def __init__(
        self,
        embedding_port: Optional[EmbeddingPort] = None,
        vector_port: Optional[VectorStorePort] = None,
    ):
        self.embedding_port = embedding_port or HFEmbeddingAdapter()
        self.vector_port = vector_port or QdrantAdapter()

    async def search(self, req: SearchRequest) -> SearchResponse:
        start_time = time.time()

        # 1. Generate query embedding
        query_vectors = await self.embedding_port.generate_embeddings([req.query], is_query=True)
        query_vector = query_vectors[0] if query_vectors else []

        # 2. Build filters
        filters = {}
        if req.type:
            filters["type"] = req.type

        # 3. Query Qdrant
        results = self.vector_port.search(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            query_vector=query_vector,
            limit=req.limit,
            filters=filters,
        )

        # 4. Map results
        items: List[SearchResultItem] = []
        for r in results:
            payload = r.payload
            doc_id = payload.get("doc_id") or payload.get("document_id", "")
            workflow_id = payload.get("workflow_id") or doc_id
            items.append(
                SearchResultItem(
                    chunk_id=str(payload.get("chunk_id", r.id)),
                    workflow_id=workflow_id,
                    document_id=doc_id,
                    text=payload.get("text", ""),
                    score=r.score,
                    page_number=None,
                    scheme_code=None,
                    scheme_name=payload.get("name") or payload.get("name_en"),
                    instance=payload.get("instance"),
                    section_title=None,
                    metadata=payload,
                )
            )

        latency_ms = (time.time() - start_time) * 1000
        return SearchResponse(
            query=req.query,
            total_results=len(items),
            results=items,
            latency_ms=round(latency_ms, 2),
        )
