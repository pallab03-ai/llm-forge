"""Common Pydantic schemas for API responses.

Standardizes the response envelope per engineering guardrails:
- Success: {"success": true, "data": {}}
- Error:   {"success": false, "error": {"code": "...", "message": "..."}}
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Error detail payload."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(default=None, description="Additional context")


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response envelope."""

    success: bool = True
    data: T
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    success: bool = False
    error: ErrorDetail


class HealthData(BaseModel):
    """Health check payload."""

    status: str = Field(default="healthy", description="Service health status")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Current environment")
