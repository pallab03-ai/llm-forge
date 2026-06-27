# LLM Forge

Production-grade LLMOps platform for fine-tuning, evaluating, deploying, and monitoring open-source LLMs.

> **Status:** Phase 7 — Deployment Service. Deploy trained ModelVersions as synchronous inference endpoints: PENDING → DEPLOYING → ACTIVE lifecycle, adapter caching, and `/deployments/{id}/generate`. Previous phases (Dataset, Training, Evaluation, Model Registry) complete and validated.

---

## Architecture

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Frontend   │─────▶│   Backend    │─────▶│  PostgreSQL  │
│  Next.js 15  │      │   FastAPI    │      │     16       │
│   :3000      │      │   :8000      │      │   :5432      │
└──────────────┘      └──────┬───────┘      └──────────────┘
                             │
                             ├──────▶ Redis    :6379  (cache / broker)
                             ├──────▶ MinIO    :9000  (datasets, artifacts)
                             └──────▶ MLflow   :5000  (experiments, registry)
```

### Tech Stack

| Layer       | Technology                                 |
| ----------- | ------------------------------------------ |
| Frontend    | Next.js 15, TypeScript (strict), Tailwind  |
| Backend     | FastAPI, Pydantic v2, SQLAlchemy 2 (async) |
| Database    | PostgreSQL 16 + Alembic migrations         |
| Cache/Queue | Redis 7                                    |
| Storage     | MinIO (S3-compatible)                      |
| Tracking    | MLflow                                     |
| Training    | Transformers, PEFT, TRL, Accelerate, BnB   |
| Deployment  | FastAPI + Transformers + PEFT (no vLLM)    |

---

## Repository Layout

```
.
├── backend/                 # FastAPI application
│   ├── app/
│   │   ├── api/v1/          # Routers (health, future: datasets, training, …)
│   │   ├── core/            # config, logging
│   │   ├── db/              # SQLAlchemy base + session
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── services/        # Business logic (Phase 1+)
│   │   ├── workers/         # Background jobs (Phase 3+)
│   │   └── main.py          # FastAPI entry point
│   ├── alembic/             # Database migrations
│   ├── tests/               # Pytest suite
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                # Next.js 15 application
│   ├── app/                 # App router pages
│   ├── lib/                 # API client, utilities
│   ├── package.json
│   └── Dockerfile
├── training/                # Training scripts (Phase 3)
├── inference/               # Inference server (Phase 6)
├── monitoring/              # Prometheus + Grafana (Phase 7)
├── scripts/                 # Operational scripts
├── docs/                    # Architecture & requirements docs
├── docker-compose.yml       # Full local stack
└── .env.example
```

---

## Quick Start

### Prerequisites

- Docker 24+ and Docker Compose v2
- (Optional) Python 3.11+ and Node.js 20+ for local development without Docker

### Run the full stack

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Build and start all services
docker compose up --build

# 3. Verify
curl http://localhost:8000/api/v1/health
# → {"success":true,"data":{"status":"healthy","version":"0.1.0","environment":"development"}}

# 4. Open the UI
open http://localhost:3000
```

### Service URLs

| Service     | URL                        |
| ----------- | -------------------------- |
| Frontend    | http://localhost:3000      |
| Backend API | http://localhost:8000      |
| API docs    | http://localhost:8000/docs |
| MLflow UI   | http://localhost:5000      |
| MinIO UI    | http://localhost:9001      |

---

## Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # then edit values
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

### Tests

```bash
cd backend
pytest -v
```

---

## Engineering Guardrails (Phase 0+)

These rules are enforced from day one:

1. **Response envelope** — every API response uses `{success, data}` or `{success, error}`.
2. **Typed contracts** — Pydantic models for all request/response payloads.
3. **Business logic outside routes** — services layer owns the logic; routers are thin.
4. **Explicit configuration** — Pydantic Settings, no `os.getenv` scattered through code.
5. **Structured logging** — JSON logs via `structlog`.
6. **No binary in DB** — checkpoints, adapters, datasets live in MinIO.
7. **UUID primary keys** — for all domain entities (Phase 1+).
8. **Migrations only** — schema changes go through Alembic, never `Base.metadata.create_all`.
9. **Repository pattern** — services never touch `AsyncSession` directly; they go through repositories.
10. **Auth via dependency** — protected endpoints depend on `CurrentUser`; no manual token parsing in routes.

