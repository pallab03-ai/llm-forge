# Phase 6 — Model Registry (MVP) — Handoff Report

**Phase**: 6 — Model Registry (MVP)
**Date**: 2025-06-27
**Status**: ✅ COMPLETE
**Predecessor**: Phase 5.1 (Real Evaluation Validation)

---

## 1. Executive Summary

Phase 6 implements the Model Registry MVP — a synchronous, user-scoped registry for managing trained LoRA adapters and their lifecycle. The implementation follows the existing Repository → Service → API pattern. 37 new tests pass; the full suite of 338 tests passes with 0 failures.

**Key decisions**:
- `Model` is a user-owned logical container; `ModelVersion` is one trained adapter + evaluation snapshot.
- Version lifecycle is exactly four states: `DRAFT`, `STAGING`, `PRODUCTION`, `ARCHIVED`.
- New versions default to `STAGING`.
- Promotion to `PRODUCTION` is atomic and demotes the previous `PRODUCTION` version to `STAGING` in the same transaction.
- Version registration validates that the training job is completed with an artifact and that the evaluation is completed and belongs to the same training job.

**Out of scope** (explicitly excluded): MLflow Registry, HuggingFace Hub, OCI Registry, model download, deployment, canary rollout, traffic splitting, rollback API, async workers.

---

## 2. Files Read

| File | Purpose |
|------|---------|
| `docs/00_project_context.md` | Project status and conventions |
| `docs/17_architecture_decisions.md` | Architecture standards, API envelope, MVP scope lock |
| `docs/23_phase5_evaluation_handoff.md` | Phase 5 completion state, evaluation schema |
| `docs/24_phase51_real_evaluation_validation.md` | Phase 5.1 completion state |
| `backend/app/db/base.py` | BaseModel (UUID + Timestamp mixins) |
| `backend/app/models/__init__.py` | Model registration for Alembic autogenerate |
| `backend/app/models/user.py` | User ORM pattern |
| `backend/app/models/dataset.py` | Dataset/DatasetVersion pattern |
| `backend/app/models/training_job.py` | TrainingJob ORM pattern |
| `backend/app/models/evaluation.py` | Evaluation ORM pattern |
| `backend/app/repositories/base.py` | Generic async CRUD repository |
| `backend/app/repositories/evaluation_repository.py` | Repository pattern |
| `backend/app/repositories/training_job_repository.py` | Repository pattern |
| `backend/app/services/evaluation_service.py` | Service + domain exception pattern |
| `backend/app/schemas/evaluation.py` | Pydantic schema pattern |
| `backend/app/api/v1/evaluations.py` | Route pattern, dependency injection |
| `backend/app/api/v1/router.py` | Router aggregation |
| `backend/app/api/deps.py` | CurrentUser, DBSession dependencies |
| `backend/app/main.py` | Exception handler registration pattern |
| `backend/app/schemas/common.py` | SuccessResponse envelope |

---

## 3. Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/models/model.py` | 150 | `Model`, `ModelVersion`, `ModelVersionStatus` |
| `backend/app/repositories/model_repository.py` | 168 | `ModelRepository` — model/version data access |
| `backend/app/services/model_registry_service.py` | 414 | `ModelRegistryService` + 12 domain exceptions |
| `backend/app/schemas/model.py` | 88 | Request/response Pydantic schemas |
| `backend/app/api/v1/models.py` | 206 | Model Registry API routes |
| `backend/alembic/versions/0006_create_model_registry.py` | 198 | Alembic migration for `models` and `model_versions` |
| `backend/tests/test_models.py` | 1074 | 37 tests (repository, service, API) |
| `docs/25_phase6_model_registry_handoff.md` | — | This report |

---

## 4. Files Modified

| File | Change |
|------|--------|
| `backend/app/models/__init__.py` | Added `Model`, `ModelVersion` imports + `__all__` entries |
| `backend/app/api/v1/router.py` | Added `models` router import + include |
| `backend/app/main.py` | Added 12 Model Registry exception handlers |
| `README.md` | Updated status line, roadmap table, added Model Registry section |

No other files were touched.

---

## 5. Database Design

**Table: `models`**

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | UUID | NO | PK (BaseModel) |
| owner_id | UUID | NO | FK → users.id CASCADE |
| name | String(255) | NO | Indexed |
| description | Text | YES | |
| created_at | DateTime(tz) | NO | BaseModel |
| updated_at | DateTime(tz) | NO | BaseModel |

