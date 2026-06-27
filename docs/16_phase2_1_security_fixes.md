# Phase 2.1 — Security Fixes (Dataset Service)

**Status:** ✅ Complete — 24/24 tests passing
**Scope:** Dataset ownership enforcement + upload size protection
**Date:** 2026-06-20

---

## 1. Files Modified

| # | File | Change |
|---|------|--------|
| 1 | `backend/app/core/config.py` | `DATASET_MAX_FILE_SIZE_BYTES` default tightened from 1 GB → 50 MB (52428800 bytes); env-overridable |
| 2 | `backend/app/repositories/dataset_repository.py` | Owner filtering on `list_active()` / `count_active()`; new `get_by_id_and_owner()`; `soft_delete()` accepts `owner_id`; `selectinload(Dataset.versions)` for eager loading |
| 3 | `backend/app/services/dataset_service.py` | New `DatasetAccessDeniedError`; all methods require `current_user_id: UUID`; use `get_by_id_and_owner`; raise `DatasetAccessDeniedError` on cross-tenant access; `session.refresh()` after commit to load server-generated `updated_at` |
| 4 | `backend/app/api/v1/datasets.py` | All 7 routes pass `current_user_id=current_user.id`; `_reject_if_too_large()` helper rejects oversized files BEFORE `await file.read()`; uses `HTTP_413_CONTENT_TOO_LARGE` with structured `{code, message}` detail |
| 5 | `backend/app/main.py` | Registered exception handlers for `DatasetError`, `DatasetNotFoundError`, `DatasetNameExistsError`, `DatasetValidationError`, `DatasetVersionNotFoundError`, `DatasetAccessDeniedError`, `StarletteHTTPException` — all emit the standard `{success, error}` envelope |
| 6 | `backend/tests/test_datasets.py` | +8 new tests (5 ownership + 3 size); helpers `_csv_bytes`, `_json_bytes`, `_jsonl_bytes`, `_register_and_login`, `_create_dataset`, `_register_user` |
| 7 | `backend/tests/conftest.py` | `AsyncClient` with `ASGITransport` (replaces sync `TestClient`); async `auth_headers_factory` |

---

## 2. Security Fixes Implemented

### 2.1 Dataset Ownership Enforcement

**Threat:** Any authenticated user could read, modify, or delete any other user's dataset by guessing/iterating UUIDs.

**Fix (defense-in-depth, 3 layers):**

1. **Repository layer** — `DatasetRepository` now accepts `owner_id` and filters at the SQL level:
   - `list_active(owner_id)` — only returns the caller's datasets
   - `get_by_id_and_owner(dataset_id, owner_id)` — returns `None` if the dataset doesn't exist OR isn't owned by the caller (no existence leak)
   - `soft_delete(dataset_id, owner_id)` — refuses to delete datasets not owned by the caller

2. **Service layer** — `DatasetService` requires `current_user_id: UUID` on every method and raises `DatasetAccessDeniedError` when the repository returns `None`. The service is the single chokepoint that translates "not found / not yours" into the right exception.

3. **API layer** — All 7 routes extract `current_user` via the `CurrentUser` dependency and pass `current_user.id` to the service.

**Response contract:**
- Non-owner access → **403 Forbidden** with `{"success": false, "error": {"code": "DATASET_ACCESS_DENIED", "message": "You do not have access to this dataset."}}`
- The message is intentionally generic — we do NOT distinguish between "dataset doesn't exist" and "dataset exists but isn't yours" to avoid leaking the existence of other users' datasets.

### 2.2 Upload Size Protection

**Threat:** A malicious or buggy client could upload a multi-GB file, causing the FastAPI worker to OOM.

**Fix (two-layer guard):**

1. **Route layer (pre-read OOM guard)** — `_reject_if_too_large(file)` checks `UploadFile.size` (populated by Starlette from the `Content-Length` header) BEFORE calling `await file.read()`. If the file exceeds `settings.DATASET_MAX_FILE_SIZE_BYTES`, it raises `HTTPException(413, detail={"code": "DATASET_FILE_TOO_LARGE", "message": "..."})` and the file body is never read into process memory.

2. **Service layer (authoritative check)** — The service also validates size after reading, as a defense against clients that omit `Content-Length` (chunked transfer encoding).

**Configuration:**
- Default: **50 MB** (52428800 bytes) — tightened from the previous 1 GB default
- Overridable via env var `DATASET_MAX_FILE_SIZE_BYTES`
- Comment in `config.py` documents the rationale: "Phase 2.1: tightened default to 50 MB to prevent OOM on large uploads."

**Response contract:**
- Oversized file → **413 Content Too Large** with `{"success": false, "error": {"code": "DATASET_FILE_TOO_LARGE", "message": "File is N bytes which exceeds the maximum allowed size of M bytes (X MB)."}}`

---

## 3. Tests Added

### 3.1 Ownership Tests (5)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_other_user_cannot_get_dataset_detail` | User B tries to GET User A's dataset | 403 |
| `test_other_user_cannot_delete_dataset` | User B tries to DELETE User A's dataset | 403 |
| `test_other_user_cannot_upload_version` | User B tries to POST a new version to User A's dataset | 403 |
| `test_other_user_cannot_list_versions` | User B tries to GET User A's dataset versions | 403 |
| `test_list_datasets_is_scoped_to_owner` | User A and User B each have datasets; each lists only their own | Only own datasets returned |

