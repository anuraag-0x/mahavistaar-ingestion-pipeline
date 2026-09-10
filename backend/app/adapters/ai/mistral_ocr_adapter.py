"""
Mistral OCR API Adapter.
Extracts markdown text from PDF documents using Mistral Cloud OCR.
"""

import base64
import logging
from typing import List, Optional
import httpx

from backend.app.core.config import settings

logger = logging.getLogger("mahavistaar.ocr")
from backend.app.ports.ai_ports import OCRPort, OcrPageResult


class MistralOCRAdapter(OCRPort):
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        self.api_key = api_key or settings.MISTRAL_API_KEY
        self.api_url = api_url or settings.MISTRAL_OCR_API_URL
        self.model = model or getattr(settings, "MISTRAL_OCR_MODEL", settings.OCR_MODEL)
        self.timeout = timeout_seconds or settings.OCR_REQUEST_TIMEOUT_SECONDS

    async def process_pdf(self, file_bytes: bytes, file_name: str) -> List[OcrPageResult]:
        if not self.api_key:
            raise RuntimeError(
                "No Mistral API key is configured. Set MISTRAL_API_KEY in the root .env."
            )
        if not file_bytes:
            raise RuntimeError(f"'{file_name}' is empty, there is nothing to extract.")

        # The payload always claimed application/pdf regardless of what was
        # handed in, so a Word or image upload reached Mistral wearing the wrong
        # content type and came back as an unexplained 400. Check it here, where
        # we can say which file and which type actually caused it.
        if not file_bytes.startswith(b"%PDF-"):
            signature = file_bytes[:8]
            raise RuntimeError(
                f"'{file_name}' is not a PDF, so text extraction cannot run on it. "
                f"The file starts with {signature!r}"
                + (" which is a ZIP container, typical of .docx, .xlsx and .pptx files."
                   if signature.startswith(b"PK") else ".")
                + " Convert the file to PDF before uploading it."
            )

        base64_doc = base64.b64encode(file_bytes).decode("utf-8")
        payload = {
            "model": self.model,
            "document": {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{base64_doc}",
            },
            "include_image_base64": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info(
            "OCR request | file=%s bytes=%d model=%s url=%s",
            file_name, len(file_bytes), self.model, self.api_url,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(self.api_url, json=payload, headers=headers)
            except httpx.RequestError as exc:
                logger.error("OCR unreachable | file=%s url=%s | %s", file_name, self.api_url, exc)
                raise RuntimeError(
                    f"Could not reach the OCR service at {self.api_url}: {exc}"
                ) from exc

            # raise_for_status() throws away the response body, which is the only
            # place the provider explains itself. Read it before raising.
            if response.status_code >= 400:
                detail = response.text.strip()
                logger.error(
                    "OCR rejected | file=%s status=%s | %s",
                    file_name, response.status_code, detail[:1200] or "(empty body)",
                )
                raise RuntimeError(
                    f"OCR failed for '{file_name}' with HTTP {response.status_code}: "
                    f"{detail[:600] or 'the provider returned no explanation'}"
                )

            data = response.json()
            results: List[OcrPageResult] = []
            for page in data.get("pages", []):
                results.append(
                    OcrPageResult(
                        page_number=page.get("index", 0) + 1,
                        markdown=page.get("markdown", ""),
                        detected_language=None,
                    )
                )
            logger.info("OCR complete | file=%s pages=%d", file_name, len(results))
            return results
