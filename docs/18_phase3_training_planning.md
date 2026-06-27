# Phase 3 — Training Job Infrastructure Planning Report

**Date:** 2026-06-20
**Status:** Planning Complete — Awaiting Implementation
**Prerequisite:** Phase 2 (Dataset Service) ✅ Complete

---

## 1. Executive Summary

This report designs the complete Training Job Infrastructure for LLM Forge. It covers the database schema, status lifecycle, queue architecture, worker design, API contracts, security model, and integration points for future QLoRA/Colab/MLflow features.

**Key Design Principles:**

- **Separation of Concerns:** Metadata lives in PostgreSQL; artifacts live in MinIO/local storage.
- **Async by Default:** All training operations are asynchronous via Redis + RQ.
- **Ownership-First:** Every job is tied to a user; no cross-user visibility.
- **Extensible Configuration:** `TrainingConfig` is a JSONB/schema hybrid supporting future methods (LoRA, QLoRA, SFT, DPO, RLHF).
- **Fault Tolerance:** Jobs survive worker crashes via checkpointing and state persistence.

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LLM Forge — Training Architecture                 │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────┐      ┌──────────────┐      ┌──────────────────────────┐
│   Client     │      │   FastAPI    │      │      PostgreSQL            │
│  (React)     │◄────►│   Backend    │◄────►│  ┌────────────────────┐   │
│              │      │              │      │  │  users              │   │
│  POST /jobs  │      │  ┌────────┐  │      │  │  datasets           │   │
│  GET  /jobs  │      │  │ Auth   │  │      │  │  dataset_versions   │   │
│  GET /jobs/1 │      │  │ Layer  │  │      │  │  training_jobs ⬅──┘   │
│  POST /cancel│      │  └───┬────┘  │      │  └────────────────────┘   │
│              │      │      │      │      └──────────────────────────┘
└──────────────┘      │  ┌───▼────┐  │
                      │  │Training│  │      ┌──────────────────────────┐
                      │  │Service │  │      │        Redis Queue         │
                      │  └───┬────┘  │      │  ┌────────────────────┐   │
                      │      │      │      │  │  training_jobs     │   │
                      │  ┌───▼────┐  │      │  │  ┌─────────────┐   │   │
                      │  │Dataset │  │      │  │  │ job_id: 1   │   │   │
                      │  │Service │  │      │  │  │ status: Q   │   │   │
                      │  └────────┘  │      │  │  │ payload: {} │   │   │
                      └──────────────┘      │  │  └─────────────┘   │   │
                                            │  └────────────────────┘   │
                                            └──────────────────────────┘
                                                       │
                                                       ▼
                                            ┌──────────────────────────┐
                                            │      RQ Worker(s)        │
                                            │  ┌────────────────────┐  │
                                            │  │ MockTrainingRunner │  │
                                            │  │ ┌────────────────┐ │  │
                                            │  │ │ Simulate Train │ │  │
                                            │  │ │ Sleep Duration │ │  │
                                            │  │ │ Produce Mock   │ │  │
                                            │  │ │ Artifacts      │ │  │
                                            │  │ │ Update Status  │ │  │
                                            │  │ └────────────────┘ │  │
                                            │  └────────────────────┘  │
                                            └──────────────────────────┘
                                                       │
                                                       ▼
                                            ┌──────────────────────────┐
                                            │    Artifact Storage      │
                                            │  ┌────────────────────┐   │
                                            │  │ artifacts/         │   │
                                            │  │  ├─ model/         │   │
                                            │  │  ├─ tokenizer/     │   │
                                            │  │  ├─ adapter/       │   │
                                            │  │  └─ logs/          │   │
                                            │  └────────────────────┘   │
                                            └──────────────────────────┘
