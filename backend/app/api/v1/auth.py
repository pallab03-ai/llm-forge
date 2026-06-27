"""Authentication API routes.

Routes delegate entirely to ``AuthService``; domain errors are
translated to the response envelope by the global handler in
``app.main``.
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


def _token_bundle_to_response(bundle) -> TokenResponse:
    return TokenResponse(
        access_token=bundle.access_token,
        token_type=bundle.token_type,
        expires_in=bundle.expires_in,
        user=UserResponse.model_validate(bundle.user),
    )


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
    return SuccessResponse[UserResponse](
        data=UserResponse.model_validate(current_user)
    )
