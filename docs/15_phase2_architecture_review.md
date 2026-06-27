# Phase 2 — Dataset Service: Critical Architecture Review

**Date:** 2025-01-20  
**Scope:** `backend/app/models/dataset.py`, `backend/app/schemas/dataset.py`, `backend/app/repositories/dataset_repository.py`, `backend/app/services/dataset_service.py`, `backend/app/services/storage_service.py`, `backend/app/services/validation_service.py`, `backend/app/api/v1/datasets.py`, `backend/alembic/versions/0003_create_datasets_tables.py`, `backend/tests/test_datasets.py`  
**Methodology:** Static code analysis against production-readiness criteria. No code modifications performed.

---

## 1. Component-by-Component Analysis

### 1.1 Dataset Model (`backend/app/models/dataset.py`)

| Criterion                | Assessment                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strengths**            | Clean SQLAlchemy 2.0 mapped-column style. Proper enum usage for `DatasetFormat`, `DatasetType`, `DatasetStatus`. Soft-delete via `deleted_at` timestamp with `is_deleted` property. `selectin` lazy loading on `versions` relationship avoids N+1. Indexes on `name` and `created_by` are correctly placed. `ON DELETE SET NULL` on `created_by` FK prevents user-deletion cascades from destroying datasets. |
| **Weaknesses**           | `validation_errors` and `statistics` stored as `Text` with manual JSON serialization — no DB-level JSON validation. `file_size_bytes` uses `Integer` (max ~2.1 GB signed) — will overflow for files >2 GB. No `CHECK` constraint on `version_number > 0`.                                                                                                                                                     |
| **Production Risks**     | **MEDIUM.** `Integer` for `file_size_bytes` is a ticking time bomb for large datasets. The `uq_dataset_versions_dataset_version` unique constraint exists in migration but is not reflected in the model as a `UniqueConstraint` — SQLAlchemy won't enforce it at the ORM level, only the DB will catch violations.                                                                                           |
| **Scalability Concerns** | `selectin` on `versions` loads ALL versions eagerly — fine for <100 versions, problematic for datasets with thousands of versions. No pagination on the relationship.                                                                                                                                                                                                                                         |
| **Security Concerns**    | `created_by` is nullable (`ON DELETE SET NULL`) — after user deletion, dataset ownership is lost. No audit trail for who performed which action.                                                                                                                                                                                                                                                              |

### 1.2 DatasetVersion Model (`backend/app/models/dataset.py`)

| Criterion                | Assessment                                                                                                                                                                                                                          |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strengths**            | Clean versioning model. `ON DELETE CASCADE` from dataset is correct — versions have no meaning without their parent dataset. Composite unique constraint `(dataset_id, version_number)` in migration.                               |
| **Weaknesses**           | No `file_hash` (SHA-256) column — impossible to detect if the same file is re-uploaded. No `uploaded_by` column — can't track who uploaded which version. `file_path` is relative but no column documents the storage backend used. |
| **Production Risks**     | **MEDIUM.** Without a file hash, duplicate detection is purely content-based and expensive. Version number is derived via `MAX + 1` in application code — race condition under concurrency (see Question 7).                        |
| **Scalability Concerns** | Same as Dataset — no pagination on the relationship side.                                                                                                                                                                           |
| **Security Concerns**    | No per-version access control. Anyone who can read the dataset can read all its versions.                                                                                                                                           |

### 1.3 DatasetRepository (`backend/app/repositories/dataset_repository.py`)

