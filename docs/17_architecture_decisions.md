# Architecture Decisions

## Purpose

This document contains all implementation decisions that were not explicitly defined in the original architecture documents.

These decisions are authoritative.

If any generated code conflicts with this document, this document takes precedence.

---

# Authentication

JWT Expiration:

24 Hours

Refresh Tokens:

Not implemented in MVP

Password Policy:

- Minimum Length: 8
- Maximum Length: 128

Password Storage:

bcrypt

---

# API Standards

Response Format:

Success:

{
"success": true,
"data": {}
}

Failure:

{
"success": false,
"error": {
"code": "",
"message": ""
}
}

---

# Rate Limiting

Default:

100 Requests Per Minute

Applied To:

- Authentication APIs
- Dataset APIs
- Inference APIs

---

# Dataset Limits

Maximum Upload Size:

1 GB

Maximum Records:

10,000,000

Supported Formats:

- CSV
- JSON
- JSONL

---

# Dataset Deletion

Strategy:

Soft Delete

Reason:

Maintain reproducibility of training runs.

---

# Versioning Strategy

Dataset Versions:

v1
v2
v3

Model Versions:

v1
v2
v3

---

# Training Limits

Training Environment:

Google Colab T4

GPU Memory:

16 GB

Maximum Epochs:

10

Maximum Training Duration:

24 Hours

Concurrent Jobs Per User:

1

Checkpoint Retention:

Keep Last 3 Checkpoints

---

# QLoRA Configuration

Default:

load_in_4bit=True

bnb_4bit_quant_type="nf4"

bnb_4bit_use_double_quant=True

gradient_checkpointing=True

---

# Evaluation

Required Metrics:

- ROUGE
- BERTScore

Optional Metrics:

- Semantic Similarity

Excluded From MVP:

- RAGAS
- LLM Judge

---

# Inference Limits

Maximum Input Tokens:

4096

Maximum Output Tokens:

1024

Default Temperature:

0.7

---

# Deployment

Deployment Type:

Single Instance

Inference Framework:

Transformers + PEFT

Adapter Loading:

- Base model is loaded with the same 4-bit NF4 quantization used in Phase 4.3 training.
- LoRA adapter is applied via `peft.PeftModel.from_pretrained`.
- Tokenizer is loaded from `artifact_path/tokenizer/` if present, otherwise from `artifact_path/`.

Model Caching:

- A module-level `InferenceService` singleton caches the loaded model + tokenizer.
- Cache key is `base_model:artifact_path`.
- Loading the same adapter twice is a no-op.
- `unload()` drops the cache for testing and resource cleanup.

Deployment Lifecycle:

- Four states: PENDING, DEPLOYING, ACTIVE, FAILED.
- Activation moves PENDING → DEPLOYING → ACTIVE.
- Adapter load failures mark the deployment FAILED.
- Only ACTIVE deployments accept `/generate`.

No Delete:

- Deployments are not deleted; failed deployments can be re-activated.

Future Backend Swap:

- The `/deployments/{id}/generate` API contract is independent of the inference implementation.
- Replacing `InferenceService` with vLLM, TGI, or Triton does not change the endpoint shape.

Excluded From MVP:

- Kubernetes
- vLLM
- Ray Serve
- Autoscaling
- Streaming responses

---

# Storage

Metadata:

PostgreSQL

Artifacts:

MinIO

Never Store Artifacts In PostgreSQL

---

# CORS

Allowed Origins:

http://localhost:3000

---

# Worker Configuration

Initial Workers:

1

Queue:

Redis

Framework:

RQ

---

# Testing

Backend Coverage:

Minimum 70%

Frontend:

Component Tests

---

# Logging

Format:

Structured JSON Logs

Required Fields:

- timestamp
- service
- level
- message

---

# Monitoring

Required:

- Prometheus
- Grafana

All Services Must Expose:

GET /health

---

# MVP Scope Lock

Do Not Implement:

- RLHF
- DPO
- PPO
- Kubernetes
- Ray
- vLLM
- Multi-GPU Training
- RAGAS
- LLM Judge

Unless explicitly requested later.

---

# User Identity Uniqueness

Email And Username Are Case-Insensitive Unique.

Invariant:

Two users cannot share the same email or username regardless of letter casing.

Enforcement Layers:

- Application Layer:
  - Repository normalizes email and username to lowercase before lookup.
  - AuthService rejects duplicate registrations with HTTP 409.
- Database Layer:
  - PostgreSQL enforces uniqueness via expression indexes on LOWER(email) and LOWER(username).
  - Migration 0002 replaces the original case-sensitive unique indexes with these expression indexes.

Rationale:

Application-only enforcement is bypassable. Direct database writes, race conditions, or future code paths that bypass the repository could create duplicate identities. The database is the final source of truth.

SQLite Limitation:

SQLite does not support expression indexes. The test suite uses SQLite and relies on application-layer normalization only. Production uses PostgreSQL where the database invariant holds.

---

# Production Secret Validation

Settings Refuse To Boot With A Development JWT Secret In Production-Like Environments.

Production-Like Environments:

- production
- staging

Matching Is Case-Insensitive And Trims Whitespace.

Validator Behavior:

- If APP_ENV is production or staging AND JWT_SECRET_KEY starts with the development prefix, Settings raises ValidationError on instantiation.
- The error message instructs operators to generate a strong random secret.

Rationale:

A development JWT secret in production would allow attackers to forge valid tokens. Silent acceptance of the default is a critical security failure. Failing fast at startup is the only safe behavior.

Development Environments:

- development
- test
- Any other value

The development default secret is accepted without validation.

---
