# Phase 3: Training Job Infrastructure — Developer Handoff Report

**Date:** 2026-06-21  
**Author:** AI Development Agent  
**Phase:** 3.1 (Foundation) + 3.2 (Service Layer)  
**Status:** ✅ Complete — All 62 tests passing

---

## 1. Executive Summary

Phase 3 implements the Training Job Infrastructure for the LLM Forge platform. This phase delivers the complete backend pipeline for creating, queuing, tracking, and cancelling fine-tuning training jobs. The implementation follows a strict Repository Pattern architecture with FastAPI, PostgreSQL, Redis/RQ, and a MockTrainingRunner that simulates training execution.

**Key Deliverables:**

- Database migration for `training_jobs` table
- Domain model with 5 lifecycle statuses and 4 training types
- Repository layer with 8 methods
- Redis/RQ queue infrastructure
- Training service with business logic and 6 domain exceptions
- Mock training runner for development/testing
- 4 REST API endpoints
- 62 comprehensive tests (all passing)

---

## 2. Scope & Constraints

### In Scope (Phase 3.1 + 3.2)

- Database migration, domain model, repository layer
- Queue infrastructure (Redis + RQ)
- Training service with create/enqueue/get/list/cancel
- MockTrainingRunner (simulates training, creates mock artifacts)
- 4 API endpoints with full error handling
- Comprehensive test suite

### Out of Scope (Future Phases)

- Real training execution (Transformers, PEFT, LoRA, QLoRA, SFT)
- MLflow integration
- Colab/cloud execution targets
- Evaluation service
- Model registry
- Deployment service

### Required Revisions Applied

1. **No CREATED status** — Jobs start at QUEUED immediately upon creation
2. **No execution_target / PENDING_COLAB** — Removed entirely
3. **1 ACTIVE job per user** — Enforced via `count_active_jobs()` check
4. **TrainingConfig simplified to 4 fields** — epochs, batch_size, learning_rate, max_seq_length
5. **MockTrainingRunner** — Replaces real training infrastructure

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      API Layer                           │
│  POST /training-jobs          GET /training-jobs         │
│  GET /training-jobs/{id}      POST /training-jobs/{id}/cancel │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  Service Layer                           │
│  TrainingService                                         │
│  ├─ create_job()  → validate → create → enqueue → commit│
│  ├─ get_job()     → fetch → ownership check              │
│  ├─ list_jobs()   → paginated query                      │
│  └─ cancel_job()  → validate → cancel RQ → update status │
└──────┬──────────────────────────────┬───────────────────┘
       │                              │
┌──────▼──────────┐    ┌──────────────▼───────────────────┐
│  Repository      │    │  Queue Infrastructure            │
│  TrainingJobRepo │    │  QueueService → Redis/RQ         │
│  DatasetRepo     │    │  MockTrainingRunner (worker)     │
└──────┬──────────┘    └──────────────────────────────────┘
       │