| Criterion                | Assessment                                                                                                                                                                                                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Strengths**            | Clean inheritance from `BaseRepository`. Case-insensitive name lookup via `func.lower`. `soft_delete` sets both `deleted_at` and `status=DELETED` — good defense-in-depth. `list_active` filters out soft-deleted rows.                                                        |
| **Weaknesses**           | **No ownership filtering.** `list_active`, `get_by_id`, `get_by_name` — none accept a `user_id` parameter. Any authenticated user can list/access any dataset. `get_latest_version_number` uses `COALESCE(MAX, 0)` which is correct but not concurrency-safe (see Question 7). |
| **Production Risks**     | **HIGH.** Missing ownership filtering is a data isolation vulnerability. The `soft_delete` method calls `flush()` but not `commit()` — caller must remember to commit, and if they don't, the soft-delete is silently lost.                                                    |
| **Scalability Concerns** | `list_active` uses `limit/offset` pagination — acceptable for moderate scale but will degrade with deep offsets on large tables. No cursor-based pagination option.                                                                                                            |
| **Security Concerns**    | **CRITICAL.** No row-level security. Multi-tenant isolation is entirely absent at the repository layer.                                                                                                                                                                        |

### 1.4 DatasetService (`backend/app/services/dataset_service.py`)

| Criterion                | Assessment                                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strengths**            | Clean separation of concerns — delegates to repository, storage, and validator. Well-defined exception hierarchy. Response builders are static methods, easy to test. `upload()` workflow is logically ordered.                                                                                                                                                                                                   |
| **Weaknesses**           | **No transaction wrapping.** The `upload()` method performs 5 distinct operations (DB insert, file write, validation, version insert, status update) without an explicit transaction boundary. If the session has autocommit off (which it does with async SQLAlchemy), partial failures leave inconsistent state. `upload_version()` has the same problem. No file size check before calling storage/validation. |
| **Production Risks**     | **CRITICAL.** Orphaned files and orphaned DB rows are guaranteed under failure conditions (see Questions 3-5). The `file_content: bytes` parameter means the entire file is already in memory before this method is called — a 900 MB upload will consume ~900 MB of RAM in the API process.                                                                                                                      |
| **Scalability Concerns** | Synchronous validation blocks the async event loop for large files. No background task offloading for validation.                                                                                                                                                                                                                                                                                                 |
| **Security Concerns**    | No ownership check in `get_dataset()`, `get_versions()`, `get_statistics()`, `soft_delete()`, or `upload_version()`. User A can delete User B's dataset by guessing the UUID.                                                                                                                                                                                                                                     |

### 1.5 LocalStorageService (`backend/app/services/storage_service.py`)

| Criterion                | Assessment                                                                                                                                                                                                                                  |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strengths**            | Simple, well-structured directory layout: `{root}/datasets/{dataset_id}/{version_number}/{filename}`. Path traversal protection in `get_absolute_path`. Clean `StorageError` exception.                                                     |
| **Weaknesses**           | No file integrity verification (no checksum on write/read). No atomic write — if the process crashes mid-write, a partial file remains on disk. No disk space check before writing. No quarantine directory for files that fail validation. |
| **Production Risks**     | **MEDIUM.** Partial writes are not cleaned up. `shutil.rmtree` in `delete_dataset_dir` is synchronous and blocking — will stall the event loop for large directories. No retry logic for transient filesystem errors.                       |
| **Scalability Concerns** | Single-disk, single-server design. No sharding, no object storage abstraction. The `LocalStorageService` is hardcoded — swapping to S3/MinIO requires rewriting every caller.                                                               |
| **Security Concerns**    | Path traversal protection exists but is string-based — a `..` in the filename itself (not the path) could still cause issues. No file type validation at the storage layer (relies entirely on validation service).                         |

### 1.6 DatasetValidationService (`backend/app/services/validation_service.py`)

