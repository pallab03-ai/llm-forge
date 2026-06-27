# Phase 2: Dataset Service — Developer Handoff Report

> **Status:** Implementation complete. Ready for code review and integration testing.
> **Scope:** Dataset upload, validation, listing, versioning, statistics, and soft delete.
> **Approved Revisions Applied:** 4 of 4.

---

## 1. Executive Summary

Phase 2 delivers the **Dataset Service** — the first user-facing data plane of the platform. Users can upload CSV / JSON / JSONL files, the service validates schema and detects within-file duplicates, and every upload becomes a new immutable version of a named dataset. All operations are scoped to the authenticated owner.

The service follows the layered architecture established in Phase 1 (API → Service → Repository → Model) and uses the same `{success, data}` / `{success, error}` response envelope, the same `CurrentUser` dependency, and the same `BaseRepository` pattern.

**Key design choice:** MinIO is **not** used. Per the approved revision, files are stored on the local filesystem under `LOCAL_STORAGE_PATH`. This keeps Phase 2 self-contained and easy to test; a future phase can swap `LocalStorageService` for an `S3StorageService` without touching call sites.

---

## 2. Approved Revisions — Applied

| #   | Revision                                                | Where Applied                                                                                                                                                                   |
| --- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **LocalStorageService** instead of MinIO                | `backend/app/services/storage_service.py` — single class with `save_file`, `get_file_path`, `delete_file`, `delete_dataset_dir`. Configured via `settings.LOCAL_STORAGE_PATH`.  |
| 2   | **`version_number` is an integer**                      | `backend/app/models/dataset.py` — `DatasetVersion.version_number: int`. Migration uses `sa.Integer()`. New versions are `max(version_number) + 1` per dataset.                  |
| 3   | **`DatasetVersion.created_at` is the upload timestamp** | `backend/app/models/dataset.py` — `created_at` defaults to `func.now()` at insert time (i.e. when the row is created, which is during upload). No separate `uploaded_at` field. |
| 4   | **Duplicate detection only inside the uploaded file**   | `backend/app/services/validation_service.py` — `_detect_duplicates` operates on the in-memory record list. No cross-dataset or cross-version comparison.                        |

---

## 3. Files Delivered

### 3.1 New Files (9)

