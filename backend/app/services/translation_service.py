"""Self-contained translation service used by the native backend."""

import asyncio
import re
from typing import Any, Awaitable, Callable, Optional

import httpx
from lingua import LanguageDetectorBuilder

from backend.app.core.config import settings

SCRIPT_RANGES = {
    "hi": r"[\u0900-\u097f]", "bn": r"[\u0980-\u09ff]",
    "pa": r"[\u0a00-\u0a7f]", "gu": r"[\u0a80-\u0aff]",
    "or": r"[\u0b00-\u0b7f]", "ta": r"[\u0b80-\u0bff]",
    "te": r"[\u0c00-\u0c7f]", "kn": r"[\u0c80-\u0cff]",
    "ml": r"[\u0d00-\u0d7f]",
}

LANGUAGE_DETECTOR = LanguageDetectorBuilder.from_all_languages().with_minimum_relative_distance(0.15).build()


def detect_language(text: str) -> str:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "en"

    # Very short OCR fragments do not contain enough evidence for statistical
    # detection. Use the script only as a fallback for those fragments.
    if len(letters) < 20:
        counts = {language: len(re.findall(pattern, text)) for language, pattern in SCRIPT_RANGES.items()}
        language, count = max(counts.items(), key=lambda item: item[1])
        return language if count else "en"

    detected = LANGUAGE_DETECTOR.detect_language_of(text)
    if detected is None:
        return "unknown"
    code = detected.iso_code_639_1
    return code.name.lower() if code else detected.name.lower()


def clean_translation(text: str) -> str:
    return re.sub(r"^(?:Here is the .*?translation|Translation|Translated content)\s*:?\s*", "", text.strip(), flags=re.I | re.M)


async def _translate(text: str, source_language: str) -> str:
    prompt = f"Translate this text from {source_language} to English. Preserve markdown, tables, lists, numbers, and formatting. Return only the translation.\n\n{text}"
    if settings.LLM_PROVIDER.lower().strip() == "cerebras":
        endpoint = settings.CEREBRAS_BASE_URL.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {settings.CEREBRAS_API_KEY}"}
        payload = {
            "model": settings.CEREBRAS_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "top_p": 1,
            "max_completion_tokens": 8000,
            "stream": False,
        }
    else:
        endpoint = settings.VLLM_AGRINET_MODEL_URL.rstrip("/") + "/chat/completions"
        headers = {}
        payload = {
            "model": settings.LLM_AGRINET_MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 8000,
            "stream": False,
        }
    async with httpx.AsyncClient(timeout=300.0) as client:
        for attempt in range(settings.TRANSLATION_MAX_RETRIES):
            try:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                return clean_translation(response.json()["choices"][0]["message"]["content"])
            except Exception:
                if attempt == settings.TRANSLATION_MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(settings.TRANSLATION_RETRY_BASE_SECONDS * (2 ** attempt))
    raise RuntimeError("Translation failed")


async def translate_pages(
    pages: list[dict[str, Any]],
    progress_callback: Optional[Callable[[int, int, dict[str, Any]], Awaitable[None]]] = None,
) -> list[dict[str, Any]]:
    """Translate every page that needs it.

    Pages run concurrently, so ``progress_callback`` is called with the count
    finished so far, the total, and the page that just completed. Completion
    order is not page order, which is why the count is passed rather than
    inferred by the caller.
    """
    semaphore = asyncio.Semaphore(max(1, settings.TRANSLATION_PAGE_CONCURRENCY))
    total = len(pages)
    done = 0
    # asyncio.gather runs the coroutines on one event loop thread, so the
    # counter needs no lock, but the callback does need serialising.
    report_lock = asyncio.Lock()

    async def process(page: dict[str, Any]) -> dict[str, Any]:
        nonlocal done
        text = page.get("edited_markdown") or page.get("original_markdown") or ""
        language = detect_language(text)
        page["detected_language"] = language
        if language != "en" and text.strip():
            async with semaphore:
                page["translated_markdown"] = await _translate(text, language)
                page["translation_provider"] = settings.LLM_PROVIDER
                page["translation_model"] = settings.CEREBRAS_MODEL if settings.LLM_PROVIDER.lower().strip() == "cerebras" else settings.LLM_AGRINET_MODEL_NAME
                page["translation_target_language"] = "en"
        if progress_callback:
            async with report_lock:
                done += 1
                await progress_callback(done, total, page)
        return page

    return list(await asyncio.gather(*(process(page) for page in pages)))