**Table: `model_versions`**

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | UUID | NO | PK (BaseModel) |
| model_id | UUID | NO | FK → models.id CASCADE |
| training_job_id | UUID | NO | FK → training_jobs.id CASCADE |
| evaluation_id | UUID | NO | FK → evaluations.id CASCADE |
| version_number | Integer | NO | Per-model auto-increment |
| artifact_path | String(1024) | NO | Copied from training job |
| metrics_snapshot | JSON | YES | Snapshot of evaluation metrics |
| status | enum | NO | draft/staging/production/archived |
| created_at | DateTime(tz) | NO | BaseModel |
| updated_at | DateTime(tz) | NO | BaseModel |

**Indexes**:
- `ix_models_owner_id`
- `ix_model_versions_model_id`
- `ix_model_versions_training_job_id`
- `ix_model_versions_evaluation_id`
- `ix_model_versions_status`

**Constraints**:
- Unique `(model_id, version_number)` — enforced at the database layer.

No soft delete — versions move to `ARCHIVED` instead.

---

## 6. Model Lifecycle

Exactly four states are supported:

```text
DRAFT → STAGING → PRODUCTION → ARCHIVED
```

| State | Meaning |
|-------|---------|
| DRAFT | Reserved for future use; MVP does not create DRAFT versions via API. |
| STAGING | Default state for newly registered versions. Ready for testing/promotion. |
| PRODUCTION | The currently deployed/serving version. Only one per model. |
| ARCHIVED | Retired version. Cannot be promoted. |

**Allowed transitions**:
- `STAGING` → `PRODUCTION` (via `POST /models/versions/{id}/promote`)
- Any non-archived state → `ARCHIVED` (via `POST /models/versions/{id}/archive`)
- `PRODUCTION` → `STAGING` (automatic demotion during promotion)

**Rejected transitions**:
- `ARCHIVED` → `PRODUCTION`
- `PRODUCTION` → `PRODUCTION` (already production)

---

## 7. Versioning Design

Each trained adapter becomes one `ModelVersion`.

```text
Model: Customer Support Assistant
├── v1 (STAGING)
├── v2 (PRODUCTION)
└── v3 (ARCHIVED)
```

- `version_number` is an integer auto-incremented per model (`1, 2, 3, ...`).
- The repository computes `max(version_number) + 1` for the next version.
- A unique database constraint on `(model_id, version_number)` prevents duplicates even under races.
- New versions are created via `POST /api/v1/models/{id}/versions` by providing a completed `training_job_id` and `evaluation_id`.
- The `artifact_path` is copied from the training job; `metrics_snapshot` is copied from the evaluation.

---

## 8. Repository Design

`ModelRepository` extends `BaseRepository[Model]` and owns data access for both `Model` and `ModelVersion`.

| Method | Purpose |
|--------|---------|
| `create_model(model)` | Persist a new model container |
| `get_model(model_id)` | Fetch model by UUID (versions loaded via `selectin`) |
| `list_models(owner_id, limit, offset)` | Paginated list, newest first |
| `count_models(owner_id)` | Pagination total |
| `get_version(version_id)` | Fetch a version by UUID |
| `get_version_by_number(model_id, version_number)` | Fetch version by composite key |
| `get_next_version_number(model_id)` | Compute next version number |
| `create_version(version)` | Persist a new version |
| `get_current_production_version(model_id)` | Find the current PRODUCTION version |
| `promote_version(version_id)` | Atomic promote + demote |
| `archive_version(version_id)` | Set status to ARCHIVED |

No business logic lives in the repository. Promotion atomically updates both the old production version and the new version inside the current transaction (single `flush`).

---

## 9. Service Design

`ModelRegistryService` orchestrates the registry flow and enforces business rules.

| Method | Responsibility |
|--------|----------------|
| `create_model` | Create a model container |
| `get_model` | Ownership-checked model fetch |
| `list_models` | Paginated, user-scoped list |
| `create_version` | Register a trained adapter as a new version; validates job/eval ownership and readiness |
| `promote_version` | Promote to PRODUCTION; validates version state and ownership |
| `archive_version` | Archive a version; validates version state and ownership |

**Validation rules enforced in the service**:
- Model must exist and be owned by the requesting user.
- Training job must exist, be owned, be `COMPLETED`, and have `artifact_path`.
- Evaluation must exist, be owned, be `COMPLETED`.
- Evaluation must reference the same training job (prevents cross-linking unrelated artifacts).
- Version cannot be promoted if `ARCHIVED` or already `PRODUCTION`.
- Version cannot be archived if already `ARCHIVED`.

**Domain exceptions** (12 total):