| Criterion                | Assessment                                                                                                                                                                                                                                                                                                                                                                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strengths**            | Clean `ValidationResult` dataclass. Format-specific parsers (CSV, JSON, JSONL). Schema validation checks required columns per dataset type. Duplicate detection within file. Statistics computation.                                                                                                                                                                                                             |
| **Weaknesses**           | **Hardcoded constants duplicate settings.** `MAX_FILE_SIZE_BYTES` and `MAX_RECORDS` are defined in the validator class AND in `settings` — they can diverge. All parsers load the entire file into memory (`json.load()` for JSON, list accumulation for CSV/JSONL). No streaming parser exists. Duplicate detection uses `json.dumps` per record — O(n) memory for the `seen` set plus O(n) serialization cost. |
| **Production Risks**     | **HIGH.** A 900 MB JSON file will be fully loaded into memory by `json.load()`, then duplicated in the `records` list, then each record serialized again for duplicate detection — peak memory could be 3-4× the file size. CSV parser uses `csv.DictReader` which is line-streaming, but then accumulates all rows into a list, negating the streaming benefit.                                                 |
| **Scalability Concerns** | No chunked/batched validation. No timeout mechanism — a malformed file could cause infinite processing. Validation is CPU-bound and runs in the async event loop.                                                                                                                                                                                                                                                |
| **Security Concerns**    | No protection against zip bombs or compression bombs (though only CSV/JSON/JSONL are accepted). No file content sniffing to verify the claimed format matches actual content.                                                                                                                                                                                                                                    |

### 1.7 Dataset APIs (`backend/app/api/v1/datasets.py`)

| Criterion                | Assessment                                                                                                                                                                                                                                                                                                                                               |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strengths**            | Clean FastAPI routing with proper response models. Exception handlers map domain errors to HTTP status codes correctly. File upload uses multipart form data. Pagination parameters have sensible defaults and bounds (limit 1-500).                                                                                                                     |
| **Weaknesses**           | **`content = await file.read()` reads the ENTIRE file into memory** before any size check. Starlette's `UploadFile` has a `size` attribute available before reading — it's not used. No `Content-Length` check against `DATASET_MAX_FILE_SIZE_BYTES`. The `current_user` dependency is injected but **never used** for ownership checks in any endpoint. |
| **Production Risks**     | **CRITICAL.** A 900 MB upload will allocate 900 MB in the API process before any validation occurs. Multiple concurrent uploads will OOM the process. No `RequestValidationError` handler for file size — FastAPI's default will return a 422 without the standard envelope.                                                                             |
| **Scalability Concerns** | Synchronous file reading in async handlers. No upload progress tracking. No resumable upload support.                                                                                                                                                                                                                                                    |
| **Security Concerns**    | **CRITICAL.** Zero ownership enforcement. `current_user` is authenticated but never checked against `dataset.created_by`. Every mutation endpoint (delete, upload version) and every read endpoint (get, list versions, statistics) is accessible to any authenticated user for any dataset ID.                                                          |

### 1.8 Alembic Migration 0003 (`backend/alembic/versions/0003_create_datasets_tables.py`)

| Criterion                | Assessment                                                                                                                                                                                                                                                                                      |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strengths**            | Clean migration structure. Enums created with `checkfirst=True`. Proper index creation. Unique constraint on `(dataset_id, version_number)`. Correct downgrade path that drops constraints before tables before enums.                                                                          |
| **Weaknesses**           | **No unique constraint on `(created_by, name)`.** Name uniqueness is global, not per-user — User A and User B cannot both have a dataset named "test". This is a product decision, not a bug, but it's worth flagging. No `CHECK` constraint on `version_number > 0` or `file_size_bytes >= 0`. |
| **Production Risks**     | **LOW.** The migration itself is well-formed. The risks are in what it _doesn't_ enforce (see above).                                                                                                                                                                                           |
| **Scalability Concerns** | B-tree indexes on `name` and `created_by` are fine. No composite index for common query patterns like `(created_by, deleted_at, created_at)`.                                                                                                                                                   |
| **Security Concerns**    | None directly — migration is structural.                                                                                                                                                                                                                                                        |

### 1.9 Tests (`backend/tests/test_datasets.py`)