```

---

## 3. Database Design

### 3.1 `training_jobs` Table

| Column               | Type          | Constraints                        | Description                                      |
| -------------------- | ------------- | ---------------------------------- | ------------------------------------------------ |
| `id`                 | UUID          | PK, auto                           | Primary identifier for the job.                  |
| `user_id`            | UUID          | FK → users.id, NOT NULL, INDEX     | Owner of the job. Enforces ownership.            |
| `dataset_id`         | UUID          | FK → datasets.id, NOT NULL, INDEX  | Dataset used for training.                       |
| `dataset_version_id` | UUID          | FK → dataset_versions.id, NOT NULL | Specific version of the dataset.                 |
| `status`             | VARCHAR(20)   | NOT NULL, INDEX                    | Current lifecycle state (see §4).                |
| `base_model`         | VARCHAR(100)  | NOT NULL                           | e.g., "mistral-7b-instruct", "llama-3-8b".       |
| `training_type`      | VARCHAR(20)   | NOT NULL                           | "sft", "lora", "qlora", "peft". Extensible.      |
| `configuration`      | JSONB         | NOT NULL, DEFAULT '{}'             | Full training config (see §5).                   |
| `artifact_path`      | VARCHAR(1024) | NULL                               | Path to stored artifacts (model, adapter, logs). |
| `started_at`         | TIMESTAMPTZ   | NULL                               | When the job began execution.                    |
| `completed_at`       | TIMESTAMPTZ   | NULL                               | When the job finished (success or failure).      |
| `error_message`      | TEXT          | NULL                               | Human-readable error on failure.                 |
| `created_at`         | TIMESTAMPTZ   | NOT NULL, DEFAULT now()            | Job creation timestamp.                          |
| `updated_at`         | TIMESTAMPTZ   | NOT NULL, DEFAULT now()            | Last update timestamp.                           |

### 3.2 Indexes

```sql
CREATE INDEX idx_training_jobs_user_id ON training_jobs(user_id);
CREATE INDEX idx_training_jobs_status ON training_jobs(status);
CREATE INDEX idx_training_jobs_dataset_id ON training_jobs(dataset_id);
CREATE INDEX idx_training_jobs_created_at ON training_jobs(created_at DESC);
```

### 3.3 Field Explanations

- **`id`**: UUID v4 for global uniqueness and safe exposure in APIs.
- **`user_id`**: Enforces ownership; every query filters by this.
- **`dataset_id` + `dataset_version_id`**: Immutable references to the exact data used. Prevents training on deleted/modified datasets.
- **`status`**: Drives the state machine (see §4). Indexed for fast queue polling.
- **`base_model`**: String identifier for the HuggingFace model name. Validated at creation.
- **`training_type`**: Enum-like string. Allows future methods without schema changes.
- **`configuration`**: JSONB stores the full `TrainingConfig`. Flexible for future parameters.
- **`artifact_path`**: Relative path to the artifact directory. NULL until artifacts are saved.
- **`started_at` / `completed_at`**: Track duration and identify stale jobs.
- **`error_message`**: Populated on failure for debugging. Cleared on retry.

---

## 4. Status Lifecycle

### 4.1 States

```
        ┌─────────┐
        │  QUEUED  │◄── Initial state on job creation (enqueued in Redis)
        └────┬────┘
             │
             ▼
        ┌─────────┐     ┌─────────┐
        │ RUNNING  │────►│ CANCELLED│◄── User-initiated cancellation
        └────┬────┘     └─────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
┌─────────┐      ┌─────────┐
│COMPLETED│      │  FAILED  │◄── Error or worker crash
└─────────┘      └─────────┘
```

### 4.2 Valid Transitions

| From → To           | Trigger                        | Actor                       |
| ------------------- | ------------------------------ | --------------------------- |
| QUEUED → RUNNING    | Worker picks up job            | RQ Worker                   |
| RUNNING → COMPLETED | Training finished successfully | MockTrainingRunner          |
| RUNNING → FAILED    | Exception or crash             | MockTrainingRunner / Worker |
| RUNNING → CANCELLED | User cancels active job        | API + Worker signal         |
| QUEUED → CANCELLED  | User cancels before start      | API (removes from queue)    |

### 4.3 Invalid Transitions (Guarded)

- COMPLETED → _any_ (job is terminal)
- CANCELLED → _any_ (job is terminal)
- FAILED → _any_ (job is terminal; no retry in MVP)
- QUEUED → COMPLETED (must pass through RUNNING)

---

## 5. Training Configuration Design

### 5.1 `TrainingConfig` Schema (Pydantic v2)

The MVP `TrainingConfig` is intentionally minimal — only the four fields needed to drive a simulated training run. Future phases will extend this schema with optimizer, scheduler, and LoRA/QLoRA fields.

```python
class TrainingConfig(BaseModel):
    epochs: int = Field(default=3, ge=1, le=10)
    batch_size: int = Field(default=4, ge=1, le=16)
    learning_rate: float = Field(default=2e-4, gt=0)
    max_seq_length: int = Field(default=2048, ge=128, le=4096)
