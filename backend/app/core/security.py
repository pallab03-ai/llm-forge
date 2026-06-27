"""Password hashing (bcrypt via passlib) and JWT token management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


# bcrypt-only; `deprecated="auto"` lets future schemes coexist.
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not plain_password or not password_hash:
        return False
    try:
        return _pwd_context.verify(plain_password, password_hash)
    except (ValueError, TypeError):
        # Malformed hash or unsupported scheme.
        return False


class TokenError(Exception):
    """Raised when a JWT cannot be decoded or is otherwise invalid."""


def _build_claims(
    subject: str,
    extra: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    claims: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "type": "access",
    }
    if extra:
        claims.update(extra)
    return claims


def create_access_token(
    user_id: UUID,
    *,
    role: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    extra: dict[str, Any] = {}
    if role is not None:
        extra["role"] = role
    claims = _build_claims(str(user_id), extra=extra, expires_delta=expires_delta)
    return jwt.encode(
        claims,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
    except JWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("type") != "access":
        raise TokenError("Invalid token type")

    return payload