┌──────▼──────────┐
│  PostgreSQL      │
│  training_jobs   │
└─────────────────┘
```

---

## 4. Database Schema

### Migration: `0004_create_training_jobs.py`

**Table:** `training_jobs`

| Column               | Type         | Constraints                       | Description                               |
| -------------------- | ------------ | --------------------------------- | ----------------------------------------- |
| `id`                 | UUID         | PK, default uuid4                 | Primary key                               |
| `user_id`            | UUID         | FK → users.id, CASCADE, INDEX     | Job owner                                 |
| `dataset_id`         | UUID         | FK → datasets.id, CASCADE, INDEX  | Training dataset                          |
| `dataset_version_id` | UUID         | FK → dataset_versions.id, CASCADE | Specific version                          |
| `status`             | ENUM         | NOT NULL, INDEX, default 'queued' | queued/running/completed/failed/cancelled |
| `base_model`         | VARCHAR(255) | NOT NULL                          | HF model identifier                       |
| `training_type`      | ENUM         | NOT NULL                          | sft/lora/qlora/peft                       |
| `configuration`      | JSON         | NOT NULL                          | Training hyperparameters                  |
| `artifact_path`      | VARCHAR(500) | NULLABLE                          | Path to trained model                     |
| `started_at`         | TIMESTAMPTZ  | NULLABLE                          | Job start timestamp                       |
| `completed_at`       | TIMESTAMPTZ  | NULLABLE                          | Job completion timestamp                  |
| `error_message`      | TEXT         | NULLABLE                          | Error details on failure                  |
| `deleted_at`         | TIMESTAMPTZ  | NULLABLE                          | Soft delete                               |
| `created_at`         | TIMESTAMPTZ  | NOT NULL, server_default now()    | Creation timestamp                        |
| `updated_at`         | TIMESTAMPTZ  | NOT NULL, server_default now()    | Last update timestamp                     |

**Indexes:** user_id, status, dataset_id, created_at  
**Foreign Keys:** user_id → users(id) CASCADE, dataset_id → datasets(id) CASCADE, dataset_version_id → dataset_versions(id) CASCADE

---

## 5. Domain Models

### TrainingJobStatus (Enum)

```python
class TrainingJobStatus(str, enum.Enum):
    QUEUED = "queued"       # Enqueued in RQ, waiting for worker
    RUNNING = "running"     # Worker picked up the job
    COMPLETED = "completed" # Training finished successfully
    FAILED = "failed"       # Training failed with error
    CANCELLED = "cancelled" # User cancelled the job
```

### TrainingType (Enum)

```python
class TrainingType(str, enum.Enum):
    SFT = "sft"
    LORA = "lora"
    QLORA = "qlora"
    PEFT = "peft"
```

### TrainingConfig (Pydantic v2)

```python
class TrainingConfig(PydanticBaseModel):
    model_config = ConfigDict(extra="forbid")
    epochs: int = Field(ge=1, le=100)
    batch_size: int = Field(ge=1, le=256)
    learning_rate: float = Field(ge=1e-7, le=1.0)
    max_seq_length: int = Field(ge=64, le=32768)
