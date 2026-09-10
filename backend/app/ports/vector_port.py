"""
Vector Store Port (Interface for Qdrant / Vector Databases).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class VectorPoint(BaseModel):
    id: str
    vector: List[float]
    payload: Dict[str, Any]


class VectorSearchResult(BaseModel):
    id: str
    score: float
    payload: Dict[str, Any]


class VectorStorePort(ABC):
    @abstractmethod
    def ensure_collection(self, collection_name: str, vector_size: int = 1024) -> None:
        """Create collection and indexes if not exists."""
        pass

    @abstractmethod
    def upsert_points(self, collection_name: str, points: List[VectorPoint]) -> bool:
        """Upsert embedded points into the collection."""
        pass

    @abstractmethod
    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        """Perform semantic vector search."""
        pass

    @abstractmethod
    def delete_by_workflow_id(self, collection_name: str, workflow_id: str) -> int:
        """Delete all points belonging to a workflow/document."""
        pass
