# Phase 3 Architecture Audit

**Date**: 2026-06-21  
**Scope**: Training Job Infrastructure — race conditions, soft delete, config limits, test status  
**Action**: Recommendations only — no code changes.

---

## 1. Active Job Race Condition Analysis

### Finding: YES — Two concurrent requests CAN create multiple ACTIVE jobs

The `TrainingService.create_job` method performs a classic **TOCTOU (Time-of-Check-Time-of-Use)** race condition:

```python
# Step 2: CHECK — count active jobs
active_count = await self._jobs.count_active_jobs(user_id)
if active_count >= 1:
    raise ActiveJobLimitExceededError(user_id)

# Step 3: USE — create the job row
job = TrainingJob(...)
job = await self._jobs.create(job)

# Step 5: COMMIT
await self._jobs.commit()
```

**Race scenario**:

1. Request A calls `count_active_jobs(user_id)` → returns `0` → proceeds
2. Request B calls `count_active_jobs(user_id)` → returns `0` → proceeds (A hasn't committed yet)
3. Both requests create a `TrainingJob` row with `status=QUEUED`
4. Both commit successfully → **user now has 2 active jobs**

The gap between the `count_active_jobs` SELECT and the final COMMIT is unguarded. SQLAlchemy's default isolation level in PostgreSQL is READ COMMITTED, which does NOT prevent this race — both transactions see a snapshot where no active job exists.

### Recommendation: Database-Level Partial Unique Index

Add a **partial unique index** that enforces the constraint at the PostgreSQL level:

```sql
CREATE UNIQUE INDEX uq_one_active_job_per_user
    ON training_jobs (user_id)
    WHERE status IN ('queued', 'running');
```

**Why this works**:

- PostgreSQL evaluates the unique constraint at INSERT/UPDATE commit time, not at SELECT time
- If two concurrent transactions try to insert a row with the same `user_id` and `status` in `('queued', 'running')`, the second will get a unique constraint violation
- The partial WHERE clause means completed/failed/cancelled jobs are excluded — users can have unlimited historical jobs

**Implementation notes** (for Phase 4):

- Add the index in a new Alembic migration
- Catch `IntegrityError` in `TrainingService.create_job` and re-raise as `ActiveJobLimitExceededError`
- This is the only reliable fix — application-level locks (e.g., `SELECT ... FOR UPDATE`) are fragile and don't work across separate HTTP requests

**Severity**: 🔴 **HIGH** — The 1-active-job-per-user invariant can be violated under concurrent load.

---

## 2. Soft Delete Necessity Analysis

### Current State

The `TrainingJob` model has a `deleted_at: Mapped[datetime | None]` column (nullable, default=None). The repository filters on `deleted_at.is_(None)` in every query (`get_by_id`, `list_for_user`, `count_for_user`, `count_active_jobs`).

### Why Soft Delete Exists

Soft delete was inherited from the `Dataset` model pattern, where it makes clear sense:

- Datasets are user-facing content that users may want to "undo" deleting
- Datasets may be referenced by training jobs (FK dependency)
- Accidental deletion of a dataset could orphan training jobs

### Why Soft Delete is UNNECESSARY for Training Jobs

| Factor                    | Assessment                                                                                                                      |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **FK cascade protection** | Not needed — training_jobs are leaf nodes. No other table FKs into training_jobs.                                               |
| **Undo/restore**          | Low value — a deleted job's artifact is already on disk; re-creating the job is trivial.                                        |
| **Audit trail**           | Completed/failed/cancelled jobs already persist indefinitely. A user "deleting" a job is really just hiding it from their list. |
| **Admin debugging**       | The `error_message`, `started_at`, `completed_at` fields on non-deleted jobs provide sufficient debug info.                     |
| **Complexity cost**       | Every query must include `deleted_at.is_(None)` — easy to forget, causes subtle bugs if omitted.                                |

### Recommendation: REMOVE soft delete from training_jobs

**Rationale**:

1. Training jobs are **computational resources**, not user content. They have a clear lifecycle (QUEUED → RUNNING → terminal state) and once terminal, they're historical records.
2. If a user wants to "hide" a job from their list, add a `hidden: bool` column instead — it's semantically clearer and doesn't carry the FK-implication baggage of soft delete.
3. Removing `deleted_at` eliminates the filter-everywhere tax and reduces the chance of bugs from forgotten filters.
4. The partial unique index (Recommendation 1) becomes simpler without the `deleted_at.is_(None)` condition.

**Migration steps** (for Phase 4):

1. New Alembic migration: `DROP COLUMN deleted_at` from `training_jobs`
2. Remove `deleted_at` from the ORM model
3. Remove `deleted_at.is_(None)` from all repository queries
4. Remove `is_deleted` property from the model
5. If "hide from list" is a product requirement, add `hidden: Mapped[bool]` with `default=False`

**Severity**: 🟡 **MEDIUM** — Not a bug, but unnecessary complexity that increases maintenance burden and bug surface area.

---

## 3. TrainingConfig Limits Review

### Current Limits

| Field            | Type    | Min  | Max   | Assessment    |
| ---------------- | ------- | ---- | ----- | ------------- |
| `epochs`         | `int`   | 1    | 100   | ⚠️ See below  |
| `batch_size`     | `int`   | 1    | 256   | ⚠️ See below  |
| `learning_rate`  | `float` | 1e-7 | 1.0   | ✅ Reasonable |
| `max_seq_length` | `int`   | 64   | 32768 | ⚠️ See below  |

### Issues

1. **`epochs` max=100 is too high for production**. 100 epochs on a 10K-row dataset with a 7B model would take days and likely overfit. Industry standard for SFT is 1–5 epochs. Recommend lowering max to **10** for MVP, with a config-driven override for power users.

2. **`batch_size` max=256 is unrealistic for GPU memory**. A batch size of 256 with `max_seq_length=32768` on a 7B model would require ~500GB+ VRAM. Even with gradient accumulation, the effective batch size rarely exceeds 128. Recommend lowering max to **128**, or adding a **gradient_accumulation_steps** field to decouple logical vs physical batch size.

3. **`max_seq_length` max=32768 is dangerous**. 32K context on a 7B model with batch_size=1 requires ~64GB VRAM (fp16). With batch_size=256, this is physically impossible on any single GPU. Recommend:
   - Lower max to **8192** for MVP (covers most SFT use cases)
   - Add a runtime VRAM check in the training runner before starting

4. **Missing: `warmup_steps` or `warmup_ratio`**. Standard practice for LR scheduling. Not critical for MVP but should be added before production.

5. **Missing: `weight_decay`**. Common regularization parameter (typically 0.01–0.1). Low priority for MVP.

6. **Cross-field validation gap**: No constraint prevents `batch_size=256` + `max_seq_length=32768` combination, which is physically impossible. Recommend adding a **composite validation** or at minimum documenting the OOM risk.

### Recommendation

| Field            | Current Max | Recommended Max     | Rationale                                              |
| ---------------- | ----------- | ------------------- | ------------------------------------------------------ |
| `epochs`         | 100         | **10**              | Overfit risk; industry SFT standard is 1–5             |
| `batch_size`     | 256         | **128**             | GPU VRAM limits; add gradient_accumulation_steps later |
| `learning_rate`  | 1.0         | **1.0** (unchanged) | Already reasonable                                     |
| `max_seq_length` | 32768       | **8192**            | VRAM feasibility for 7B models                         |

**Severity**: 🟡 **MEDIUM** — Won't cause data corruption, but unrealistic limits will lead to OOM crashes in the training runner when real training is implemented.

---

## 4. Actual Pytest Status

### Project-Wide Test Results

```
Platform: win32 -- Python 3.14.2, pytest-9.1.1
Collected: 111 items
```

| Category            | Count   | Status |
| ------------------- | ------- | ------ |
| **Total collected** | **111** |        |
| **PASSED**          | **90**  | ✅     |
| **FAILED**          | **21**  | ❌     |
| **SKIPPED**         | **0**   | —      |
| **ERRORS**          | **0**   | —      |

### Failure Breakdown

| Test File          | Failed | Root Cause                                                                                               |
| ------------------ | ------ | -------------------------------------------------------------------------------------------------------- |
| `test_auth.py`     | 13/13  | All fail — uses sync `client.post()` instead of `await client.post()` on `AsyncClient`                   |
| `test_health.py`   | 4/4    | Same — sync calls on async client                                                                        |
| `test_security.py` | 3/7    | 3 tests use sync `client.post()` on `AsyncClient`; 4 tests pass (they use `TestClient` or startup hooks) |

### Passing Breakdown

| Test File               | Passed | Total                            |
| ----------------------- | ------ | -------------------------------- |
| `test_datasets.py`      | 24     | 24 ✅                            |
| `test_training_jobs.py` | 62     | 62 ✅                            |
| `test_security.py`      | 4      | 7 (3 fail for same async reason) |

### Root Cause of All 21 Failures

**Single issue**: `test_auth.py`, `test_health.py`, and 3 tests in `test_security.py` use the `client` fixture (which provides `httpx.AsyncClient`) but call it synchronously (`client.post(...)`) instead of asynchronously (`await client.post(...)`). This returns an unawaited coroutine object, causing `AttributeError: 'coroutine' object has no attribute 'status_code'`.

**Fix**: Add `async def` + `await` to all affected test functions, or migrate them to use `pytest.mark.asyncio` properly.

**Severity**: 🟡 **MEDIUM** — Not a Phase 3 issue. Pre-existing tech debt from the auth/health test suites. All Phase 3 tests (62/62) pass.

---

## Summary of Recommendations

| #   | Item                                     | Severity  | Action                                                                                                                                                          |
| --- | ---------------------------------------- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Active job race condition**            | 🔴 HIGH   | Add PostgreSQL partial unique index `uq_one_active_job_per_user` on `(user_id) WHERE status IN ('queued', 'running')`. Catch `IntegrityError` in service layer. |
| 2   | **Soft delete on training_jobs**         | 🟡 MEDIUM | Remove `deleted_at` column. Training jobs are computational resources, not user content. If "hide" is needed, add a `hidden: bool` column instead.              |
| 3   | **TrainingConfig limits too permissive** | 🟡 MEDIUM | Reduce `epochs` max 100→10, `batch_size` max 256→128, `max_seq_length` max 32768→8192. Add cross-field OOM risk documentation.                                  |
| 4   | **Pre-existing test failures**           | 🟡 MEDIUM | Fix 21 failing tests by adding `await` to `AsyncClient` calls in `test_auth.py`, `test_health.py`, `test_security.py`.                                          |

### Priority Order for Phase 4

1. **🔴 Race condition fix** — This is a data integrity bug that can violate the core business invariant under concurrent load.
2. **🟡 Soft delete removal** — Simplifies all repository queries and the partial unique index.
3. **🟡 TrainingConfig limits** — Prevents OOM crashes when real training is implemented.
4. **🟡 Test suite fix** — Improves CI reliability and coverage visibility.
