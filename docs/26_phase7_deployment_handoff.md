# Phase 7 — Deployment Service (MVP) — Handoff Report

**Phase**: 7 — Deployment Service (MVP)
**Date**: 2025-06-27
**Status**: ✅ COMPLETE
**Predecessor**: Phase 6 (Model Registry)

---

## 1. Executive Summary

Phase 7 implements the Deployment Service MVP. A user can select a `ModelVersion`, create a `Deployment`, activate it to load the LoRA adapter into an inference engine, and then call `/deployments/{id}/generate` to produce text.

The implementation is intentionally synchronous and single-instance:

- No Kubernetes, Docker orchestration, Ray, vLLM, Triton, TGI, autoscaling, load balancing, streaming, multi-GPU, background workers, Celery, Redis queues, canary, A/B testing, or rate limiting.
- Heavy ML imports are lazy, so the module imports cleanly in tests.
- The inference engine is a module-level singleton that caches the loaded base model + LoRA adapter by `(base_model, artifact_path)` key.
- The API contract (`POST /deployments/{id}/generate`) is decoupled from the inference backend so a production engine can be swapped in later.

**All 363 tests pass** (338 pre-existing + 25 new).

---

## 2. Files Read

| File | Purpose |
|------|---------|
| `docs/00_project_context.md` | Project status and conventions |
| `docs/17_architecture_decisions.md` | Architecture standards, API envelope, MVP scope lock |
| `docs/24_phase51_real_evaluation_validation.md` | Real adapter loading pattern validated in Phase 5.1 |
| `docs/25_phase6_model_registry_handoff.md` | Phase 6 completion state |
| `backend/app/db/base.py` | BaseModel (UUID + Timestamp mixins) |
| `backend/app/models/__init__.py` | Model registration for Alembic autogenerate |
| `backend/app/models/model.py` | ModelVersion pattern |
| `backend/app/models/training_job.py` | TrainingJob ORM pattern, `base_model`, `artifact_path` |
| `backend/app/repositories/base.py` | Generic async CRUD repository |
| `backend/app/repositories/model_repository.py` | Repository pattern for ModelVersion |
| `backend/app/services/evaluation_service.py` | Real adapter loading pattern (`_generate_predictions`) |
| `backend/app/services/model_registry_service.py` | Service + domain exception pattern |
| `backend/app/schemas/model.py` | Pydantic schema pattern |
| `backend/app/api/v1/models.py` | Route pattern, dependency injection |
| `backend/app/api/v1/router.py` | Router aggregation |
| `backend/app/api/deps.py` | CurrentUser, DBSession dependencies |
| `backend/app/main.py` | Exception handler registration pattern |
| `backend/app/schemas/common.py` | SuccessResponse envelope |
| `backend/alembic/versions/0006_create_model_registry.py` | Migration pattern |
| `backend/tests/test_models.py` | Test patterns for registry/service/API |

---

## 3. Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/models/deployment.py` | 95 | `Deployment`, `DeploymentStatus` |
| `backend/app/repositories/deployment_repository.py` | 96 | `DeploymentRepository` |
| `backend/app/services/inference_service.py` | 142 | `InferenceService` with adapter caching |
| `backend/app/services/deployment_service.py` | 373 | `DeploymentService` + 9 domain exceptions |
| `backend/app/schemas/deployment.py` | 94 | Request/response Pydantic schemas |
| `backend/app/api/v1/deployments.py` | 166 | Deployment API routes |
| `backend/alembic/versions/0007_create_deployments.py` | 148 | Migration for `deployments` table |
| `backend/tests/test_deployments.py` | 956 | 25 tests (repository, service, API, inference seam) |
| `docs/26_phase7_deployment_handoff.md` | — | This report |

---

## 4. Files Modified

| File | Change |
|------|--------|
| `backend/app/models/__init__.py` | Added `Deployment` import + `__all__` entry |
| `backend/app/api/v1/router.py` | Added `deployments` router import + include |
| `backend/app/main.py` | Added 10 Deployment/Inference exception handlers |
| `README.md` | Updated status line, added Deployment Service section, updated roadmap |
| `docs/17_architecture_decisions.md` | Expanded Deployment section with adapter loading, caching, lifecycle, and future-backend-swap decisions |
| `docs/00_project_context.md` | Updated phase, progress, tables, APIs, services, test count, scope, next deliverable |

No other files were touched.

---

## 5. Database Design

