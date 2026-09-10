"""
Common Pydantic Schemas and Pagination Responses.
"""

from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class StandardResponse(BaseSchema):
    success: bool = True
    message: Optional[str] = None


class PaginatedResponse(BaseSchema, Generic[T]):
    items: List[T]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 1