```

### TrainingJob (ORM Model)

- Inherits from `BaseModel` (UUIDMixin + TimestampMixin)
- Uses `SAEnum` for status and training_type columns
- Uses `JSON` type for configuration (cross-compatible with SQLite and PostgreSQL)
- Has `dataset` relationship (lazy="selectin")
- Has `is_deleted` property

---

## 6. Repository Layer

### TrainingJobRepository (`app/repositories/training_job_repository.py`)

Extends `BaseRepository[TrainingJob]` with 8 methods:

| Method                 | Signature                                                            | Description                                |
| ---------------------- | -------------------------------------------------------------------- | ------------------------------------------ |
| `create`               | `(job: TrainingJob) → TrainingJob`                                   | Persist new job                            |
| `get_by_id`            | `(job_id: UUID) → TrainingJob \| None`                               | Fetch by PK, excludes soft-deleted         |
| `list_for_user`        | `(user_id, limit, offset) → list[TrainingJob]`                       | Paginated list, ordered by created_at DESC |
| `count_for_user`       | `(user_id: UUID) → int`                                              | Total non-deleted jobs for pagination      |
| `count_active_jobs`    | `(user_id: UUID) → int`                                              | Count QUEUED + RUNNING jobs                |
| `update_status`        | `(job_id, status, started_at?, completed_at?) → TrainingJob \| None` | Update status + timestamps                 |
| `update_artifact_path` | `(job_id, artifact_path) → TrainingJob \| None`                      | Set artifact path                          |
| `update_error`         | `(job_id, error_message) → TrainingJob \| None`                      | Set FAILED + error + completed_at          |

---

## 7. Queue Infrastructure

### QueueService (`app/services/queue_service.py`)

Thin wrapper around Redis Queue (RQ):

- **`get_redis_connection()`** — Creates Redis connection from `settings.redis_url`
- **`get_training_queue()`** — Returns RQ `Queue("training")`
- **`QueueService.queue`** — Lazy-initialized property
- **`enqueue(job_id)`** — Enqueues `mock_training_runner` with 10min timeout, 1hr result TTL
- **`cancel_queued_job(job_id)`** — Searches queue for matching job and cancels it
- **`get_queue_status()`** — Returns dict with queued/started/finished/failed counts

### Redis URL Format

```
redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}
```

---

## 8. Service Layer

### TrainingService (`app/services/training_service.py`)

**Dependencies:** `TrainingJobRepository`, `DatasetRepository`, `QueueService`

**Methods:**

#### `create_job(*, user_id, request) → TrainingJobResponse`

1. Validate dataset ownership via `DatasetRepository.get_by_id_and_owner()`
2. Check active job limit via `count_active_jobs()` — raises `ActiveJobLimitExceededError`
3. Create `TrainingJob` with status=QUEUED
4. Enqueue via `QueueService.enqueue()`
5. Commit and return response

#### `get_job(job_id, *, user_id) → TrainingJobResponse`

1. Fetch job by ID
2. Validate ownership (`job.user_id == user_id`)
3. Raises `TrainingJobNotFoundError` or `TrainingJobAccessDeniedError`

#### `list_jobs(*, user_id, limit, offset) → TrainingJobListResponse`

1. Query `list_for_user()` + `count_for_user()`
2. Return paginated response with items, total, limit, offset

#### `cancel_job(job_id, *, user_id) → TrainingJobResponse`

1. Validate ownership
2. Validate status is QUEUED or RUNNING — raises `TrainingJobNotCancellableError`
3. If QUEUED: cancel RQ job via `QueueService.cancel_queued_job()`
4. Update status to CANCELLED with `completed_at`

### Domain Exceptions

| Exception                        | HTTP Status | Error Code                     |
| -------------------------------- | ----------- | ------------------------------ |
| `TrainingJobNotFoundError`       | 404         | `TRAINING_JOB_NOT_FOUND`       |
| `TrainingJobAccessDeniedError`   | 403         | `TRAINING_JOB_ACCESS_DENIED`   |
| `ActiveJobLimitExceededError`    | 409         | `ACTIVE_JOB_LIMIT_EXCEEDED`    |
| `DatasetNotOwnedError`           | 403         | `DATASET_NOT_OWNED`            |
| `TrainingJobNotCancellableError` | 409         | `TRAINING_JOB_NOT_CANCELLABLE` |
| `TrainingJobError`               | 400         | `TRAINING_JOB_ERROR`           |

---

## 9. Mock Training Runner

### `app/workers/mock_training_runner.py`

**Purpose:** Synchronous RQ worker function that simulates training for development/testing.

**Key Design Decision:** Uses **synchronous** SQLAlchemy sessions because RQ workers are synchronous. Connects via `settings.database_url_sync` (PostgreSQL sync URL).

**Workflow:**

1. Load `TrainingJob` from database
2. Mark status → RUNNING, set `started_at`
3. Sleep 2 seconds (simulate training)
4. Create mock artifact JSON at `{LOCAL_STORAGE_PATH}/artifacts/{job_id}/model.json`
5. Mark status → COMPLETED, set `completed_at` and `artifact_path`
6. On error: mark status → FAILED, set `error_message` and `completed_at`

**Mock Artifact Format:**

```json
{
    "job_id": "...",
    "base_model": "...",
    "training_type": "...",
    "configuration": {...},
    "completed_at": "...",
    "mock": true
}
```

---

## 10. API Endpoints

All endpoints are prefixed with `/api/v1/training-jobs` and require authentication.

### POST `/api/v1/training-jobs` — Create Training Job

- **Status:** 201 Created
- **Auth:** Required
- **Request Body:**

```json
{
  "dataset_id": "uuid",
  "dataset_version_id": "uuid",
  "base_model": "meta-llama/Llama-3.1-8B",
  "training_type": "sft",
  "configuration": {
    "epochs": 3,
    "batch_size": 8,
    "learning_rate": 2e-5,
    "max_seq_length": 2048
  }
}
```

- **Response:** `{success: true, data: TrainingJobResponse}`
- **Errors:** 403 (dataset not owned), 409 (active job limit), 422 (validation)

### GET `/api/v1/training-jobs` — List Training Jobs

- **Status:** 200 OK
- **Auth:** Required
- **Query Params:** `limit` (1-500, default 100), `offset` (≥0, default 0)
- **Response:** `{success: true, data: {items: [...], total, limit, offset}}`

### GET `/api/v1/training-jobs/{job_id}` — Get Training Job

- **Status:** 200 OK
- **Auth:** Required (owner only)
- **Response:** `{success: true, data: TrainingJobResponse}`
- **Errors:** 404 (not found), 403 (access denied)

### POST `/api/v1/training-jobs/{job_id}/cancel` — Cancel Training Job

- **Status:** 200 OK
- **Auth:** Required (owner only)
- **Response:** `{success: true, data: TrainingJobResponse}`
- **Errors:** 404 (not found), 403 (access denied), 409 (not cancellable)

---

## 11. Error Handling

All exceptions are registered as FastAPI exception handlers in `app/main.py` within the `create_app()` factory function. Each handler returns the standard error envelope:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message"
  }
}
```

