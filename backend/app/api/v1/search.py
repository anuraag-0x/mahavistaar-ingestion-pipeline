"""
Search API Router.
Handles hybrid and semantic vector queries over indexed document chunks.
"""

from fastapi import APIRouter, HTTPException
from backend.app.schemas.search import SearchRequest, SearchResponse
from backend.app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["Search"])
search_service = SearchService()


@router.post("", response_model=SearchResponse)
async def execute_search(request: SearchRequest):
    try:
        return await search_service.search(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search execution failed: {str(e)}")