---

## Authentication (Phase 1)

JWT-based authentication with bcrypt-hashed passwords.

| Endpoint                | Method | Auth   | Description                    |
| ----------------------- | ------ | ------ | ------------------------------ |
| `/api/v1/auth/register` | POST   | Public | Create a new user, returns JWT |
| `/api/v1/auth/login`    | POST   | Public | Exchange credentials for a JWT |
| `/api/v1/auth/me`       | GET    | Bearer | Return the authenticated user  |

### Example: register

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","username":"alice","password":"S3cret!Pass"}'
```

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {
      "id": "5f7e...-...-...-...-...",
      "email": "alice@example.com",
      "username": "alice",
      "role": "user",
      "created_at": "2025-01-01T00:00:00Z",
      "updated_at": "2025-01-01T00:00:00Z"
    }
  }
}
```

### Example: login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"S3cret!Pass"}'
```

### Example: authenticated request

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"
```

### Auth configuration

| Env var                                       | Default                       | Notes                        |
| --------------------------------------------- | ----------------------------- | ---------------------------- |
| `JWT_SECRET_KEY`                              | dev placeholder               | **Must** be replaced in prod |
| `JWT_ALGORITHM`                               | `HS256`                       |                              |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`             | `1440` (24h)                  |                              |
| `JWT_ISSUER` / `JWT_AUDIENCE`                 | `llm-forge` / `llm-forge-api` | Validated on every decode    |
| `PASSWORD_MIN_LENGTH` / `PASSWORD_MAX_LENGTH` | `8` / `128`                   | Enforced by Pydantic         |
| `BCRYPT_ROUNDS`                               | `12`                          |                              |

---

## Model Registry (Phase 6)

User-owned model containers with versioned LoRA adapters.

| Endpoint                                     | Method | Auth   | Description                                       |
| -------------------------------------------- | ------ | ------ | ------------------------------------------------- |
| `/api/v1/models`                             | POST   | Bearer | Create a model container                          |
| `/api/v1/models`                             | GET    | Bearer | List models for the current user                  |
| `/api/v1/models/{id}`                        | GET    | Bearer | Get a model by ID                                 |
| `/api/v1/models/{id}/versions`               | POST   | Bearer | Register a trained adapter as a new version       |
| `/api/v1/models/versions/{version_id}/promote` | POST   | Bearer | Promote a version to PRODUCTION                   |
| `/api/v1/models/versions/{version_id}/archive` | POST   | Bearer | Archive a version                                 |

### Version lifecycle

```
DRAFT → STAGING → PRODUCTION → ARCHIVED
```

- New registered versions start in `STAGING`.
- Promoting a version to `PRODUCTION` atomically demotes the previous `PRODUCTION` version to `STAGING`.
- Only one version per model may be `PRODUCTION` at any time.
- `ARCHIVED` versions cannot be promoted.

### Example: create a model

```bash
curl -X POST http://localhost:8000/api/v1/models \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Customer Support Assistant","description":"Fine-tuned support bot"}'
```

### Example: register a trained adapter as a version

```bash
curl -X POST http://localhost:8000/api/v1/models/<model_id>/versions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"training_job_id":"...","evaluation_id":"..."}'
```

### Example: promote a version to production

```bash
curl -X POST http://localhost:8000/api/v1/models/versions/<version_id>/promote \
  -H "Authorization: Bearer <token>"