**Exception Handler Registration (Phase 3 additions):**

```python
@app.exception_handler(TrainingJobNotFoundError)
@app.exception_handler(TrainingJobAccessDeniedError)
@app.exception_handler(ActiveJobLimitExceededError)
@app.exception_handler(DatasetNotOwnedError)
@app.exception_handler(TrainingJobNotCancellableError)
@app.exception_handler(TrainingJobError)
```

---

## 12. Configuration

### Environment Variables (Phase 3 relevant)

| Variable             | Default           | Description             |
| -------------------- | ----------------- | ----------------------- |
| `REDIS_HOST`         | `localhost`       | Redis server hostname   |
| `REDIS_PORT`         | `6379`            | Redis server port       |
| `REDIS_DB`           | `0`               | Redis database number   |
| `LOCAL_STORAGE_PATH` | `./local_storage` | Path for mock artifacts |

### Redis URL Property

```python
@property
def redis_url(self) -> str:
    return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
```

---

## 13. Testing Strategy

### Test File: `backend/tests/test_training_jobs.py`

**62 tests, all passing.** Test categories:

| Category                   | Count | Description                                 |
| -------------------------- | ----- | ------------------------------------------- |
| Create - Success           | 4     | sft, lora, qlora, peft training types       |
| Create - Ownership         | 1     | Dataset not owned → 403                     |
| Create - Active Limit      | 1     | Second active job → 409                     |
| Create - After Cancel      | 1     | New job allowed after cancel                |
| Create - After Complete    | 1     | New job allowed after completion            |
| Get - Success              | 1     | Fetch own job                               |
| Get - Not Found            | 1     | Non-existent job → 404                      |
| Get - Access Denied        | 1     | Other user's job → 403                      |
| List - Empty               | 1     | No jobs → empty list                        |
| List - With Items          | 1     | Jobs returned in order                      |
| List - Pagination          | 1     | limit/offset respected                      |
| List - Offset              | 1     | Offset skips items                          |
| List - Scoped              | 1     | Only shows own jobs                         |
| Cancel - Queued            | 1     | Cancel queued job                           |
| Cancel - Running           | 1     | Cancel running job                          |
| Cancel - Completed         | 1     | Completed → 409                             |
| Cancel - Failed            | 1     | Failed → 409                                |
| Cancel - Already Cancelled | 1     | Cancelled → 409                             |
| Cancel - Not Found         | 1     | Non-existent → 404                          |
| Cancel - Access Denied     | 1     | Other user's → 403                          |
| Auth Required              | 4     | All endpoints require auth                  |
| Schema Validation          | 7     | Extra fields, missing fields, invalid types |
| Config Bounds              | 13    | Min/max/boundary for all 4 fields           |
| Response Shape             | 2     | All fields present, pagination fields       |
| Invalid UUID               | 2     | Malformed UUID → 422                        |
| Multi-User Isolation       | 2     | Cross-user visibility, per-user limits      |
| Repository Unit Tests      | 9     | All 8 repo methods + not-found cases        |