| Exception | HTTP | Code |
|-----------|------|------|
| `ModelNotFoundError` | 404 | `MODEL_NOT_FOUND` |
| `ModelAccessDeniedError` | 403 | `MODEL_ACCESS_DENIED` |
| `ModelVersionNotFoundError` | 404 | `MODEL_VERSION_NOT_FOUND` |
| `ModelVersionAccessDeniedError` | 403 | `MODEL_VERSION_ACCESS_DENIED` |
| `ModelVersionExistsError` | 409 | `MODEL_VERSION_EXISTS` |
| `TrainingJobNotFoundError` | 404 | `TRAINING_JOB_NOT_FOUND` |
| `TrainingJobNotReadyError` | 409 | `TRAINING_JOB_NOT_READY` |
| `EvaluationNotFoundError` | 404 | `EVALUATION_NOT_FOUND` |
| `EvaluationNotReadyError` | 409 | `EVALUATION_NOT_READY` |
| `InvalidPromotionError` | 409 | `INVALID_PROMOTION` |
| `InvalidArchiveError` | 409 | `INVALID_ARCHIVE` |
| `ModelRegistryError` | 400 | `MODEL_REGISTRY_ERROR` (fallback) |

---

## 10. API Design

| Method | Path | Status | Purpose |
|--------|------|--------|---------|
| POST | `/api/v1/models` | 201 | Create a model container |
| GET | `/api/v1/models` | 200 | List models for current user |
| GET | `/api/v1/models/{id}` | 200 | Get a model by ID |
| POST | `/api/v1/models/{id}/versions` | 201 | Register a trained adapter as a version |
| POST | `/api/v1/models/versions/{version_id}/promote` | 200 | Promote version to PRODUCTION |
| POST | `/api/v1/models/versions/{version_id}/archive` | 200 | Archive a version |

No DELETE endpoints — versions are archived instead.

All responses use the standard `{success, data}` / `{success, error}` envelope. All endpoints require JWT auth via `CurrentUser` dependency.

### Example request/response

Create model:

```bash
curl -X POST http://localhost:8000/api/v1/models \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Support Bot","description":"Support assistant"}'
```

Response:

```json
{
  "success": true,
  "data": {
    "id": "...",
    "owner_id": "...",
    "name": "Support Bot",
    "description": "Support assistant",
    "versions": [],
    "created_at": "2025-06-27T00:00:00Z",
    "updated_at": "2025-06-27T00:00:00Z"
  }
}
```

---

## 11. Transaction Strategy

Promotion uses a single database transaction:

1. Load the version to be promoted.
2. Load the current PRODUCTION version of the same model (if any).
3. Set current PRODUCTION → STAGING.
4. Set promoted version → PRODUCTION.
5. `flush()` once.
6. Service calls `commit()`.

There is no intermediate state where two versions are PRODUCTION or where the old version is demoted but the new one is not yet promoted. The unique constraint on `(model_id, version_number)` also guards version creation against races.

---

## 12. Validation Rules

Rejected conditions and their HTTP responses:

| Condition | HTTP | Code |
|-----------|------|------|
| Model not found / not owned | 404 / 403 | `MODEL_NOT_FOUND` / `MODEL_ACCESS_DENIED` |
| Version not found / not owned | 404 / 403 | `MODEL_VERSION_NOT_FOUND` / `MODEL_VERSION_ACCESS_DENIED` |
| Duplicate version number | 409 | `MODEL_VERSION_EXISTS` |
| Training job not found / not owned | 404 | `TRAINING_JOB_NOT_FOUND` |
| Training job not completed or no artifact | 409 | `TRAINING_JOB_NOT_READY` |
| Evaluation not found / not owned | 404 | `EVALUATION_NOT_FOUND` |
| Evaluation not completed | 409 | `EVALUATION_NOT_READY` |
| Evaluation does not match training job | 400 | `MODEL_REGISTRY_ERROR` |
| Promoting an archived version | 409 | `INVALID_PROMOTION` |
| Promoting an already-production version | 409 | `INVALID_PROMOTION` |
| Archiving an already-archived version | 409 | `INVALID_ARCHIVE` |

---

## 13. Test Results

### Phase 6 tests

```text
============================= test session starts =============================
platform win32 -- Python 3.11.4, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\PALLAB\Auto_finetuning\backend
configfile: pyproject.toml
plugins: anyio-3.7.1, langsmith-0.4.6, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 37 items

tests\test_models.py .....................................               [100%]

============================== warnings summary ===============================
tests/test_models.py::TestModelRegistryAPI::test_create_model_extra_fields_rejected
  C:\Python311\Lib\site-packages\starlette\_exception_handler.py:59: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.

======================= 37 passed, 1 warning in 11.08s ========================
```

### Full suite

