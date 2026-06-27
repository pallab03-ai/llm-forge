"""Authentication API routes.

Endpoints:
- `POST /api/v1/auth/register` — create a new user, return JWT.
- `POST /api/v1/auth/login`    — exchange credentials for a JWT.
- `GET  /api/v1/auth/me`       — return the current authenticated user.

Per engineering guardrails:
- Routes contain NO business logic; they delegate to `AuthService`.
- All responses use the `{success, data}` / `{success, error}` envelope.
- Domain errors (`AuthError`) are translated to the envelope by the
  global exception handler registered in `app.main`.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, CurrentUser
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import SuccessResponse
from app.services.auth_service import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
)


router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _token_bundle_to_response(bundle) -> TokenResponse:
    return TokenResponse(
        access_token=bundle.access_token,
        token_type=bundle.token_type,
        expires_in=bundle.expires_in,
        user=UserResponse.model_validate(bundle.user),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=SuccessResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: RegisterRequest,
    auth_service: AuthServiceDep,
) -> SuccessResponse[TokenResponse]:
    """Create a new user account and return an access token.

    Raises:
        UserAlreadyExistsError: propagated to the global handler.
    """
    bundle = await auth_service.register(payload)
    return SuccessResponse[TokenResponse](
        data=_token_bundle_to_response(bundle)
    )


@router.post(
    "/login",
    response_model=SuccessResponse[TokenResponse],
    summary="Authenticate and obtain an access token",
)
async def login(
    payload: LoginRequest,
    auth_service: AuthServiceDep,
) -> SuccessResponse[TokenResponse]:
    """Exchange email + password for a JWT access token.

    Raises:
        InvalidCredentialsError: propagated to the global handler.
    """
    bundle = await auth_service.login(payload.email, payload.password)
    return SuccessResponse[TokenResponse](
        data=_token_bundle_to_response(bundle)
    )


@router.get(
    "/me",
    response_model=SuccessResponse[UserResponse],
    summary="Get the currently authenticated user",
)
async def me(current_user: CurrentUser) -> SuccessResponse[UserResponse]:
    """Return the user resolved from the bearer token."""
    return SuccessResponse[UserResponse](
        data=UserResponse.model_validate(current_user)
    )
