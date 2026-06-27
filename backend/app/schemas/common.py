"""Common Pydantic schemas for the standard response envelope.

- Success: ``{"success": true, "data": ...}``
- Error:   ``{"success": false, "error": {"code", "message"}}``
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T


class HealthData(BaseModel):
    status: str = Field(default="healthy", description="Service health status")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Current environment")