```

### 5.2 Storage in Database

- Stored as **JSONB** in `training_jobs.configuration`.
- Pydantic validates at API layer before persistence.
- Worker deserializes the 4-field config and passes values to `MockTrainingRunner`.

### 5.3 Design Rationale

| Decision             | Rationale                                                                                                                                     |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Only 4 fields in MVP | Keeps Phase 3 focused on infrastructure (DB, queue, worker, API). Real training knobs (optimizer, LoRA, QLoRA) are deferred to a later phase. |
| Flat structure       | Easier to query and index in JSONB than nested objects.                                                                                       |
| Bounded ranges       | `epochs ≤ 10`, `batch_size ≤ 16`, `max_seq_length ≤ 4096` prevent runaway resource use.                                                       |
| JSONB column         | Schema can be extended in future phases without DB migrations.                                                                                |

---

## 6. Queue Architecture

### 6.1 Component Flow

```
┌─────────┐    enqueue    ┌─────────┐    dequeue    ┌─────────┐
│ FastAPI │──────────────►│  Redis  │──────────────►│   RQ    │
│  API    │               │  Queue  │               │ Worker  │
└─────────┘               └─────────┘               └────┬────┘
                                                            │
                                                            ▼
                                                    ┌─────────────┐
                                                    │  Training   │
                                                    │   Runner    │
                                                    └─────────────┘