**Table: `deployments`**

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | UUID | NO | PK (BaseModel) |
| owner_id | UUID | NO | FK → users.id CASCADE |
| model_version_id | UUID | NO | FK → model_versions.id CASCADE |
| deployment_name | String(255) | NO | Indexed |
| status | enum | NO | pending/deploying/active/failed |
| endpoint_name | String(255) | NO | Indexed |
| created_at | DateTime(tz) | NO | BaseModel |
| updated_at | DateTime(tz) | NO | BaseModel |

**Indexes**:
- `ix_deployments_owner_id`
- `ix_deployments_model_version_id`
- `ix_deployments_deployment_name`
- `ix_deployments_endpoint_name`
- `ix_deployments_status`

No soft delete and no unique constraints in MVP.

---

## 6. Deployment Lifecycle

Exactly four states are supported:

```text
PENDING → DEPLOYING → ACTIVE
              ↘ FAILED
```

| State | Meaning |
|-------|---------|
| PENDING | Deployment created; adapter not yet loaded. |
| DEPLOYING | Activation in progress; model loading. |
| ACTIVE | Adapter loaded; `/generate` accepted. |
| FAILED | Activation failed; can be re-activated. |

**Allowed transitions**:
- `PENDING` → `DEPLOYING` → `ACTIVE` (via `POST /deployments/{id}/activate`)
- `FAILED` → `DEPLOYING` → `ACTIVE` (retry activation)
- `ACTIVE` stays `ACTIVE` (no-op activation rejected)

**Rejected transitions**:
- Activation of an already `ACTIVE` deployment
- Activation of a `DEPLOYING` deployment (must wait or fail first)
- `/generate` on `PENDING`, `DEPLOYING`, or `FAILED`

---

## 7. Repository Design

`DeploymentRepository` extends `BaseRepository[Deployment]`.

| Method | Purpose |
|--------|---------|
| `create_deployment(deployment)` | Persist a new deployment |
| `get_deployment(id)` | Fetch by UUID |
| `list_deployments(owner_id, limit, offset)` | Paginated list, newest first |
| `count_deployments(owner_id)` | Pagination total |
| `update_status(deployment, status)` | Set status and flush |
| `find_active_deployment(owner_id, model_version_id)` | Find an ACTIVE deployment matching filters |

No business logic lives in the repository.

---

## 8. Service Design

`DeploymentService` orchestrates deployment flow and enforces business rules.

| Method | Responsibility |
|--------|----------------|
| `create_deployment` | Validate version, reject archived/duplicate-active, create PENDING deployment |
| `get_deployment` | Ownership-checked fetch |
| `list_deployments` | Paginated, user-scoped list |
| `activate_deployment` | Validate adapter exists, load model, transition to ACTIVE or FAILED |
| `generate` | Verify ACTIVE, ensure model loaded, return generated text |

**Domain exceptions** (9 total):

| Exception | HTTP | Code |
|-----------|------|------|
| `DeploymentNotFoundError` | 404 | `DEPLOYMENT_NOT_FOUND` |
| `DeploymentAccessDeniedError` | 403 | `DEPLOYMENT_ACCESS_DENIED` |
| `DeploymentAlreadyActiveError` | 409 | `DEPLOYMENT_ALREADY_ACTIVE` |
| `DeploymentModelVersionNotFoundError` | 404 | `MODEL_VERSION_NOT_FOUND` |
| `DeploymentModelVersionArchivedError` | 409 | `MODEL_VERSION_ARCHIVED` |
| `DeploymentAdapterNotFoundError` | 404 | `ADAPTER_NOT_FOUND` |
| `DeploymentNotActiveError` | 409 | `DEPLOYMENT_NOT_ACTIVE` |
| `DeploymentInvalidStatusError` | 409 | `INVALID_DEPLOYMENT_STATUS` |
| `DeploymentError` | 400 | `DEPLOYMENT_ERROR` (fallback) |

---

## 9. Inference Design

`InferenceService` is a synchronous wrapper around `transformers` + `PEFT`.

| Method | Responsibility |
|--------|----------------|
| `load(artifact_path, base_model)` | Load tokenizer, quantized base model, and LoRA adapter; cache by key |
| `generate(prompt, ...)` | Encode prompt, run `model.generate`, decode only new tokens |
| `unload()` | Drop cached model/tokenizer |

**Default generation parameters** (from `docs/17_architecture_decisions.md`):
- `max_new_tokens`: 1024
- `temperature`: 0.7
- `do_sample`: True

The service raises `InferenceError` if no adapter is found, no model is loaded, or generation fails.

