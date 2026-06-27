"""Shared FastAPI dependencies.

Per engineering guardrails:
- Dependencies are the only place where infrastructure (DB session,
  current user, services) is wired into request handlers.
- Domain errors raised here are translated to the standard envelope by
  the global exception handler registered in `app.main`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.repositories.dataset_repository import DatasetRepository
from app.services.auth_service import AuthService, InvalidTokenError
from app.services.dataset_service import DatasetService
from app.services.storage_service import LocalStorageService
from app.services.validation_service import ValidationService


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DBSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

# auto_error=False so we can raise our own domain error and let the
# global handler emit the envelope.
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_auth_service(session: DBSession) -> AuthService:
    """Return a request-scoped `AuthService`."""
    return AuthService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


# ---------------------------------------------------------------------------
# Dataset Service (Phase 2)
# ---------------------------------------------------------------------------


def get_storage_service() -> LocalStorageService:
    """Return a request-scoped `LocalStorageService`.

    The storage service is stateless apart from its configured root
    directory, so we instantiate it per request to keep the dependency
    graph explicit and easy to override in tests.
    """
    return LocalStorageService(settings.LOCAL_STORAGE_PATH)


StorageServiceDep = Annotated[LocalStorageService, Depends(get_storage_service)]


def get_validation_service() -> ValidationService:
    """Return a request-scoped `ValidationService`."""
    return ValidationService()


ValidationServiceDep = Annotated[ValidationService, Depends(get_validation_service)]


def get_dataset_repository(session: DBSession) -> DatasetRepository:
    """Return a request-scoped `DatasetRepository`."""
    return DatasetRepository(session)


DatasetRepositoryDep = Annotated[DatasetRepository, Depends(get_dataset_repository)]


def get_dataset_service(
    repository: DatasetRepositoryDep,
    storage: StorageServiceDep,
    validator: ValidationServiceDep,
) -> DatasetService:
    """Return a request-scoped `DatasetService`.

    Wires together the repository, storage service, and validation
    service. Keeping the wiring here (rather than inside the service
    constructor) makes it trivial to swap any dependency in tests.
    """
    return DatasetService(
        repository=repository,
        storage=storage,
        validator=validator,
    )


DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]


class MissingTokenError(Exception):
    """Raised when the `Authorization` header is missing or empty."""

    http_status = 401
    code = "missing_token"
    message = "Authorization header is required"


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    auth_service: AuthServiceDep,
) -> User:
    """Resolve the current authenticated user from the `Authorization` header.

    Raises:
        MissingTokenError: if the header is missing or empty.
        InvalidTokenError: if the token is invalid or the user no longer
            exists.
    """
    if credentials is None or not credentials.credentials:
        raise MissingTokenError()

    return await auth_service.get_user_by_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Settings (re-exported for convenience)
# ---------------------------------------------------------------------------

__all__ = [
    "DBSession",
    "AuthServiceDep",
    "CurrentUser",
    "MissingTokenError",
    "StorageServiceDep",
    "ValidationServiceDep",
    "DatasetRepositoryDep",
    "DatasetServiceDep",
    "settings",
]