### Key Fixtures

- **`mock_queue_service`** — `MagicMock(spec=QueueService)`, prevents actual Redis/RQ calls
- **`override_queue`** — Overrides `_get_training_service` dependency to inject mock queue
- **`auth_headers`** — Registers user, returns `{"Authorization": "Bearer <token>"}`

### Running Tests

```bash
# Training job tests only
.venv\Scripts\python.exe -m pytest tests/test_training_jobs.py -v

# All Phase 2 + Phase 3 tests
.venv\Scripts\python.exe -m pytest tests/test_datasets.py tests/test_training_jobs.py -v
```

---

## 14. Deployment Notes

### Prerequisites

- PostgreSQL database with migrations applied (0001–0004)
- Redis server running and accessible
- Python 3.12+ with dependencies installed

### RQ Worker

The MockTrainingRunner requires an RQ worker process:

```bash
rq worker training --url redis://localhost:6379/0
```

### Database Migrations

```bash
alembic upgrade head  # Applies migration 0004
```

### Dependencies Added

- `rq` (Redis Queue) — installed in venv

---

## 15. Migration Guide

### New Files Created

```
backend/
├── alembic/versions/0004_create_training_jobs.py   # Migration
├── app/
│   ├── models/training_job.py                       # Domain model
│   ├── repositories/training_job_repository.py      # Repository
│   ├── services/
│   │   ├── queue_service.py                         # Queue wrapper
│   │   └── training_service.py                      # Business logic
│   ├── schemas/training_job.py                      # API schemas
│   ├── api/v1/training_jobs.py                      # API routes
│   └── workers/mock_training_runner.py              # Mock worker
└── tests/test_training_jobs.py                      # Test suite
```

### Modified Files

```
backend/app/
├── models/__init__.py           # Added TrainingJob import
├── api/v1/router.py             # Added training_jobs router
└── main.py                      # Added 6 exception handlers
```

---

## 16. Known Limitations

1. **Mock Training Only** — No real model training. The MockTrainingRunner sleeps 2 seconds and creates a JSON artifact. Real training (Transformers/PEFT/LoRA) is planned for Phase 4+.

2. **No Training Progress Tracking** — The current implementation doesn't expose training progress (e.g., current epoch, loss). This would require a progress callback mechanism in the worker.

3. **No Job Timeout Enforcement** — RQ's `job_timeout="10m"` is set but the mock runner always completes in ~2 seconds. Real training jobs may need dynamic timeouts.

4. **No Automatic Retry** — Failed jobs are not automatically retried. This would need to be implemented in the worker or queue configuration.

5. **Pre-existing Test Failures** — Auth tests (13) and health tests (3) fail with `'coroutine' object has no attribute 'status_code'`. These tests use the synchronous `TestClient` but the `client` fixture now provides an async `AsyncClient`. These failures are **not caused by Phase 3 changes** and existed before this phase.

6. **SQLite DateTime Limitation** — The test database uses SQLite which only accepts Python `datetime` objects (not strings) for DateTime columns. This is handled in tests but worth noting for any future test development.

---

## 17. Future Work (Phase 4+)

- **Real Training Runners** — Integrate Transformers, PEFT, LoRA/QLoRA, SFT trainers
- **GPU Resource Management** — CUDA device allocation, multi-GPU support
- **Training Progress** — WebSocket or polling-based progress updates
- **Checkpointing** — Save/resume training from checkpoints
- **Hyperparameter Validation** — Model-specific config validation
- **MLflow Integration** — Experiment tracking and model registry
- **Evaluation Service** — Post-training evaluation metrics
- **Model Registry** — Versioned model storage and serving

---

## 18. API Examples

### Create a Training Job

