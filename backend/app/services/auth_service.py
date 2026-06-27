"""Authentication service.

Encapsulates all business logic for registration, login, and current-user
lookup. API routes MUST delegate to this service rather than touching the
repository or session directly.

Per engineering guardrails:
- Business logic MUST NOT live in API routes.
- Passwords are hashed with bcrypt before persistence.
- JWT tokens expire after 24 hours.
"""

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


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Base class for authentication-related errors."""

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


class InactiveUserError(AuthError):
    http_status = 403
    code = "inactive_user"


class InvalidTokenError(AuthError):
    http_status = 401
    code = "invalid_token"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TokenBundle:
    """Result of a successful authentication operation."""

    access_token: str
    token_type: str
    expires_in: int
    user: User


class AuthService:
    """Async authentication service.

    A new instance is created per request via the `get_auth_service`
    dependency, sharing the request-scoped `AsyncSession`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def register(self, payload: RegisterRequest) -> TokenBundle:
        """Register a new user and return an access token.

        Raises:
            UserAlreadyExistsError: if email or username is already taken.
        """
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
        """Authenticate a user by email + password.

        Raises:
            InvalidCredentialsError: if the credentials are wrong.
        """
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            # Use the same error for both cases to avoid user enumeration.
            raise InvalidCredentialsError("Invalid email or password")

        return self._build_token_bundle(user)

    async def get_user_by_token(self, token: str) -> User:
        """Resolve a JWT access token to the corresponding `User`.

        Raises:
            InvalidTokenError: if the token is invalid or the user no
                longer exists.
        """
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

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_token_bundle(self, user: User) -> TokenBundle:
        token = create_access_token(user.id, role=user.role.value)
        return TokenBundle(
            access_token=token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user,
        )