---

## 10. API Design

| Method | Path | Status | Purpose |
|--------|------|--------|---------|
| POST | `/api/v1/deployments` | 201 | Create a deployment |
| GET | `/api/v1/deployments` | 200 | List deployments for current user |
| GET | `/api/v1/deployments/{id}` | 200 | Get a deployment by ID |
| POST | `/api/v1/deployments/{id}/activate` | 200 | Load adapter and activate |
| POST | `/api/v1/deployments/{id}/generate` | 200 | Run inference |

No DELETE endpoints.

All responses use the standard `{success, data}` / `{success, error}` envelope. All endpoints require JWT auth via `CurrentUser` dependency.

### Example request/response

Create deployment:

```bash
curl -X POST http://localhost:8000/api/v1/deployments \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "model_version_id": "...",
    "deployment_name": "support-bot-prod",
    "endpoint_name": "support-bot-prod-v1"
  }'
```

Response:

```json
{
  "success": true,
  "data": {
    "id": "...",
    "owner_id": "...",
    "model_version_id": "...",
    "deployment_name": "support-bot-prod",
    "status": "pending",
    "endpoint_name": "support-bot-prod-v1",
    "created_at": "2025-06-27T00:00:00Z",
    "updated_at": "2025-06-27T00:00:00Z"
  }
}
```

---

## 11. Model Loading Strategy

1. Resolve adapter path from `TrainingJob.artifact_path` (fall back to `ModelVersion.artifact_path`).
2. Verify the directory exists on disk.
3. Set deployment status to `DEPLOYING`.
4. Load tokenizer from `artifact_path/tokenizer/` if present, otherwise from `artifact_path/`.
5. Load base model with 4-bit NF4 quantization (`BitsAndBytesConfig`) matching Phase 4.3 training.
6. Apply LoRA adapter via `PeftModel.from_pretrained`.
7. Set deployment status to `ACTIVE`.
8. On any `InferenceError`, set status to `FAILED` and raise a domain error.

`generate` also calls `load` defensively so a deployment that survives a process restart can still serve requests.

---

## 12. Caching Strategy

`InferenceService` is instantiated once at module import in `backend/app/api/v1/deployments.py`:

```python
_inference_service = InferenceService()
```

The same instance is injected into every request's `DeploymentService`, so the loaded model is reused across requests within the same process.

Cache key: `base_model:artifact_path`.

Behavior:
- `load(a, b)` called twice with the same arguments loads only once.
- `load(c, d)` with a different key unloads the previous model first.
- `unload()` clears the cache for tests and resource cleanup.

This is an in-process, single-instance cache. It is not shared across replicas or processes.

---

## 13. Validation Rules

| Condition | HTTP | Code |
|-----------|------|------|
| Model version not found / not owned | 404 | `MODEL_VERSION_NOT_FOUND` |
| Model version archived | 409 | `MODEL_VERSION_ARCHIVED` |
| Active deployment already exists for version | 409 | `DEPLOYMENT_ALREADY_ACTIVE` |
| Deployment not found / not owned | 404 / 403 | `DEPLOYMENT_NOT_FOUND` / `DEPLOYMENT_ACCESS_DENIED` |
| Adapter artifact missing on disk | 404 | `ADAPTER_NOT_FOUND` |
| Activation of already-active deployment | 409 | `DEPLOYMENT_ALREADY_ACTIVE` |
| Activation from non-PENDING/FAILED status | 409 | `INVALID_DEPLOYMENT_STATUS` |
| Inference on non-ACTIVE deployment | 409 | `DEPLOYMENT_NOT_ACTIVE` |

---

## 14. Test Results

### Phase 7 tests

```text
============================= test session starts =============================
platform win32 -- Python 3.11.4, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\PALLAB\Auto_finetuning\backend
configfile: pyproject.toml
plugins: anyio-3.7.1, langsmith-0.4.6, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_test_loop_scope=function
collected 25 items

tests/test_deployments.py .........................

========================= 25 passed in 5.99s =========================
```

### Full suite

```text
============================= test session starts =============================
platform win32 -- Python 3.11.4, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\PALLAB\Auto_finetuning\backend
testpaths: tests
plugins: anyio-3.7.1, langsmith-0.4.6, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_test_loop_scope=function
collected 363 items

tests\test_auth.py .................
tests\test_datasets.py ........................
tests\test_deployments.py .........................
tests\test_evaluations.py ............................
tests\test_health.py ....
tests\test_models.py .....................................
tests\test_security.py ........
tests\test_training_jobs.py ............................................
.......................
tests\test_training_module.py ..........................................
........................................................................
...........................................

====================== 363 passed, 24 warnings in 54.10s ======================
```