```

### 6.2 Job Submission Flow

1. **Client** sends `POST /training-jobs` with config.
2. **FastAPI** validates config via Pydantic.
3. **TrainingService**:
   - Verifies dataset ownership and status (READY).
   - Verifies user has no ACTIVE jobs (status `QUEUED` or `RUNNING`).
   - Creates `training_jobs` row with status `QUEUED`.
   - Enqueues job to Redis RQ queue with `job_id = training_job.id`.
4. **Response** returns `202 Accepted` with job ID and status.

### 6.3 Job Execution Flow

1. **RQ Worker** polls Redis and dequeues job.
2. **Worker** updates `training_jobs.status` → `RUNNING`, sets `started_at`.
3. **MockTrainingRunner** executes:
   - Read `TrainingConfig` (epochs, batch_size, learning_rate, max_seq_length) from the job row.
   - **Simulate training**: sleep for a duration proportional to `epochs` (e.g. `epochs × 30s`).
   - **Produce mock artifacts**: write a dummy `model.bin` and `training.log` to `artifacts/{job_id}/`.
   - **Update status** to `COMPLETED` (or `FAILED` if the simulation raises).
4. On success: status → `COMPLETED`, set `completed_at`, update `artifact_path`.
5. On failure: status → `FAILED`, set `error_message`, set `completed_at`.

> **Note:** No real model loading, GPU work, or `transformers.Trainer` invocation occurs in Phase 3. The `MockTrainingRunner` exists so the entire infrastructure (DB → queue → worker → API) can be exercised end-to-end before real training is wired in.

### 6.4 Failure Handling

| Failure Type               | Handling Strategy                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------- |
| **Worker Crash**           | Job remains `RUNNING` in DB. Heartbeat timeout (5 min) marks as `FAILED`. Retry from latest checkpoint. |
| **OOM Error**              | Catch `RuntimeError`; reduce batch size or enable gradient checkpointing; retry once.                   |
| **Invalid Config**         | Fail fast at API validation; job never enqueued.                                                        |
| **Dataset Not Found**      | Fail at worker startup; status → `FAILED` with descriptive message.                                     |
| **Model Download Failure** | Retry with exponential backoff (3 attempts); then fail.                                                 |

### 6.5 Retry Policy

```python
# RQ retry configuration
retry = Retry(
    max=3,
    interval=[60, 300, 900],  # 1min, 5min, 15min
    exceptions=[ConnectionError, TimeoutError]
)
```

---

## 7. Worker Design

### 7.1 Responsibilities

| Area                    | Responsibility                                                                                  |
| ----------------------- | ----------------------------------------------------------------------------------------------- |
| **Startup**             | Connect to Redis, PostgreSQL, MinIO. Register heartbeat.                                        |
| **Job Execution**       | Dequeue → Update DB → Run `MockTrainingRunner` → Update DB → Save mock artifacts.               |
| **MockTrainingRunner**  | Simulates training: sleeps for `epochs × 30s`, writes dummy `model.bin` + `training.log`.       |
| **Heartbeat**           | Every 30 seconds: update `training_jobs.updated_at`. Allows crash detection.                    |
| **Cancellation**        | Listen for SIGTERM/SIGINT. Stop the runner, update DB to `CANCELLED`, clean up.                 |
| **Shutdown**            | Graceful: finish current job, reject new jobs. Forced: mark job `FAILED`, exit.                 |
| **Resource Monitoring** | Log CPU usage and elapsed time to structured logs every 60s. (No GPU monitoring — mock runner.) |

### 7.2 Worker Lifecycle

```
┌─────────────┐
│   START     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Connect    │──► Redis, PostgreSQL, MinIO
│  Resources  │──► Verify CUDA, GPU memory
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   IDLE      │◄── Heartbeat every 30s
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  RUNNING    │◄── Execute training job
│   (job)     │
└──────┬──────┘
       │
   ┌───┴───┐
   ▼       ▼
┌─────┐ ┌─────┐
│DONE │ │FAIL │
└──┬──┘ └──┬──┘
   │       │
   ▼       ▼
┌─────────────┐
│   IDLE      │◄── Return to pool
└─────────────┘
       │
       ▼
┌─────────────┐
│   STOP      │◄── SIGTERM received
└─────────────┘
```

### 7.3 Cancellation Mechanism

1. User sends `POST /training-jobs/{id}/cancel`.
2. API updates DB status to `CANCELLED`.
3. If job is `QUEUED`: RQ removes from queue.
4. If job is `RUNNING`: API sends cancellation signal (Redis pub/sub or RQ's `send_stop_job_command`).
5. Worker catches signal, saves checkpoint, updates DB, exits gracefully.

---

## 8. API Design

### 8.1 Endpoints

#### `POST /api/v1/training-jobs`

**Request:**

```json
{
  "dataset_id": "uuid",
  "dataset_version_id": "uuid",
  "base_model": "mistral-7b-instruct",
  "training_type": "qlora",
  "configuration": {
    "epochs": 3,
    "batch_size": 4,
    "learning_rate": 0.0002,
    "max_seq_length": 2048
  }
}
```

**Response (202 Accepted):**

```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "status": "QUEUED",
    "dataset_id": "uuid",
    "base_model": "mistral-7b-instruct",
    "training_type": "qlora",
    "created_at": "2026-06-20T10:00:00Z"
  }
}
```

**Errors:**

- `400` — Invalid configuration
- `403` — Dataset access denied
- `409` — User already has an ACTIVE job (QUEUED or RUNNING)
- `422` — Dataset not in READY status

---

#### `GET /api/v1/training-jobs`

**Query Parameters:**

- `status` (optional): Filter by status
- `limit` (default: 20, max: 100)
- `offset` (default: 0)

**Response:**

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "status": "RUNNING",
        "base_model": "mistral-7b-instruct",
        "training_type": "qlora",
        "started_at": "2026-06-20T10:05:00Z",
        "progress_percent": 45
      }
    ],
    "total": 1,
    "limit": 20,
    "offset": 0
  }
}
```