### 3.2 Upload Size Tests (3)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_upload_within_size_limit_succeeds` | Upload a small file (well under 50 MB) | 201 Created |
| `test_upload_oversized_file_rejected_with_413` | Upload a file > 50 MB | 413 with `DATASET_FILE_TOO_LARGE` code |
| `test_upload_version_oversized_rejected_with_413` | Upload an oversized new version | 413 with `DATASET_FILE_TOO_LARGE` code |

### 3.3 Test Infrastructure Fixes

- **`conftest.py`**: Migrated from sync `TestClient` to async `AsyncClient` with `ASGITransport` to match the async FastAPI app.
- **`dataset_service.py`**: Added `session.refresh()` after commit in `upload()` and `upload_version()` to load server-generated `updated_at` without triggering `MissingGreenlet`.
- **Test expectations**: Updated `test_delete_nonexistent_returns_403` to expect 403 (not 404) for non-owner access — consistent with the "no existence leak" policy.

---

## 4. Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.11.4, pytest-9.0.3
collected 24 items

tests/test_datasets.py::test_upload_csv_dataset_success PASSED           [  4%]
tests/test_datasets.py::test_upload_json_dataset_success PASSED          [  8%]
tests/test_datasets.py::test_upload_jsonl_dataset_success PASSED         [ 12%]
tests/test_datasets.py::test_upload_duplicate_name_returns_409 PASSED    [ 16%]
tests/test_datasets.py::test_upload_missing_required_column_marks_failed PASSED [ 20%]
tests/test_datasets.py::test_upload_detects_within_file_duplicates PASSED [ 25%]
tests/test_datasets.py::test_upload_empty_file_marks_failed PASSED       [ 29%]
tests/test_datasets.py::test_upload_requires_auth PASSED                 [ 33%]
tests/test_datasets.py::test_list_datasets PASSED                        [ 37%]
tests/test_datasets.py::test_get_dataset_detail PASSED                   [ 41%]
tests/test_datasets.py::test_get_dataset_not_found PASSED                [ 45%]
tests/test_datasets.py::test_upload_new_version PASSED                   [ 50%]
tests/test_datasets.py::test_list_versions PASSED                        [ 54%]
tests/test_datasets.py::test_get_statistics PASSED                       [ 58%]
tests/test_datasets.py::test_soft_delete_dataset PASSED                  [ 62%]
tests/test_datasets.py::test_delete_nonexistent_returns_403 PASSED       [ 66%]
tests/test_datasets.py::test_other_user_cannot_get_dataset_detail PASSED [ 70%]
tests/test_datasets.py::test_other_user_cannot_delete_dataset PASSED     [ 75%]
tests/test_datasets.py::test_other_user_cannot_upload_version PASSED     [ 79%]
tests/test_datasets.py::test_other_user_cannot_list_versions PASSED      [ 83%]
tests/test_datasets.py::test_list_datasets_is_scoped_to_owner PASSED     [ 87%]
tests/test_datasets.py::test_upload_within_size_limit_succeeds PASSED    [ 91%]
tests/test_datasets.py::test_upload_oversized_file_rejected_with_413 PASSED [ 95%]
tests/test_datasets.py::test_upload_version_oversized_rejected_with_413 PASSED [100%]

============================= 24 passed in 8.18s ==============================
```

**Result: 24 passed, 0 failed, 0 warnings.**

---

## 5. Production Readiness Reassessment

### Before Phase 2.1

| Dimension | Status |
|-----------|--------|
| Dataset ownership | ❌ Any authenticated user could access any dataset |
| Upload size | ❌ No limit — OOM risk on large uploads |
| Error envelope consistency | ⚠️ Some exceptions leaked as 500s |
| Test coverage | 16 tests, no ownership/size coverage |

### After Phase 2.1

| Dimension | Status |
|-----------|--------|
| Dataset ownership | ✅ Enforced at repo + service + API layers; 403 for non-owners |
| Upload size | ✅ 50 MB default, configurable, pre-read OOM guard |
| Error envelope consistency | ✅ All dataset exceptions mapped to standard `{success, error}` envelope |
| Test coverage | 24 tests including 5 ownership + 3 size scenarios |

### Remaining Gaps (Out of Scope for Phase 2.1)

These were explicitly excluded by the user and remain as future work:

1. **Streaming uploads** — Current implementation reads the full file into memory before validation. For files near the 50 MB limit this is acceptable; for larger limits, streaming would be needed.
2. **Version locking** — No mechanism to prevent concurrent version uploads to the same dataset (would need optimistic locking or a DB constraint).
3. **File hashing / deduplication** — No content-addressable storage; identical files are stored twice.
4. **Background validation jobs** — Validation is synchronous in the request handler; large files would block the worker.
5. **Transaction redesign** — The current `upload()` method commits mid-flight; a single transaction wrapping validation + storage write would be more robust.

### Verdict

**Phase 2.1 is production-ready for the MVP scope.** The two critical security vulnerabilities (cross-tenant access and OOM via oversized uploads) are closed with defense-in-depth. The error contract is consistent. Test coverage is adequate for the changes made.

The remaining gaps are real but non-blocking for an MVP launch — they should be tracked as Phase 2.2 or later work items.