| Criterion                | Assessment                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strengths**            | Good coverage of happy paths: upload CSV/JSON/JSONL, duplicate name rejection, missing column detection, within-file duplicate counting, empty file rejection, auth required, list datasets, get detail, upload new version, list versions, statistics, soft delete. Clean helper functions for test data generation.                                                                                                                   |
| **Weaknesses**           | **No concurrency tests.** No test for two simultaneous uploads creating the same version number. **No ownership isolation tests.** No test verifying User A cannot access/delete User B's dataset. **No large file tests.** No test for files approaching the size limit. **No failure injection tests.** No test for storage failure mid-upload, DB failure mid-transaction, or validation timeout. **No transaction rollback tests.** |
| **Production Risks**     | **HIGH.** The test suite gives false confidence. The most likely production failures (concurrency, ownership, partial failure) have zero coverage.                                                                                                                                                                                                                                                                                      |
| **Scalability Concerns** | Tests use `aiosqlite` — behavior differs from PostgreSQL (especially around concurrency and constraints).                                                                                                                                                                                                                                                                                                                               |
| **Security Concerns**    | No tests for path traversal in file paths, no tests for malicious file content.                                                                                                                                                                                                                                                                                                                                                         |

---

## 2. Answers to Specific Technical Questions

### Q1: What happens if a user uploads a 900 MB CSV?

**The API process will attempt to allocate ~900 MB of RAM and likely OOM.**

The chain is:

1. Starlette/FastAPI receives the multipart upload and spools it to a temporary file (or memory, depending on size).
2. `content = await file.read()` in `datasets.py` reads the **entire** 900 MB into a `bytes` object in RAM.
3. This `bytes` object is passed to `DatasetService.upload()`, which passes it to `LocalStorageService.save_file()` (writes to disk — another 900 MB of buffer).
4. Then `ValidationService.validate()` opens the file and parses it — CSV via `csv.DictReader` accumulates all rows into a list, consuming another ~900+ MB.
5. Duplicate detection serializes each record to JSON and stores in a `set`, adding more memory pressure.

**Estimated peak memory: 2.5–3.5 GB for a 900 MB CSV.** On a typical 512 MB or 1 GB container, this will trigger an OOM kill.

### Q2: Is the file streamed or loaded entirely into memory?

**Loaded entirely into memory. There is zero streaming.**

- `datasets.py` line: `content = await file.read()` — reads the full file into RAM.
- `dataset_service.py`: `file_content: bytes` parameter — the entire file is passed as a single bytes object.
- `validation_service.py`: `json.load()` for JSON (full load), list accumulation for CSV/JSONL (full load).
- `storage_service.py`: `write_bytes(content)` — writes the full buffer to disk in one call.

No part of the pipeline uses streaming, chunked reading, or `UploadFile.file`-as-iterator.

### Q3: What happens if upload fails halfway through?

**It depends on WHERE it fails. The system has no transactional rollback across DB + filesystem.**

| Failure Point                      | DB State                               | Filesystem State    | Outcome                                                         |
| ---------------------------------- | -------------------------------------- | ------------------- | --------------------------------------------------------------- |
| After `Dataset.add()` (DB insert)  | Dataset row exists, status=`UPLOADING` | No file written     | **Orphaned DB row** — status stuck at UPLOADING forever         |
| After `storage.save_file()`        | Dataset row exists, status=`UPLOADING` | File exists on disk | File written, but no version record                             |
| After `validator.validate()` fails | Dataset row exists, status=`UPLOADING` | File exists on disk | **Orphaned file** — no version record pointing to it            |
| After `DatasetVersion.add()`       | Dataset row + version row exist        | File exists         | Partial success — but status may not be updated if commit fails |
| After `commit()` + status update   | All consistent                         | File exists         | Clean state                                                     |

The `upload()` method does not wrap operations in a transaction. Each `add()` calls `flush()` (via `BaseRepository.add()`), so partial state is persisted to the DB immediately, even if a later step fails.

### Q4: Can orphaned files exist on disk?

**Yes, in multiple scenarios:**

