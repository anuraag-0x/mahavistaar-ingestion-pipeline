"""
AI Provider Ports (OCR, Translation, and Embeddings Interfaces).
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel


class OcrPageResult(BaseModel):
    page_number: int
    markdown: str
    detected_language: Optional[str] = None


class TranslationPageResult(BaseModel):
    page_number: int
    original_text: str
    translated_text: str
    target_language: str
    provider: str
    model: str


class OCRPort(ABC):
    @abstractmethod
    async def process_pdf(self, file_bytes: bytes, file_name: str) -> List[OcrPageResult]:
        """Extract markdown text per page from PDF bytes."""
        pass


class TranslationPort(ABC):
    @abstractmethod
    async def translate_text(
        self, text: str, source_lang: Optional[str], target_lang: str
    ) -> str:
        """Translate markdown text to target language."""
        pass


class EmbeddingPort(ABC):
    @abstractmethod
    async def generate_embeddings(
        self, texts: List[str], is_query: bool = False
    ) -> List[List[float]]:
        """Generate dense vector embeddings for a list of texts."""
        pass
