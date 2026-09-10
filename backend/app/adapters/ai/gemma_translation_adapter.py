"""
Gemma / vLLM Multilingual Translation Adapter.
"""

from typing import Optional
import httpx

from backend.app.core.config import settings
from backend.app.ports.ai_ports import TranslationPort


class GemmaTranslationAdapter(TranslationPort):
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 60.0,
    ):
        self.base_url = (base_url or settings.VLLM_AGRINET_MODEL_URL).rstrip("/")
        self.model = model or settings.LLM_AGRINET_MODEL_NAME
        self.timeout = timeout_seconds

    async def translate_text(
        self, text: str, source_lang: Optional[str], target_lang: str = "en"
    ) -> str:
        if not text.strip():
            return ""

        prompt = (
            f"You are a professional translator. Translate the following agricultural/government text "
            f"from {source_lang or 'the source language'} to {target_lang}. "
            f"Preserve all markdown formatting, tables, lists, and numerical values.\n\n"
            f"Text:\n{text}\n\nTranslation:"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
