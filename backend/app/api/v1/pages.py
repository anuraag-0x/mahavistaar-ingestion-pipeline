"""
Pages API Router.
Handles page-level markdown viewing, OCR editing, and multilingual translations.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.schemas.page import (
    PageListResponse,
    PageResponse,
    PageUpdateOcrRequest,
    PageUpdateTranslationRequest,
)
from backend.app.services.page_service import PageService

router = APIRouter(prefix="/pages", tags=["Pages"])


@router.get("/document/{workflow_id}", response_model=PageListResponse)
async def get_document_pages(
    workflow_id: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    pages, total = await PageService.get_pages_for_document(db, workflow_id, limit, offset)
    return PageListResponse(
        pages=[PageResponse.model_validate(p) for p in pages],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{workflow_id}/{page_number}", response_model=PageResponse)
async def get_page(workflow_id: str, page_number: int, db: AsyncSession = Depends(get_db)):
    page = await PageService.get_page(db, workflow_id, page_number)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse.model_validate(page)


@router.patch("/{workflow_id}/{page_number}/ocr", response_model=PageResponse)
async def update_page_ocr(
    workflow_id: str,
    page_number: int,
    data: PageUpdateOcrRequest,
    db: AsyncSession = Depends(get_db),
):
    page = await PageService.update_page_ocr(db, workflow_id, page_number, data)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse.model_validate(page)


@router.patch("/{workflow_id}/{page_number}/translation", response_model=PageResponse)
async def update_page_translation(
    workflow_id: str,
    page_number: int,
    data: PageUpdateTranslationRequest,
    db: AsyncSession = Depends(get_db),
):
    page = await PageService.update_page_translation(db, workflow_id, page_number, data)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse.model_validate(page)
