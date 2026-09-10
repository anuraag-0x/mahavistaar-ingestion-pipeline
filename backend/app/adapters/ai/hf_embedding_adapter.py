"""
Hugging Face Embedding Adapter.
Calls the standalone Hugging Face embedding microservice over standard HTTP.
"""

from typing import List, Optional
import httpx

from backend.app.core.config import settings
from backend.app.ports.ai_ports import EmbeddingPort


class HFEmbeddingAdapter(EmbeddingPort):
    def __init__(
        self,
        service_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        self.service_url = (service_url or settings.HF_EMBEDDING_SERVICE_URL).rstrip("/")
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.timeout = timeout_seconds

    async def generate_embeddings(
        self, texts: List[str], is_query: bool = False
    ) -> List[List[float]]:
        if not texts:
            return []

        # For e5 models, queries are prefixed with 'query: ' and passages with 'passage: '
        processed_texts = [
            f"query: {t}" if is_query else f"passage: {t}" for t in texts
        ]

        payload = {
            "input": processed_texts,
            "model": self.model_name,
            "encoding_format": "float",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.service_url}/v1/embeddings",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            # Extract embedding vectors sorted by index
            embeddings = [item["embedding"] for item in data["data"]]
            return embeddings