---

#### `GET /api/v1/training-jobs/{id}`

**Response:**

```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "status": "COMPLETED",
    "dataset_id": "uuid",
    "dataset_version_id": "uuid",
    "base_model": "mistral-7b-instruct",
    "training_type": "qlora",
    "configuration": { ... },
    "artifact_path": "artifacts/uuid/",
    "started_at": "2026-06-20T10:00:00Z",
    "completed_at": "2026-06-20T12:30:00Z",
    "duration_seconds": 9000,
    "error_message": null
  }
}
```

---

#### `POST /api/v1/training-jobs/{id}/cancel`

**Response (200 OK):**

```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "status": "CANCELLED",
    "cancelled_at": "2026-06-20T10:15:00Z"
  }
}
```

**Errors:**

- `400` — Job already terminal (COMPLETED/FAILED/CANCELLED)
- `403` — Not job owner
- `404` — Job not found

---

## 9. Security Design

### 9.1 Ownership Enforcement

| Layer              | Enforcement                                                                           |
| ------------------ | ------------------------------------------------------------------------------------- |
| **API Layer**      | `CurrentUser` dependency injects authenticated user. All queries filter by `user_id`. |
| **Service Layer**  | `TrainingService` verifies `job.user_id == current_user.id` before any mutation.      |
| **Database Layer** | Foreign key `training_jobs.user_id → users.id` with `ON DELETE CASCADE`.              |

### 9.2 Job Visibility Rules

- **Users** see only their own jobs.
- **Admins** (future) see all jobs.
- **Public** access is denied; no unauthenticated endpoints.

### 9.3 Cancellation Permissions

- Only the **job owner** can cancel.
- Admins can cancel any job (future RBAC).
- Attempting to cancel another user's job returns `403 Forbidden`.

### 9.4 Configuration Validation

- Pydantic validates all config fields before persistence.
- `base_model` is checked against an allowlist of supported models.
- `training_type` must be one of: `sft`, `lora`, `qlora`, `peft`.
- Resource limits enforced: max epochs ≤ 10, max batch size ≤ 16.
- **Concurrency guard:** each user may have at most **1 ACTIVE job** (status `QUEUED` or `RUNNING`). Submitting a new job while one is ACTIVE returns `409 Conflict`.

---

## 10. Risk Analysis

### 10.1 Concurrency Risks

| Risk                            | Impact                                       | Mitigation                                                                                            |
| ------------------------------- | -------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **Race condition on job start** | Two jobs start simultaneously for one user.  | Database `CHECK` constraint or application-level lock on `(user_id, status IN ('QUEUED','RUNNING'))`. |
| **Status update collision**     | Worker and API update status simultaneously. | Optimistic locking with `updated_at` or `version` column.                                             |
| **Duplicate queue entries**     | Same job enqueued twice.                     | Use `job_id` as RQ job ID (idempotent).                                                               |

### 10.2 Job Duplication Risks

| Risk                    | Impact                             | Mitigation                                        |
| ----------------------- | ---------------------------------- | ------------------------------------------------- |
| **Client retries POST** | Same config creates multiple jobs. | Idempotency key header (`Idempotency-Key: uuid`). |
| **Worker restart**      | Job re-executed after completion.  | RQ `result_ttl` and job ID deduplication.         |

### 10.3 Artifact Consistency Risks

| Risk                           | Impact                                  | Mitigation                                         |
| ------------------------------ | --------------------------------------- | -------------------------------------------------- |
| **Partial artifact write**     | Crash during save leaves corrupt files. | Write to temp directory; atomic rename on success. |
| **Orphaned artifacts**         | Job deleted but artifacts remain.       | Background cleanup task (future).                  |
| **Concurrent artifact access** | Two workers write to same path.         | UUID-based artifact paths (`artifacts/{job_id}/`). |

### 10.4 Worker Crash Risks