```bash
curl -X POST http://localhost:8000/api/v1/training-jobs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "550e8400-e29b-41d4-a716-446655440000",
    "dataset_version_id": "660e8400-e29b-41d4-a716-446655440001",
    "base_model": "meta-llama/Llama-3.1-8B",
    "training_type": "sft",
    "configuration": {
      "epochs": 3,
      "batch_size": 8,
      "learning_rate": 2e-5,
      "max_seq_length": 2048
    }
  }'
```

### List Training Jobs

```bash
curl http://localhost:8000/api/v1/training-jobs?limit=10&offset=0 \
  -H "Authorization: Bearer <token>"
```

### Get a Training Job

```bash
curl http://localhost:8000/api/v1/training-jobs/770e8400-e29b-41d4-a716-446655440002 \
  -H "Authorization: Bearer <token>"
```

### Cancel a Training Job

```bash
curl -X POST http://localhost:8000/api/v1/training-jobs/770e8400-e29b-41d4-a716-446655440002/cancel \
  -H "Authorization: Bearer <token>"
```

---

## 19. Troubleshooting

| Issue                               | Cause                                     | Solution                                   |
| ----------------------------------- | ----------------------------------------- | ------------------------------------------ |
| `ACTIVE_JOB_LIMIT_EXCEEDED`         | User already has QUEUED/RUNNING job       | Cancel existing job or wait for completion |
| `DATASET_NOT_OWNED`                 | Dataset belongs to another user           | Use a dataset you own                      |
| `TRAINING_JOB_NOT_CANCELLABLE`      | Job is COMPLETED/FAILED/already CANCELLED | Only QUEUED/RUNNING jobs can be cancelled  |
| RQ jobs not processing              | RQ worker not running                     | Start: `rq worker training`                |
| Redis connection refused            | Redis not running                         | Start Redis server                         |
| `ImportError: mock_training_runner` | Worker can't find module                  | Run worker from `backend/` directory       |

---

## 20. Appendix

### File Listing with Line Counts

| File                                            | Lines | Purpose                       |
| ----------------------------------------------- | ----- | ----------------------------- |
| `alembic/versions/0004_create_training_jobs.py` | ~80   | Database migration            |
| `app/models/training_job.py`                    | ~200  | Domain model + enums + config |
| `app/repositories/training_job_repository.py`   | ~150  | Repository with 8 methods     |
| `app/services/queue_service.py`                 | ~120  | Redis/RQ queue wrapper        |
| `app/services/training_service.py`              | ~250  | Business logic + exceptions   |
| `app/schemas/training_job.py`                   | ~100  | Pydantic v2 API schemas       |
| `app/api/v1/training_jobs.py`                   | ~160  | 4 API endpoints               |
| `app/workers/mock_training_runner.py`           | ~200  | Mock RQ worker                |
| `tests/test_training_jobs.py`                   | ~900  | 62 tests                      |

### Technology Stack

- **Framework:** FastAPI 0.115+
- **ORM:** SQLAlchemy 2.0 (async)
- **Database:** PostgreSQL (production), SQLite (testing)
- **Queue:** Redis + RQ (Redis Queue)
- **Validation:** Pydantic v2
- **Testing:** pytest + httpx AsyncClient
- **Python:** 3.14.2

### Key Architectural Decisions

1. **Repository Pattern** — All database access goes through repositories; services never touch the session directly
2. **Synchronous RQ Workers** — MockTrainingRunner uses sync SQLAlchemy because RQ workers are synchronous
3. **JSON (not JSONB) for Configuration** — Uses SQLAlchemy's `JSON` type which auto-selects JSONB on PostgreSQL and JSON on SQLite, ensuring cross-database compatibility
4. **Lazy Queue Initialization** — QueueService uses a lazy property to avoid connecting to Redis at import time
5. **Dependency Injection** — FastAPI's `Depends` is used throughout; `Annotated` type aliases for cleaner signatures
6. **Soft Delete** — Jobs use `deleted_at` timestamp rather than hard deletes
7. **Ownership Enforcement** — Every operation validates that the requesting user owns the resource
