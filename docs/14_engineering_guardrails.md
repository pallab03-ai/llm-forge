# Engineering Guardrails

## Purpose

This document defines non-negotiable engineering constraints for LLM Forge.

The AI coding agent MUST follow these rules when generating code, architecture, APIs, database schemas, and infrastructure.

If any generated implementation violates this document, the implementation is considered incorrect.

---

# Core Principles

1. Simplicity over complexity.
2. Production readiness over quick hacks.
3. Reproducibility over convenience.
4. Explicit configuration over hidden behavior.
5. Type safety over dynamic behavior.
6. Observability by default.
7. Fail fast on invalid inputs.

---

# Architecture Constraints

## MUST

* Use modular service architecture.
* Keep frontend and backend separated.
* Use service boundaries defined in system_architecture.md.
* Keep business logic outside API routes.
* Use dependency injection where possible.
* Use typed request and response models.

---

## MUST NOT

* Put business logic inside controllers.
* Put database queries inside frontend code.
* Create circular dependencies.
* Use global mutable state.

---

# Backend Constraints

## Technology

Required:

```text
FastAPI
Pydantic
SQLAlchemy
Alembic
PostgreSQL
Redis
```

---

## API Design

MUST:

* Follow REST conventions.
* Return structured JSON.
* Use proper HTTP status codes.
* Validate all request payloads.

Example:

```json
{
  "success": true,
  "data": {}
}
```

---

## Error Responses

MUST return:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Dataset name is required"
  }
}
```

---

## Authentication

Required:

* JWT Authentication
* Password Hashing
* Protected Routes

Must never:

* Store plaintext passwords.
* Expose secrets.

---

# Database Constraints

## MUST

* Use PostgreSQL.
* Use UUID primary keys.
* Use foreign key constraints.
* Use migrations through Alembic.

---

## MUST NOT

* Store model artifacts in PostgreSQL.
* Store datasets inside PostgreSQL.
* Store binary files in database tables.

---

# Storage Constraints

Required:

```text
MinIO
```

Store:

* datasets
* checkpoints
* adapters
* logs
* evaluation artifacts

Do not store these in PostgreSQL.

---

# Dataset Service Constraints

## Supported Formats

Only:

* CSV
* JSON
* JSONL

---

## Validation Rules

Every upload must validate:

* schema
* duplicate records
* empty fields
* file size

Invalid datasets must be rejected.

---

# Training Service Constraints

## Supported Methods

Only:

* SFT
* LoRA
* QLoRA

Do not implement:

* RLHF
* DPO
* PPO

during MVP.

---

## Supported Models

Only:

* Mistral 7B
* Llama 3 8B
* Qwen 2.5 7B

Do not add additional models unless explicitly requested.

---

## Training Environment

Assume:

```text
Google Colab T4
16GB VRAM
```

Generated code must work within this limitation.

---

## QLoRA Configuration

Default:

```python
load_in_4bit=True

bnb_4bit_quant_type="nf4"

bnb_4bit_use_double_quant=True
```

---

# Evaluation Constraints

MVP metrics:

* ROUGE
* BERTScore

Optional:

* Semantic Similarity

Do not implement:

* LLM-as-Judge
* RAGAS

during MVP.

---

# Model Registry Constraints

Model stages:

```text
DRAFT

STAGING

PRODUCTION

ARCHIVED
```

Every training run creates a model version.

No deployment is allowed without registration.

---

# Deployment Constraints

## MVP Deployment

Required:

```text
FastAPI
Transformers
PEFT
```

Do not implement:

```text
Kubernetes

vLLM

Ray Serve
```

during MVP.

---

# Frontend Constraints

Required:

```text
Next.js
TypeScript
Tailwind
ShadCN
React Query
```

---

## State Management

Use:

```text
React Query

Zustand
```

Do not use Redux.

---

# Observability Constraints

Every service must expose:

```text
health endpoint

structured logs

error logs
```

Required endpoint:

```http
GET /health
```

---

# Testing Constraints

Backend:

* Pytest

Frontend:

* Component tests

Minimum coverage:

```text
70%
```

---

# Code Quality Constraints

Python:

```text
Black
Ruff
MyPy
```

TypeScript:

```text
ESLint

Strict Mode
```

---

# Security Constraints

Never:

* Hardcode secrets
* Hardcode credentials
* Disable authentication
* Expose internal stack traces

Always:

* Validate input
* Sanitize uploads
* Rate limit APIs

---

# Anti-Hallucination Rules

The AI coding agent MUST NOT:

* Invent APIs not defined in documentation.
* Invent database tables not defined in database_design.md.
* Invent services not defined in system_architecture.md.
* Add technologies not approved in architecture documents.
* Generate placeholder production logic.
* Mock successful operations in production code.

If required information is missing:

STOP and request clarification instead of guessing.

---

# Success Criteria

Implementation is considered correct only if:

* Follows architecture documents.
* Passes tests.
* Uses approved technologies.
* Runs locally with Docker Compose.
* Supports Google Colab based QLoRA workflow.
* Produces reproducible results.