| Risk                           | Impact                          | Mitigation                                       |
| ------------------------------ | ------------------------------- | ------------------------------------------------ |
| **Worker dies mid-training**   | Job stuck in `RUNNING` forever. | Heartbeat timeout (5 min) marks job as `FAILED`. |
| **GPU OOM**                    | Process killed by OS.           | Catch `RuntimeError`; reduce batch size; retry.  |
| **Model download interrupted** | Corrupt model cache.            | Verify checksums; re-download on failure.        |

---

## 11. Recommended Implementation Order

### Phase 3.1: Foundation (Week 1)

1. **Database**
   - Create `training_jobs` table migration.
   - Add SQLAlchemy model with relationships.
   - Add indexes.

2. **Configuration**
   - Implement `TrainingConfig` Pydantic schema (4 fields only: epochs, batch_size, learning_rate, max_seq_length).
   - Add validation rules.

3. **Repository Layer**
   - `TrainingJobRepository` with CRUD + status transitions.
   - Ownership filtering.

### Phase 3.2: Service Layer (Week 1-2)

4. **TrainingService**
   - `create_job()` — validation, enqueue, status management.
   - `get_job()` / `list_jobs()` — ownership-filtered queries.
   - `cancel_job()` — queue removal + signal.
   - Concurrency guard (1 ACTIVE job per user: QUEUED or RUNNING).

5. **Queue Integration**
   - Redis connection setup.
   - RQ queue initialization.
   - Enqueue logic in `TrainingService`.

### Phase 3.3: Worker (Week 2)

6. **MockTrainingRunner**
   - Simulates training without real GPU/model loading.
   - Sleeps for a configurable duration to mimic training time.
   - Produces a mock artifact (dummy model file + log).
   - Updates job status through the full lifecycle.

7. **RQ Worker**
   - Worker startup/shutdown.
   - Heartbeat mechanism.
   - Cancellation signal handling.

### Phase 3.4: API Layer (Week 2-3)

8. **FastAPI Routes**
   - `POST /training-jobs`
   - `GET /training-jobs`
   - `GET /training-jobs/{id}`
   - `POST /training-jobs/{id}/cancel`

9. **Exception Handlers**
   - `TrainingJobNotFoundError`
   - `TrainingJobAccessDeniedError`
   - `TrainingConfigValidationError`

### Phase 3.5: Testing (Week 3)

10. **Unit Tests**
    - Repository tests (CRUD, filtering).
    - Service tests (creation, cancellation, concurrency).
    - Config validation tests.

11. **Integration Tests**
    - API endpoint tests.
    - Queue enqueue/dequeue tests (mocked worker).
    - End-to-end flow with MockTrainingRunner.

### Phase 3.6: Documentation (Week 3)

12. **Update `00_project_context.md`**
    - Mark Phase 3 as complete.
    - Document new tables, services, APIs.

---

## 12. Summary

| Component            | Status     | Key Decisions                                                                                      |
| -------------------- | ---------- | -------------------------------------------------------------------------------------------------- |
| **Database**         | Planned    | JSONB config, UUID PKs, status enum, ownership FKs                                                 |
| **Status Lifecycle** | Planned    | 4 states (QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED), 5 valid transitions, terminal states guarded |
| **TrainingConfig**   | Planned    | Minimal Pydantic schema: epochs, batch_size, learning_rate, max_seq_length                         |
| **Queue**            | Planned    | Redis + RQ, idempotent job IDs, retry with backoff                                                 |
| **Worker**           | Planned    | MockTrainingRunner (simulated training), heartbeat, graceful shutdown                              |
| **APIs**             | Planned    | 4 endpoints, 202 Accepted for async creation                                                       |
| **Security**         | Planned    | Ownership at all layers, 1 ACTIVE job per user (QUEUED or RUNNING)                                 |
| **Risks**            | Identified | Concurrency, duplication, artifacts, crashes                                                       |

---

**Next Step:** Begin Phase 3.1 implementation (database migration + model).

**Estimated Effort:** 3 weeks (1 developer).

**Dependencies:** Phase 2 (Dataset Service) must be complete.
