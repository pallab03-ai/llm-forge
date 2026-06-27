"""Authentication service: registration, login, current-user lookup."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.auth import RegisterRequest


class AuthError(Exception):
    http_status: int = 400
    code: str = "auth_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UserAlreadyExistsError(AuthError):
    http_status = 409
    code = "user_already_exists"


class InvalidCredentialsError(AuthError):
    http_status = 401
    code = "invalid_credentials"


class InvalidTokenError(AuthError):
    http_status = 401
    code = "invalid_token"


@dataclass(slots=True)
class TokenBundle:
    access_token: str
    token_type: str
    expires_in: int
    user: User


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def register(self, payload: RegisterRequest) -> TokenBundle:
        normalized_email = payload.email.lower()
        normalized_username = payload.username.lower()

        if await self._users.email_exists(normalized_email):
            raise UserAlreadyExistsError("Email is already registered")
        if await self._users.username_exists(normalized_username):
            raise UserAlreadyExistsError("Username is already taken")

        user = User(
            email=normalized_email,
            username=normalized_username,
            password_hash=hash_password(payload.password),
            role=payload.role or UserRole.USER,
        )
        await self._users.add(user)
        await self._session.commit()

        return self._build_token_bundle(user)

    async def login(self, email: str, password: str) -> TokenBundle:
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            # Same error either way — avoids user enumeration.
            raise InvalidCredentialsError("Invalid email or password")

        return self._build_token_bundle(user)

    async def get_user_by_token(self, token: str) -> User:
        try:
            payload = decode_access_token(token)
        except TokenError as exc:
            raise InvalidTokenError(str(exc)) from exc

        subject = payload.get("sub")
        if not subject:
            raise InvalidTokenError("Token missing subject")

        try:
            user_id = UUID(subject)
        except (ValueError, TypeError) as exc:
            raise InvalidTokenError("Token subject is not a valid UUID") from exc

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise InvalidTokenError("User no longer exists")

        return user

    def _build_token_bundle(self, user: User) -> TokenBundle:
        token = create_access_token(user.id, role=user.role.value)
        return TokenBundle(
            access_token=token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user,
        )