**Test summary**:

| Metric | Value |
|--------|-------|
| Phase 7 tests | 25 |
| Phase 7 passed | 25 |
| Full suite tests | 363 |
| Full suite passed | 363 |
| Full suite runtime | 54.10s |

---

## 15. Performance Notes

- **Synchronous inference**: `model.generate()` runs in the request handler. This is acceptable for MVP and single-instance use but will block the event loop for the duration of generation.
- **Adapter load cost**: Loading a quantized base model + LoRA adapter takes several seconds on a T4. The cache ensures this cost is paid once per process, not per request.
- **No batching**: Each `/generate` call processes one prompt. Throughput is limited to one generation at a time per replica.
- **No streaming**: Responses are returned only after the full generation completes.

---

## 16. Known Limitations

1. **Single-instance, in-process cache**: The loaded model is not shared across multiple backend replicas or processes. Scaling horizontally requires either per-replica model loading or a separate inference backend.
2. **Synchronous inference blocks the event loop**: Long generations will tie up a worker. A production backend (vLLM/TGI/Triton) running as a separate service is the intended replacement.
3. **No endpoint-name uniqueness**: `endpoint_name` is indexed but not unique. Two users (or the same user) could create deployments with the same endpoint name.
4. **No automatic activation**: Creating a deployment does not automatically load the adapter. The client must call `POST /deployments/{id}/activate`.
5. **No deployment deletion**: Failed or unused deployments remain in the database. A future phase can add soft delete or archival.
6. **No health check for inference backend**: The existing `/health` endpoint checks the API process, not whether a model is loaded.
7. **No input/output token limits enforced**: `GenerateRequest.prompt` validates length (1–4096 chars) but not tokens. `max_new_tokens` is fixed at 1024.
8. **No request timeout or cancellation**: A long-running generation cannot be cancelled by the caller in MVP.

---

## 17. Future Improvements

| Improvement | When | Effort |
|-------------|------|--------|
| Replace `InferenceService` with vLLM/TGI/Triton backend | Phase 7.1 | Medium |
| Async generation or dedicated inference worker | Phase 7.1 | Medium |
| Streaming `/generate` responses | Phase 7.1 | Small |
| Endpoint-name uniqueness / namespace | Phase 7.1 | Small |
| Batch inference endpoint | Phase 7.2 | Small |
| Deployment soft delete / archival | Phase 7.2 | Small |
| Auto-activation on create | Phase 7.2 | Small |
| Per-deployment model health metric | Phase 8 | Small |
| Request logging / latency metrics | Phase 8 | Small |

---

## 18. Final Assessment

**Phase 7 is COMPLETE.** All deliverables met:

1. ✅ `Deployment` ORM model with `DeploymentStatus` enum
2. ✅ `DeploymentRepository` with create/get/list/update/find-active
3. ✅ `DeploymentService` with lifecycle validation and ownership checks
4. ✅ `InferenceService` with adapter caching and real Phase 5.1 loading pattern
5. ✅ Deployment API (5 endpoints, no deletes)
6. ✅ Alembic migration `0007_create_deployments`
7. ✅ Pydantic request/response schemas
8. ✅ 25 new tests, all passing
9. ✅ Full suite passing (363/363)
10. ✅ README, architecture decisions, and project context updated

**Trade-offs made**:
- Synchronous, single-instance inference in the API process (simplest path that satisfies MVP).
- In-process model cache (no external state, easy to test, no distributed complexity).
- No automatic activation (explicit lifecycle gives the operator control and clear failure states).
- No endpoint-name uniqueness (MVP does not require global endpoint resolution).
- Failed deployments stay in the DB (auditability over deletion).

**Limitations not hidden**:
- Event-loop blocking generation.
- No horizontal model-cache sharing.
- No deletion endpoint.
- No token-level input validation.
- No production-grade inference backend.

### Test Summary

| Metric | Value |
|--------|-------|
| Phase 7 tests | 25 |
| Phase 7 passed | 25 |
| Full suite tests | 363 |
| Full suite passed | 363 |
| Full suite runtime | 54.10s |

> Phase 7 Deployment Service is ready for Phase 8 (Monitoring / Observability).

---

**STOP.** Phase 8 will not begin until explicitly requested and reviewed.