| Path                                                      | Purpose                                                                                                                                                     |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/app/models/dataset.py`                           | `Dataset` + `DatasetVersion` ORM models, enums (`DatasetType`, `DatasetFormat`, `DatasetStatus`), `TimestampMixin`.                                         |
| `backend/app/schemas/dataset.py`                          | Pydantic request/response schemas: `DatasetCreateRequest`, `DatasetResponse`, `DatasetVersionResponse`, `DatasetStatisticsResponse`, `DatasetListResponse`. |
| `backend/app/repositories/dataset_repository.py`          | `DatasetRepository(BaseRepository)` — CRUD, listing with filters, version creation, statistics aggregation.                                                 |
| `backend/app/services/storage_service.py`                 | `LocalStorageService` — filesystem-backed object storage.                                                                                                   |
| `backend/app/services/validation_service.py`              | `ValidationService` — schema validation, within-file duplicate detection, length checks.                                                                    |
| `backend/app/services/dataset_service.py`                 | `DatasetService` — orchestrates upload, list, get, versioning, soft delete.                                                                                 |
| `backend/app/api/v1/datasets.py`                          | FastAPI router with all dataset endpoints.                                                                                                                  |
| `backend/alembic/versions/0003_create_datasets_tables.py` | Migration: `datasets`, `dataset_versions`, three enums, indexes, unique constraint.                                                                         |
| `backend/tests/test_datasets.py`                          | 17 tests covering upload, validation, listing, versioning, statistics, soft delete, auth.                                                                   |

### 3.2 Modified Files (3)

| Path                           | Change                                                                                          |
| ------------------------------ | ----------------------------------------------------------------------------------------------- |
| `backend/app/core/config.py`   | Added `LOCAL_STORAGE_PATH`, `DATASET_MAX_FILE_SIZE_BYTES`, `DATASET_MAX_RECORDS`.               |
| `backend/app/api/v1/router.py` | Registered `datasets.router`.                                                                   |
| `backend/app/api/deps.py`      | Added `StorageServiceDep`, `ValidationServiceDep`, `DatasetRepositoryDep`, `DatasetServiceDep`. |

---

## 4. API Surface

All endpoints live under `/api/v1/datasets` and require `Authorization: Bearer <token>` unless noted.

| Method   | Path                               | Purpose                                                                      | Success | Errors                                                        |
| -------- | ---------------------------------- | ---------------------------------------------------------------------------- | ------- | ------------------------------------------------------------- |
| `POST`   | `/api/v1/datasets`                 | Upload new dataset (multipart: `file` + form fields)                         | `201`   | `409` name exists, `400` invalid format/type, `413` too large |
| `GET`    | `/api/v1/datasets`                 | List datasets (filters: `dataset_type`, `status`, `search`, `skip`, `limit`) | `200`   | —                                                             |
| `GET`    | `/api/v1/datasets/{id}`            | Dataset detail with all versions                                             | `200`   | `404` not found                                               |
| `POST`   | `/api/v1/datasets/{id}/versions`   | Upload a new version of an existing dataset                                  | `201`   | `404`, `413`                                                  |
| `GET`    | `/api/v1/datasets/{id}/versions`   | List versions (newest first)                                                 | `200`   | `404`                                                         |
| `GET`    | `/api/v1/datasets/{id}/statistics` | Aggregated statistics across all versions                                    | `200`   | `404`                                                         |
| `DELETE` | `/api/v1/datasets/{id}`            | Soft delete (sets `deleted_at`, marks status `deleted`)                      | `200`   | `404`                                                         |

### 4.1 Response Envelope

Success:

```json
{ "success": true, "data": { ... } }
```

Error:

```json
{ "success": false, "error": { "code": "DATASET_NOT_FOUND", "message": "..." } }
```

### 4.2 Error Codes

| Code                        | HTTP | Trigger                                                                                         |
| --------------------------- | ---- | ----------------------------------------------------------------------------------------------- |
| `DATASET_NOT_FOUND`         | 404  | Dataset id does not exist or is soft-deleted                                                    |
| `DATASET_NAME_EXISTS`       | 409  | A dataset with this name already exists for the owner                                           |
| `DATASET_INVALID_FORMAT`    | 400  | File extension / content-type does not match declared format                                    |
| `DATASET_FILE_TOO_LARGE`    | 413  | File exceeds `DATASET_MAX_FILE_SIZE_BYTES`                                                      |
| `DATASET_TOO_MANY_RECORDS`  | 413  | Record count exceeds `DATASET_MAX_RECORDS`                                                      |
| `DATASET_VALIDATION_FAILED` | 422  | Schema / duplicate / empty-file validation failed (dataset is still saved with status `failed`) |

---

## 5. Data Model

### 5.1 `datasets`

| Column         | Type                 | Notes                                                                         |
| -------------- | -------------------- | ----------------------------------------------------------------------------- |
| `id`           | UUID PK              |                                                                               |
| `name`         | VARCHAR(255)         | Unique per owner (case-sensitive at DB level; uniqueness enforced in service) |
| `description`  | TEXT NULL            |                                                                               |
| `dataset_type` | ENUM                 | `instruction_tuning`, `chat`, `qa`                                            |
| `format`       | ENUM                 | `csv`, `json`, `jsonl`                                                        |
| `status`       | ENUM                 | `uploading`, `validating`, `ready`, `failed`, `deleted`                       |
| `created_by`   | UUID FK → `users.id` | `ON DELETE SET NULL`                                                          |
| `deleted_at`   | TIMESTAMPTZ NULL     | Soft delete marker                                                            |
| `created_at`   | TIMESTAMPTZ          |                                                                               |
| `updated_at`   | TIMESTAMPTZ          |                                                                               |

Indexes: `ix_datasets_name`, `ix_datasets_created_by`.

### 5.2 `dataset_versions`

| Column              | Type                    | Notes                                    |
| ------------------- | ----------------------- | ---------------------------------------- |
| `id`                | UUID PK                 |                                          |
| `dataset_id`        | UUID FK → `datasets.id` | `ON DELETE CASCADE`                      |
| `version_number`    | INTEGER                 | Monotonically increasing per dataset     |
| `file_path`         | VARCHAR(1024)           | Absolute path under `LOCAL_STORAGE_PATH` |
| `file_size_bytes`   | INTEGER                 |                                          |
| `record_count`      | INTEGER                 | Total records in file                    |
| `duplicate_count`   | INTEGER                 | Within-file duplicates                   |
| `validation_errors` | TEXT NULL               | JSON-encoded list of error strings       |
| `statistics`        | TEXT NULL               | JSON-encoded per-field stats             |
| `created_at`        | TIMESTAMPTZ             | **Upload timestamp** (per revision #3)   |
| `updated_at`        | TIMESTAMPTZ             |                                          |

Indexes: `ix_dataset_versions_dataset_id`.
Unique: `(dataset_id, version_number)`.

---

## 6. Validation Rules

| Format | Required Columns / Keys                                                                                                                                                         |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CSV    | Header row required. Required columns depend on `dataset_type`:<br>• `instruction_tuning` → `instruction`, `response`<br>• `chat` → `messages`<br>• `qa` → `question`, `answer` |
| JSON   | Top-level must be a JSON array of objects. Each object must contain the same required keys as CSV.                                                                              |
| JSONL  | One JSON object per line. Same required keys as CSV.                                                                                                                            |

Additional checks:

- **Empty file** → status `failed`, error recorded.
- **Within-file duplicates** → counted (not removed); status remains `ready` unless schema also fails.
- **Record count > `DATASET_MAX_RECORDS`** → `413 DATASET_TOO_MANY_RECORDS`.
- **File size > `DATASET_MAX_FILE_SIZE_BYTES`** → `413 DATASET_FILE_TOO_LARGE`.

---

## 7. Storage Layout

```
{LOCAL_STORAGE_PATH}/
└── datasets/
    └── {dataset_id}/
        └── v{version_number}/
            └── {version_id}.{ext}