1. File saved to disk → validation fails → exception propagates → no cleanup of the written file.
2. File saved to disk → version record creation fails → exception propagates → file remains.
3. Dataset soft-deleted → `soft_delete` only sets `deleted_at` and `status=DELETED` in DB → **files are never deleted**.
4. Dataset version upload → new version file saved → later step fails → file remains.

The `LocalStorageService` has `delete_file()` and `delete_dataset_dir()` methods, but they are **never called** in any error-handling path or in `soft_delete()`.

### Q5: Can orphaned database records exist?

**Yes, in multiple scenarios:**

1. `Dataset.add()` succeeds (flushed) → `storage.save_file()` fails → Dataset row exists with `status=UPLOADING`, no versions, no file.
2. `Dataset.add()` succeeds → file saved → validation fails → Dataset row exists with `status=UPLOADING`, no version record.
3. `DatasetVersion.add()` succeeds → subsequent commit fails → version row exists but dataset status not updated.

The `upload()` method sets `status=FAILED` in some error paths but does not consistently clean up. The `status=UPLOADING` state has no timeout or garbage collection mechanism.

### Q6: Is version creation transactional?

**No.** Version number assignment and version record creation are not atomic.

The flow in `upload_version()`:

1. `get_latest_version_number()` — reads current MAX
2. `version_number = latest + 1` — computes next in application code
3. `storage.save_file()` — writes to filesystem (not transactional with DB)
4. `validator.validate()` — CPU-bound work (not transactional)
5. `DatasetVersion.add()` — inserts the version row
6. `commit()` — commits

Steps 1-2 are a classic **read-then-write race condition**. Steps 3-4 are non-DB operations that can't be rolled back. Only step 5-6 is actually within a DB transaction.

### Q7: Can two concurrent uploads create duplicate version numbers?

**Yes, this is a likely race condition.**

```
Request A: SELECT MAX(version_number) → returns 5
Request B: SELECT MAX(version_number) → returns 5
Request A: INSERT version_number=6 → succeeds
Request B: INSERT version_number=6 → UNIQUE CONSTRAINT VIOLATION → 500 error
```

The `uq_dataset_versions_dataset_version` unique constraint in the DB will catch this and reject the second insert, but:

- The second request will get a 500 Internal Server Error (not a graceful 409 Conflict).
- The file for Request B has already been written to disk (orphaned).
- The dataset status may have been partially updated.

The fix is to use `SELECT ... FOR UPDATE` on the dataset row, or use an atomic `INSERT ... SELECT` with `COALESCE(MAX, 0) + 1`, or use a database sequence.

### Q8: Is dataset ownership enforced everywhere?

**No. Ownership is not enforced anywhere.**