```text
============================= test session starts =============================
platform win32 -- Python 3.11.4, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\PALLAB\Auto_finetuning\backend
configfile: pyproject.toml
testpaths: tests
plugins: anyio-3.7.1, langsmith-0.4.6, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 338 items

tests\test_auth.py .............
tests\test_datasets.py ........................
tests\test_evaluations.py ............................
tests\test_health.py ....
tests\test_models.py .....................................
tests\test_security.py ........
tests\test_training_jobs.py ...........................................
.......................
tests\test_training_module.py ..........................................
........................................................................
...........................................

============================== warnings summary ===============================
tests/test_auth.py: 2 warnings
tests/test_evaluations.py: 1 warning
tests/test_models.py: 1 warning
tests/test_training_jobs.py: 20 warnings
  StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated.

====================== 338 passed, 24 warnings in 44.07s ======================
```

**Test summary**:

| Metric | Value |
|--------|-------|
| Phase 6 tests | 37 |
| Phase 6 passed | 37 |
| Full suite tests | 338 |
| Full suite passed | 338 |
| Full suite runtime | 44.07s |

---

## 14. Performance Notes

- **Synchronous**: All registry operations are synchronous and run in the request handler. This is acceptable for MVP because registry writes are infrequent metadata operations.
- **Version number computation**: `SELECT MAX(version_number)` per model. Fast with an index on `(model_id, version_number)`; the unique constraint provides it implicitly.
- **Selectin loading**: `Model.versions` uses `selectin` loading. Listing many models with many versions could issue N+1 queries. For MVP list sizes this is acceptable; a production-scale list endpoint should paginate versions or use a separate endpoint.
- **No caching**: Current PRODUCTION version lookups are fresh database queries. A cache would help only at high read volume.

---

## 15. Known Limitations

1. **No DRAFT → STAGING transition endpoint**: The `DRAFT` state exists in the enum but no API creates or transitions DRAFT versions in MVP. New versions start in `STAGING`.
2. **No rollback endpoint**: Rolling back production requires manually archiving the current production version and re-promoting the desired staging version. This is explicitly out of MVP scope.
3. **No deployment integration**: The registry tracks which version is production but does not deploy it. Phase 7 (Deployment Service) will consume this information.
4. **`metrics_snapshot` is a static copy**: Metrics are copied at version creation time. If the evaluation row is later mutated, the snapshot remains unchanged. This is intentional for auditability.
5. **No event webhooks**: Promotion does not notify other services. Deployment must poll or be wired later.
6. **Cross-link guard is application-level**: The check that `evaluation.model_id == training_job.id` happens in the service, not the database. The DB only enforces that both FKs point to existing rows owned by the same user indirectly (via application-layer ownership checks).
7. **Artifact path is copied, not referenced**: If `training_jobs.artifact_path` changes after version creation, the version retains the old path. This is intentional for reproducibility.

---

## 16. Future Enhancements

| Enhancement | When | Effort |
|-------------|------|--------|
| DRAFT → STAGING transition endpoint | Phase 6.1 | Small |
| Rollback API (re-promote previous production) | Phase 6.1 | Small |
| Webhook/event on promotion | Phase 7 | Small |
| Current production endpoint (`/models/{id}/production`) | Phase 7 | Small |
| Version tags / aliases (e.g. `latest`, `stable`) | Phase 6.2 | Small |
| Model-level metadata (base model, task type) | Phase 6.2 | Small |
| MinIO artifact lifecycle hooks | Phase 6.2 | Medium |
| Soft delete for models | On request | Small |

---

## 17. Final Assessment

**Phase 6 is COMPLETE.** All deliverables met:

1. ✅ `Model` and `ModelVersion` ORM models with `ModelVersionStatus` enum
2. ✅ `ModelRepository` with model/version CRUD and atomic promotion
3. ✅ `ModelRegistryService` with lifecycle validation and ownership checks
4. ✅ Model Registry API (6 endpoints, no deletes)
5. ✅ Alembic migration `0006_create_model_registry`
6. ✅ Pydantic request/response schemas
7. ✅ 37 new tests, all passing
8. ✅ Full suite passing (338/338)
9. ✅ README updated with Model Registry status and endpoints

**Trade-offs made**:
- Synchronous registry operations (MVP scope lock; writes are infrequent).
- `DRAFT` state reserved but unused via API (simplest path to satisfy the 4-state requirement).
- `metrics_snapshot` copied from evaluation at version creation (static audit trail over live reference).
- No MLflow integration (explicitly excluded from MVP).

**Limitations not hidden**:
- No rollback API.
- No deployment integration yet.
- DRAFT state has no API transition.
- Cross-link guard is application-level, not a database constraint.

### Test Summary

| Metric | Value |
|--------|-------|
| Phase 6 tests | 37 |
| Phase 6 passed | 37 |
| Full suite tests | 338 |
| Full suite passed | 338 |
| Full suite runtime | 44.07s |

> Phase 6 Model Registry is ready for Phase 7 (Deployment Service).

---

**STOP.** Phase 7 will not begin until explicitly requested and reviewed.