```

Example: `./local_storage/datasets/3f2a.../v1/8c1d....csv`

`LocalStorageService.delete_dataset_dir(dataset_id)` removes the entire subtree on hard delete (currently unused — soft delete only).

---

## 8. Configuration

New env vars (all optional, sensible defaults):

| Variable                      | Default             | Purpose                           |
| ----------------------------- | ------------------- | --------------------------------- |
| `LOCAL_STORAGE_PATH`          | `./local_storage`   | Root directory for uploaded files |
| `DATASET_MAX_FILE_SIZE_BYTES` | `1073741824` (1 GB) | Per-file upload limit             |
| `DATASET_MAX_RECORDS`         | `10000000` (10M)    | Per-file record limit             |

---

## 9. Testing

`backend/tests/test_datasets.py` — **17 tests**, all async, using the existing `client` and `auth_headers` fixtures.

Coverage:

- ✅ Upload: CSV, JSON, JSONL success paths
- ✅ Upload: duplicate name → 409
- ✅ Upload: missing required column → status `failed`
- ✅ Upload: within-file duplicates counted
- ✅ Upload: empty file → status `failed`
- ✅ Upload: missing auth → 401/403
- ✅ List datasets with pagination
- ✅ Get dataset detail
- ✅ Get nonexistent → 404
- ✅ Upload new version (version_number increments)
- ✅ List versions (newest first)
- ✅ Get statistics
- ✅ Soft delete (subsequent GET → 404)
- ✅ Delete nonexistent → 404

Run with:

```bash
cd backend
pytest tests/test_datasets.py -v
```

---

## 10. Migration

```bash
cd backend
alembic upgrade head
```

New revision `0003_create_datasets_tables` (depends on `0002_unique_lower_email_username`).

---

## 11. Known Limitations & Future Work

| Item                                  | Notes                                                                                                                                                                                                               |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Async validation**                  | Validation runs synchronously inside the upload request. For files near the 1 GB limit this can take minutes. Future: move to a background worker (Celery / Arq) and return `202 Accepted` with a polling endpoint. |
| **Cross-dataset duplicate detection** | Per revision #4, only within-file duplicates are detected. Cross-dataset dedup is out of scope.                                                                                                                     |
| **Storage backend**                   | `LocalStorageService` is filesystem-only. A future `S3StorageService` (or MinIO) can be added behind the same interface without changing call sites.                                                                |
| **Hard delete**                       | Only soft delete is implemented. A background job to purge soft-deleted datasets and their files is a future concern.                                                                                               |
| **Dataset name uniqueness**           | Enforced in the service layer (case-sensitive). A DB-level unique index on `(created_by, lower(name))` could be added in a follow-up migration.                                                                     |
| **Streaming uploads**                 | Files are read fully into memory before validation. For very large files, switch to streaming parsers (e.g. `ijson` for JSON, `pandas` chunks for CSV).                                                             |

---

## 12. How to Verify Locally

```bash
# 1. Apply migration
cd backend
alembic upgrade head

# 2. Run tests
pytest tests/test_datasets.py -v

# 3. Start the API
uvicorn app.main:app --reload

# 4. Try it
# Register a user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"u@x.com","username":"u","password":"StrongPass123!"}'

# Upload a dataset (use the token from the response)
curl -X POST http://localhost:8000/api/v1/datasets \
  -H "Authorization: Bearer <token>" \
  -F "file=@sample.csv" \
  -F "name=my-dataset" \
  -F "dataset_type=instruction_tuning" \
  -F "format=csv"

# List datasets
curl http://localhost:8000/api/v1/datasets \
  -H "Authorization: Bearer <token>"
```

---

## 13. Sign-Off Checklist

- [x] All 9 new files created
- [x] All 3 existing files updated
- [x] All 4 approved revisions applied
- [x] Migration is reversible (`downgrade()` implemented)
- [x] Tests cover happy paths and key error paths
- [x] Response envelope matches Phase 1 standard
- [x] Auth required on all endpoints
- [x] Soft delete implemented
- [x] No new external dependencies introduced
- [x] No changes to Phase 1 code beyond the three documented touch points

**Ready for review.**