- `DatasetRepository.list_active()` — no `user_id` filter.
- `DatasetRepository.get_by_id()` — no ownership check.
- `DatasetService.get_dataset()` — no ownership check.
- `DatasetService.upload_version()` — no ownership check (User A can upload a new version to User B's dataset).
- `DatasetService.soft_delete()` — no ownership check (User A can delete User B's dataset).
- `DatasetService.get_statistics()` — no ownership check.

The `current_user` is injected into every API endpoint but is **never passed to the service layer** and **never used for authorization**.

### Q9: Can a user access another user's dataset through direct ID lookup?

**Yes, trivially.** UUIDs are not secrets, and there is zero authorization.

1. `GET /api/v1/datasets/{any_uuid}` — returns the dataset regardless of who created it.
2. `DELETE /api/v1/datasets/{any_uuid}` — soft-deletes any dataset.
3. `POST /api/v1/datasets/{any_uuid}/versions` — uploads a new version to any dataset.
4. `GET /api/v1/datasets/{any_uuid}/versions` — lists versions of any dataset.
5. `GET /api/v1/datasets/{any_uuid}/statistics` — returns statistics for any dataset.

The only protection is that the attacker must know or guess a valid UUID, which is not a security boundary.

### Q10: What are the top 5 bugs most likely to occur in production?

| Rank  | Bug                                                                                                                                                                      | Impact                                                                     | Likelihood                                                              |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| **1** | **OOM on large file upload** — `await file.read()` loads entire file into RAM. Multiple concurrent 500 MB+ uploads will exhaust process memory.                          | Service crash, lost uploads, cascading failures if behind a load balancer. | **Very High** — first large-file user triggers it.                      |
| **2** | **Cross-tenant data access** — Zero ownership enforcement. Any authenticated user can read, delete, or modify any dataset by UUID.                                       | Data breach, data loss, compliance violation.                              | **Very High** — only requires guessing a UUID.                          |
| **3** | **Concurrent version number collision** — Two simultaneous uploads to the same dataset will collide on `(dataset_id, version_number)` unique constraint.                 | 500 error for one user, orphaned file on disk, confusing UX.               | **High** — any team with >1 user uploading versions.                    |
| **4** | **Orphaned file accumulation** — Files are never cleaned up on failure or soft-delete. Over time, disk fills with unreferenced files.                                    | Disk space exhaustion, increased storage costs, backup bloat.              | **High** — gradual but inevitable.                                      |
| **5** | **Partial upload state with no recovery** — If any step after `Dataset.add()` fails, the dataset row stays in `status=UPLOADING` forever with no timeout or cleanup job. | Cluttered UI showing "stuck" datasets, user confusion, support tickets.    | **Medium-High** — any transient error (disk full, DB blip) triggers it. |

---

## 3. Summary Risk Matrix

| Risk Area                          | Severity     | Impact                          | Mitigation Priority                           |
| ---------------------------------- | ------------ | ------------------------------- | --------------------------------------------- |
| Missing ownership/authorization    | **CRITICAL** | Multi-tenant data breach        | P0 — Must fix before any external user access |
| Full-file memory loading           | **CRITICAL** | OOM, service unavailable        | P0 — Must fix before accepting files >50 MB   |
| No cross-resource transactionality | **HIGH**     | Orphaned files + DB rows        | P1 — Fix before production deployment         |
| Concurrent version collision       | **HIGH**     | Failed uploads under normal use | P1 — Fix before multi-user deployment         |
| No file cleanup on failure/delete  | **MEDIUM**   | Disk exhaustion over time       | P2 — Add background cleanup job               |
| Hardcoded constants vs settings    | **LOW**      | Configuration drift             | P3 — Consolidate during refactor              |
| Integer file_size_bytes overflow   | **LOW**      | Wrong size for >2 GB files      | P3 — Change to BigInteger                     |

---

## 4. Architectural Recommendations

1. **Implement ownership filtering at the repository layer.** Add `owner_id: UUID` parameter to `list_active`, `get_by_id`, and all mutation methods. Reject access if `dataset.created_by != current_user.id` (unless admin).

2. **Stream file uploads.** Use `UploadFile.file` as an async iterator. Write chunks to a temporary file, validate the temp file, then move it atomically to the final location. Never hold the entire file in memory.

3. **Wrap multi-step operations in explicit transactions.** Use `async with session.begin()` for the upload workflow. If any step fails, roll back DB changes AND clean up written files in a `finally` block.

4. **Use `SELECT ... FOR UPDATE` for version number assignment.** Lock the dataset row before reading the latest version number to prevent race conditions.

5. **Add a periodic cleanup job.** Scan for datasets with `status=UPLOADING` older than N hours and mark them as `FAILED`. Scan for files without corresponding version records and remove them.

6. **Add file hashing.** Store `file_hash` (SHA-256) on `DatasetVersion` to enable deduplication and integrity verification.

7. **Move validation to a background task.** For files above a threshold (e.g., 10 MB), offload validation to a Celery/ARQ task to avoid blocking the async event loop.

8. **Add comprehensive failure-mode tests.** Concurrency tests, ownership isolation tests, storage failure injection, and large-file boundary tests.

---

_End of review. No code was modified in the production of this report._
