"""Unified API response models."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""

    code: int = 0
    message: str = "success"
    data: T | None = None


class PagedData(BaseModel, Generic[T]):
    """Paginated data payload."""

    items: list[T]
    total: int
    pageNo: int
    pageSize: int


class PagedResponse(BaseModel, Generic[T]):
    """Paginated API response."""

    code: int = 0
    message: str = "success"
    data: PagedData[T]


def success(data: Any = None, message: str = "success") -> dict:
    """Create a success response dict."""
    return {"code": 0, "message": message, "data": data}


def paged(
    items: list,
    total: int,
    page_no: int,
    page_size: int,
    message: str = "success",
) -> dict:
    """Create a paginated response dict."""
    return {
        "code": 0,
        "message": message,
        "data": {
            "items": items,
            "total": total,
            "pageNo": page_no,
            "pageSize": page_size,
        },
    }
