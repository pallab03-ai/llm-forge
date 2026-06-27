"""Authentication request / response schemas.

All schemas are Pydantic v2 models. They are the only types allowed to
cross the API boundary.

Per engineering guardrails:
- Typed request/response models are mandatory.
- Response envelope is `{success, data}` or `{success, error}`.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import settings
from app.models.user import UserRole


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Payload for `POST /api/v1/auth/register`."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(
        ...,
        description="Unique email address. Stored lowercased.",
    )
    username: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Unique username. Stored lowercased.",
    )
    password: str = Field(
        ...,
        min_length=settings.PASSWORD_MIN_LENGTH,
        max_length=settings.PASSWORD_MAX_LENGTH,
        description=(
            f"Plain-text password. Min length {settings.PASSWORD_MIN_LENGTH}."
        ),
    )
    role: UserRole | None = Field(
        default=None,
        description=(
            "Optional role. Defaults to 'user'. Only admins should be able "
            "to set 'admin' — Phase 1 allows it for bootstrap purposes."
        ),
    )

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        if not re.match(r"^[A-Za-z0-9_.-]+$", value):
            raise ValueError(
                "username may only contain letters, digits, '.', '-' and '_'"
            )
        return value.lower()


class LoginRequest(BaseModel):
    """Payload for `POST /api/v1/auth/login`."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., description="Registered email address.")
    password: str = Field(..., min_length=1, description="Plain-text password.")


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Public representation of a user (no password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    username: str
    role: UserRole
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    """Payload returned by successful login / register."""

    access_token: str = Field(..., description="Signed JWT access token.")
    token_type: str = Field(default="bearer", description="Token type.")
    expires_in: int = Field(
        ...,
        description="Token lifetime in seconds (default 24h = 86400).",
    )
    user: UserResponse
