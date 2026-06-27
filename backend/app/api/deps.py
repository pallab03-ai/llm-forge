"""Shared FastAPI dependencies.

Wires infrastructure (DB session, current user, services) into request
handlers. Domain errors raised here surface via the global handler in
``app.main``.
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


DBSession = Annotated[AsyncSession, Depends(get_db)]


# auto_error=False so we can raise our own domain error and let the
# global handler emit the envelope.
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_auth_service(session: DBSession) -> AuthService:
    return AuthService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_storage_service() -> LocalStorageService:
    return LocalStorageService(settings.LOCAL_STORAGE_PATH)


StorageServiceDep = Annotated[LocalStorageService, Depends(get_storage_service)]


def get_validation_service() -> ValidationService:
    return ValidationService()


ValidationServiceDep = Annotated[ValidationService, Depends(get_validation_service)]


def get_dataset_repository(session: DBSession) -> DatasetRepository:
    return DatasetRepository(session)


DatasetRepositoryDep = Annotated[DatasetRepository, Depends(get_dataset_repository)]


def get_dataset_service(
    repository: DatasetRepositoryDep,
    storage: StorageServiceDep,
    validator: ValidationServiceDep,
) -> DatasetService:
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
    """Resolve the current user from the bearer token.

    Raises MissingTokenError / InvalidTokenError; both surface via the
    global exception handler.
    """
    if credentials is None or not credentials.credentials:
        raise MissingTokenError()

    return await auth_service.get_user_by_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


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