```

---

## Deployment Service (Phase 7)

Expose a trained ModelVersion as a synchronous inference endpoint.

| Endpoint                                 | Method | Auth   | Description                              |
| ---------------------------------------- | ------ | ------ | ---------------------------------------- |
| `/api/v1/deployments`                    | POST   | Bearer | Create a deployment                      |
| `/api/v1/deployments`                    | GET    | Bearer | List deployments for the current user    |
| `/api/v1/deployments/{id}`               | GET    | Bearer | Get a deployment by ID                   |
| `/api/v1/deployments/{id}/activate`      | POST   | Bearer | Load adapter and mark deployment ACTIVE  |
| `/api/v1/deployments/{id}/generate`      | POST   | Bearer | Run inference against an active deployment |

### Deployment lifecycle

```
PENDING → DEPLOYING → ACTIVE
              ↘ FAILED
```

- Deployments start in `PENDING`.
- Activation validates the adapter exists, loads the base model + LoRA adapter, and transitions to `ACTIVE`.
- Load failures transition the deployment to `FAILED`.
- Only `ACTIVE` deployments accept `/generate` requests.

### Example: create and activate a deployment

```bash
# Create
curl -X POST http://localhost:8000/api/v1/deployments \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "model_version_id": "<version_id>",
    "deployment_name": "support-bot-prod",
    "endpoint_name": "support-bot-prod-v1"
  }'

# Activate
curl -X POST http://localhost:8000/api/v1/deployments/<deployment_id>/activate \
  -H "Authorization: Bearer <token>"
```

### Example: inference

```bash
curl -X POST http://localhost:8000/api/v1/deployments/<deployment_id>/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Explain LoRA."}'
```

---

## Implementation Roadmap

See [`docs/13_implementation_roadmap.md`](docs/13_implementation_roadmap.md) for the full phased plan.

| Phase | Scope                                                                       | Status      |
| ----- | --------------------------------------------------------------------------- | ----------- |
| 0     | Foundation: monorepo, health, Docker Compose                                | ✅ Complete |
| 1     | Database foundation + JWT authentication                                    | ✅ Complete |
| 1.5   | Security hardening: case-insensitive uniqueness + production JWT validation | ✅ Complete |
| 2     | Dataset service + MinIO                                                     | ✅ Complete |
| 3     | Training service (SFT/LoRA/QLoRA) + RQ worker                               | ✅ Complete |
| 4     | QLoRA training validation                                                   | ✅ Complete |
| 5     | Evaluation service (ROUGE, BERTScore, Semantic Similarity)                  | ✅ Complete |
| 5.1   | Real evaluation validation on Colab T4                                      | ✅ Complete |
| 6     | Model registry                                                              | ✅ Complete |
| 7     | Deployment service (FastAPI inference)                                      | ✅ Complete |
| 8     | Observability (Prometheus + Grafana)                                        | ⏳          |

---

## Security Hardening (Phase 1.5)

Two security gaps identified during code review were closed before Phase 2.

### 1. Case-insensitive uniqueness at the database layer

The application normalizes email and username to lowercase before lookup, but the original migration created case-sensitive unique indexes. A direct database write or a future code path that bypassed the repository could create duplicate identities.

Fix:

- Migration `0002_unique_lower_email_username` replaces the case-sensitive unique indexes with PostgreSQL expression indexes on `LOWER(email)` and `LOWER(username)`.
- The database is now the final source of truth for the uniqueness invariant.

Note: SQLite (used in tests) does not support expression indexes. The test suite relies on application-layer normalization. Production uses PostgreSQL where the database invariant holds.

### 2. Production JWT secret validation

The development JWT secret was accepted silently in any environment. A misconfigured production deployment could boot with a known secret, allowing attackers to forge valid tokens.

Fix:

- `Settings` now has a `model_validator(mode="after")` that refuses to instantiate when `APP_ENV` is `production` or `staging` AND `JWT_SECRET_KEY` starts with the development prefix.
- Matching is case-insensitive and trims whitespace.
- The error message instructs operators to generate a strong random secret (e.g. `openssl rand -hex 32`).

### Tests

Eight new security tests live in `backend/tests/test_security.py`:

- Three tests verify that duplicate registrations with different casing are rejected with HTTP 409.
- Five tests verify that `Settings` rejects the development secret in production-like environments and accepts it in development.

Total test count: **363 tests** (4 health + 13 auth + 8 security + 37 model registry + 25 deployment + …).

---

## License

Internal project — license TBD.
