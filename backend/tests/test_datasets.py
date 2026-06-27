"""Tests for the Dataset Service API.

Covers:
- Upload (CSV, JSON, JSONL)
- Validation (schema, duplicates, empty file)
- Listing, detail, versions, statistics
- Soft delete
- Auth required
"""

from __future__ import annotations

import io
import json

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _csv_bytes(rows: list[dict]) -> bytes:
    """Build CSV bytes from a list of dicts."""
    if not rows:
        return b""
    headers = list(rows[0].keys())
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row.get(h, "")) for h in headers))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _json_bytes(records: list[dict]) -> bytes:
    return json.dumps(records).encode("utf-8")


def _jsonl_bytes(records: list[dict]) -> bytes:
    return ("\n".join(json.dumps(r) for r in records) + "\n").encode("utf-8")


async def _register_and_login(client: AsyncClient) -> dict:
    """Register a user and return auth headers."""
    payload = {
        "email": "owner@example.com",
        "username": "owner",
        "password": "StrongPass123!",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict:
    return await _register_and_login(client)


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_csv_dataset_success(client: AsyncClient, auth_headers: dict):
    rows = [
        {"instruction": "What is 2+2?", "response": "4"},
        {"instruction": "What is 3+3?", "response": "6"},
    ]
    files = {"file": ("train.csv", _csv_bytes(rows), "text/csv")}
    data = {
        "name": "math-qa",
        "dataset_type": "instruction_tuning",
        "format": "csv",
        "description": "Simple math",
    }
    resp = await client.post(
        "/api/v1/datasets",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is True
    payload = body["data"]
    assert payload["name"] == "math-qa"
    assert payload["status"] == "ready"
    assert len(payload["versions"]) == 1
    assert payload["versions"][0]["version_number"] == 1
    assert payload["versions"][0]["record_count"] == 2


@pytest.mark.asyncio
async def test_upload_json_dataset_success(client: AsyncClient, auth_headers: dict):
    records = [
        {"question": "Capital of France?", "answer": "Paris"},
        {"question": "Capital of Japan?", "answer": "Tokyo"},
    ]
    files = {"file": ("qa.json", _json_bytes(records), "application/json")}
    data = {
        "name": "geo-qa",
        "dataset_type": "qa",
        "format": "json",
    }
    resp = await client.post(
        "/api/v1/datasets",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["data"]["status"] == "ready"
    assert body["data"]["versions"][0]["record_count"] == 2


@pytest.mark.asyncio
async def test_upload_jsonl_dataset_success(client: AsyncClient, auth_headers: dict):
    records = [
        {"messages": [{"role": "user", "content": "Hi"}]},
        {"messages": [{"role": "user", "content": "Hello"}]},
    ]
    files = {"file": ("chat.jsonl", _jsonl_bytes(records), "application/x-jsonlines")}
    data = {
        "name": "chat-data",
        "dataset_type": "chat",
        "format": "jsonl",
    }
    resp = await client.post(
        "/api/v1/datasets",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["data"]["status"] == "ready"


@pytest.mark.asyncio
async def test_upload_duplicate_name_returns_409(
    client: AsyncClient, auth_headers: dict
):
    rows = [{"instruction": "Q", "response": "A"}]
    files = {"file": ("a.csv", _csv_bytes(rows), "text/csv")}
    data = {
        "name": "dup-name",
        "dataset_type": "instruction_tuning",
        "format": "csv",
    }
    r1 = await client.post(
        "/api/v1/datasets", files=files, data=data, headers=auth_headers
    )
    assert r1.status_code == 201

    files2 = {"file": ("b.csv", _csv_bytes(rows), "text/csv")}
    r2 = await client.post(
        "/api/v1/datasets", files=files2, data=data, headers=auth_headers
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "DATASET_NAME_EXISTS"


@pytest.mark.asyncio
async def test_upload_missing_required_column_marks_failed(
    client: AsyncClient, auth_headers: dict
):
    # Missing 'response' column for instruction_tuning
    rows = [{"instruction": "Q"}]
    files = {"file": ("bad.csv", _csv_bytes(rows), "text/csv")}
    data = {
        "name": "bad-schema",
        "dataset_type": "instruction_tuning",
        "format": "csv",
    }
    resp = await client.post(
        "/api/v1/datasets",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["status"] == "failed"
    assert body["data"]["versions"][0]["record_count"] == 1


@pytest.mark.asyncio
async def test_upload_detects_within_file_duplicates(
    client: AsyncClient, auth_headers: dict
):
    rows = [
        {"instruction": "Q1", "response": "A1"},
        {"instruction": "Q1", "response": "A1"},  # duplicate
        {"instruction": "Q2", "response": "A2"},
    ]
    files = {"file": ("dup.csv", _csv_bytes(rows), "text/csv")}
    data = {
        "name": "with-dups",
        "dataset_type": "instruction_tuning",
        "format": "csv",
    }
    resp = await client.post(
        "/api/v1/datasets",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["versions"][0]["duplicate_count"] == 1
    assert body["data"]["versions"][0]["record_count"] == 3


@pytest.mark.asyncio
async def test_upload_empty_file_marks_failed(
    client: AsyncClient, auth_headers: dict
):
    files = {"file": ("empty.csv", b"", "text/csv")}
    data = {
        "name": "empty-ds",
        "dataset_type": "instruction_tuning",
        "format": "csv",
    }
    resp = await client.post(
        "/api/v1/datasets",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["status"] == "failed"


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    rows = [{"instruction": "Q", "response": "A"}]
    files = {"file": ("a.csv", _csv_bytes(rows), "text/csv")}
    data = {
        "name": "no-auth",
        "dataset_type": "instruction_tuning",
        "format": "csv",
    }
    resp = await client.post("/api/v1/datasets", files=files, data=data)
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List / detail / versions / statistics
# ---------------------------------------------------------------------------


async def _create_dataset(
    client: AsyncClient, headers: dict, name: str = "ds-list"
) -> dict:
    rows = [{"instruction": "Q", "response": "A"}]
    files = {"file": ("a.csv", _csv_bytes(rows), "text/csv")}
    data = {
        "name": name,
        "dataset_type": "instruction_tuning",
        "format": "csv",
    }
    resp = await client.post(
        "/api/v1/datasets", files=files, data=data, headers=headers
    )
    assert resp.status_code == 201
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_list_datasets(client: AsyncClient, auth_headers: dict):
    await _create_dataset(client, auth_headers, "list-1")
    await _create_dataset(client, auth_headers, "list-2")
    resp = await client.get("/api/v1/datasets", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["total"] >= 2


@pytest.mark.asyncio
async def test_get_dataset_detail(client: AsyncClient, auth_headers: dict):
    created = await _create_dataset(client, auth_headers, "detail-1")
    dataset_id = created["id"]
    resp = await client.get(
        f"/api/v1/datasets/{dataset_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["id"] == dataset_id
    assert len(body["data"]["versions"]) == 1


@pytest.mark.asyncio
async def test_get_dataset_not_found(client: AsyncClient, auth_headers: dict):
    """Phase 2.1: With ownership enforcement, a dataset the user does
    not own (or that does not exist) surfaces as 403 to avoid leaking
    existence of other users' datasets.
    """
    import uuid

    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/datasets/{fake_id}", headers=auth_headers
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "DATASET_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_upload_new_version(client: AsyncClient, auth_headers: dict):
    created = await _create_dataset(client, auth_headers, "versioned")
    dataset_id = created["id"]

    rows = [
        {"instruction": "Q1", "response": "A1"},
        {"instruction": "Q2", "response": "A2"},
    ]
    files = {"file": ("v2.csv", _csv_bytes(rows), "text/csv")}
    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        files=files,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["data"]["versions"]) == 2
    # Newest first
    assert body["data"]["versions"][0]["version_number"] == 2
    assert body["data"]["versions"][1]["version_number"] == 1


@pytest.mark.asyncio
async def test_list_versions(client: AsyncClient, auth_headers: dict):
    created = await _create_dataset(client, auth_headers, "versions-list")
    dataset_id = created["id"]
    resp = await client.get(
        f"/api/v1/datasets/{dataset_id}/versions", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1


@pytest.mark.asyncio
async def test_get_statistics(client: AsyncClient, auth_headers: dict):
    created = await _create_dataset(client, auth_headers, "stats-ds")
    dataset_id = created["id"]
    resp = await client.get(
        f"/api/v1/datasets/{dataset_id}/statistics", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total_versions"] == 1
    assert body["data"]["latest_version"] == 1
    assert body["data"]["total_records"] == 1


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_delete_dataset(client: AsyncClient, auth_headers: dict):
    created = await _create_dataset(client, auth_headers, "to-delete")
    dataset_id = created["id"]

    resp = await client.delete(
        f"/api/v1/datasets/{dataset_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Subsequent GET should 403 (Phase 2.1: ownership-scoped, soft-deleted
    # datasets are not visible to their owner either — we surface 403 to
    # avoid leaking existence).
    resp2 = await client.get(
        f"/api/v1/datasets/{dataset_id}", headers=auth_headers
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "DATASET_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_403(
    client: AsyncClient, auth_headers: dict
):
    """Phase 2.1: Deleting a dataset the user does not own (or that does
    not exist) surfaces as 403 to avoid leaking existence.
    """
    import uuid

    fake_id = uuid.uuid4()
    resp = await client.delete(
        f"/api/v1/datasets/{fake_id}", headers=auth_headers
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "DATASET_ACCESS_DENIED"


# ---------------------------------------------------------------------------
# Phase 2.1: Ownership enforcement (cross-user access blocked)
# ---------------------------------------------------------------------------


async def _register_user(
    client: AsyncClient, email: str, username: str
) -> dict:
    """Register a new user and return auth headers."""
    payload = {
        "email": email,
        "username": username,
        "password": "StrongPass123!",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_other_user_cannot_get_dataset_detail(client: AsyncClient):
    """User B cannot GET a dataset owned by User A → 403."""
    owner_headers = await _register_user(
        client, "owner-a@example.com", "owner-a"
    )
    other_headers = await _register_user(
        client, "other-b@example.com", "other-b"
    )

    created = await _create_dataset(client, owner_headers, "owner-only")
    dataset_id = created["id"]

    resp = await client.get(
        f"/api/v1/datasets/{dataset_id}", headers=other_headers
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "DATASET_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_other_user_cannot_delete_dataset(client: AsyncClient):
    """User B cannot DELETE a dataset owned by User A → 403."""
    owner_headers = await _register_user(
        client, "owner-del@example.com", "owner-del"
    )
    other_headers = await _register_user(
        client, "other-del@example.com", "other-del"
    )

    created = await _create_dataset(client, owner_headers, "do-not-delete")
    dataset_id = created["id"]

    resp = await client.delete(
        f"/api/v1/datasets/{dataset_id}", headers=other_headers
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "DATASET_ACCESS_DENIED"

    # Verify dataset still exists for the real owner
    verify = await client.get(
        f"/api/v1/datasets/{dataset_id}", headers=owner_headers
    )
    assert verify.status_code == 200


@pytest.mark.asyncio
async def test_other_user_cannot_upload_version(client: AsyncClient):
    """User B cannot POST a new version to User A's dataset → 403."""
    owner_headers = await _register_user(
        client, "owner-ver@example.com", "owner-ver"
    )
    other_headers = await _register_user(
        client, "other-ver@example.com", "other-ver"
    )

    created = await _create_dataset(client, owner_headers, "version-locked")
    dataset_id = created["id"]

    rows = [{"instruction": "Q", "response": "A"}]
    files = {"file": ("v2.csv", _csv_bytes(rows), "text/csv")}
    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        files=files,
        headers=other_headers,
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "DATASET_ACCESS_DENIED"

    # Verify version count is still 1 for the real owner
    versions = await client.get(
        f"/api/v1/datasets/{dataset_id}/versions", headers=owner_headers
    )
    assert versions.status_code == 200
    assert len(versions.json()["data"]) == 1


@pytest.mark.asyncio
async def test_other_user_cannot_list_versions(client: AsyncClient):
    """User B cannot GET versions of User A's dataset → 403."""
    owner_headers = await _register_user(
        client, "owner-lv@example.com", "owner-lv"
    )
    other_headers = await _register_user(
        client, "other-lv@example.com", "other-lv"
    )

    created = await _create_dataset(client, owner_headers, "versions-private")
    dataset_id = created["id"]

    resp = await client.get(
        f"/api/v1/datasets/{dataset_id}/versions", headers=other_headers
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "DATASET_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_list_datasets_is_scoped_to_owner(client: AsyncClient):
    """User B's list endpoint must NOT include User A's datasets."""
    owner_headers = await _register_user(
        client, "owner-scope@example.com", "owner-scope"
    )
    other_headers = await _register_user(
        client, "other-scope@example.com", "other-scope"
    )

    await _create_dataset(client, owner_headers, "owner-private-1")
    await _create_dataset(client, owner_headers, "owner-private-2")
    await _create_dataset(client, other_headers, "other-private-1")

    resp = await client.get("/api/v1/datasets", headers=other_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    names = {item["name"] for item in items}
    assert "other-private-1" in names
    assert "owner-private-1" not in names
    assert "owner-private-2" not in names


# ---------------------------------------------------------------------------
# Phase 2.1: Upload size protection (50 MB MVP limit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_within_size_limit_succeeds(
    client: AsyncClient, auth_headers: dict
):
    """A small file well under the 50 MB limit must upload successfully."""
    rows = [{"instruction": "Q", "response": "A"}]
    files = {"file": ("small.csv", _csv_bytes(rows), "text/csv")}
    data = {
        "name": "size-ok",
        "dataset_type": "instruction_tuning",
        "format": "csv",
    }
    resp = await client.post(
        "/api/v1/datasets",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_upload_oversized_file_rejected_with_413(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """A file whose declared size exceeds the limit must be rejected with 413
    BEFORE the body is read into memory."""
    from app.api.v1 import datasets as datasets_module
    from app.core.config import settings

    # Force the limit very low so we don't have to allocate a real 50 MB+ file.
    # The CSV payload below is ~25 bytes, so we set the limit to 10 bytes to
    # guarantee the size check triggers.
    monkeypatch.setattr(settings, "DATASET_MAX_FILE_SIZE_BYTES", 10)

    rows = [{"instruction": "Q", "response": "A"}]
    payload = _csv_bytes(rows)  # ~25 bytes, well over the 10-byte limit
    files = {"file": ("big.csv", payload, "text/csv")}
    data = {
        "name": "size-too-big",
        "dataset_type": "instruction_tuning",
        "format": "csv",
    }

    # Spy on UploadFile.read to prove it is never called for oversized uploads.
    read_called = {"value": False}

    original_read = datasets_module.UploadFile.read

    async def spy_read(self, *args, **kwargs):
        read_called["value"] = True
        return await original_read(self, *args, **kwargs)

    monkeypatch.setattr(datasets_module.UploadFile, "read", spy_read)

    resp = await client.post(
        "/api/v1/datasets",
        files=files,
        data=data,
        headers=auth_headers,
    )
    assert resp.status_code == 413, resp.text
    assert resp.json()["error"]["code"] == "DATASET_FILE_TOO_LARGE"
    # The size check must short-circuit before the body is read.
    assert read_called["value"] is False


@pytest.mark.asyncio
async def test_upload_version_oversized_rejected_with_413(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """Same protection applies to version uploads."""
    from app.api.v1 import datasets as datasets_module
    from app.core.config import settings

    monkeypatch.setattr(settings, "DATASET_MAX_FILE_SIZE_BYTES", 10)

    # Create the dataset FIRST (with the limit temporarily raised so the
    # initial upload succeeds), then lower the limit for the version
    # upload that should be rejected.
    monkeypatch.setattr(settings, "DATASET_MAX_FILE_SIZE_BYTES", 50 * 1024 * 1024)
    created = await _create_dataset(client, auth_headers, "size-version-ds")
    dataset_id = created["id"]

    # Now lower the limit so the version upload is rejected.
    monkeypatch.setattr(settings, "DATASET_MAX_FILE_SIZE_BYTES", 10)

    rows = [{"instruction": "Q", "response": "A"}]
    payload = _csv_bytes(rows)  # ~25 bytes, well over the 10-byte limit
    files = {"file": ("v2.csv", payload, "text/csv")}

    read_called = {"value": False}
    original_read = datasets_module.UploadFile.read

    async def spy_read(self, *args, **kwargs):
        read_called["value"] = True
        return await original_read(self, *args, **kwargs)

    monkeypatch.setattr(datasets_module.UploadFile, "read", spy_read)

    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        files=files,
        headers=auth_headers,
    )
    assert resp.status_code == 413, resp.text
    assert resp.json()["error"]["code"] == "DATASET_FILE_TOO_LARGE"
    assert read_called["value"] is False
