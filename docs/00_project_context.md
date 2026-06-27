# LLM Forge - Project Context

## Purpose

This document is the single source of truth for the current implementation state.

AI coding agents MUST read this file before starting work.

Agents should use this file to understand:

* current phase
* completed features
* implemented architecture
* database state
* API state
* pending work

Agents MUST NOT re-analyze the entire repository if the required information exists here.

---

# Project Summary

LLM Forge is an LLMOps platform for:

* Dataset Management
* Fine-Tuning (LoRA / QLoRA)
* Evaluation
* Model Registry
* Deployment
* Monitoring

Primary Goal:

Build a production-style fine-tuning platform suitable for portfolio and interview discussions.

---

# Current Status

Current Phase:

Phase 7 - Deployment Service

Overall Progress:

```text
Phase 0  Foundation               ✅
Phase 1  Authentication           ✅
Phase 1.5 Security Hardening      ✅
Phase 2  Dataset Service          ✅
Phase 3  Training Jobs            ✅
Phase 4  MLflow                   ✅
Phase 4.1 QLoRA Training          ✅
Phase 4.2 QLoRA Config Validation ✅
Phase 4.3 QLoRA Real Validation   ✅
Phase 5  Evaluation               ✅
Phase 5.1 Real Evaluation         ✅
Phase 6  Model Registry           ✅
Phase 7  Deployment               ✅
Phase 8  Monitoring               ⏳
```

---

# Finalized Decisions

These decisions are COMPLETE.

Do not redesign them.

## Authentication

Implemented:

* JWT Authentication
* bcrypt Password Hashing
* User Roles
* Current User Dependency

JWT Expiration:

24 Hours

---

## Security

Implemented:

* Production JWT Validation
* Case Insensitive User Uniqueness

Production startup fails if:

JWT_SECRET_KEY uses development default.

---

## Architecture

Implemented:

Repository Pattern

```text
Route
 ↓
Service
 ↓
Repository
 ↓
Database
```

Business logic MUST stay inside services.

---

## Implemented Database Tables

## users

Columns:

```text
id
email
username
password_hash
role
created_at
updated_at
```

Status:

Implemented

Migration:

0001_create_users_table

---

## datasets

Status:

Implemented

Migration:

0003_create_datasets_table

---

## dataset_versions

Status:

Implemented

Migration:

0003_create_datasets_table

---

## training_jobs

Status:

Implemented

Migration:

0004_create_training_jobs

---

## evaluations

Status:

Implemented

Migration:

0005_create_evaluations_table

---

## models

Status:

Implemented

Migration:

0006_create_model_registry

---

## model_versions

Status:

Implemented

Migration:

0006_create_model_registry

---

## deployments

Status:

Implemented

Migration:

0007_create_deployments

---

# Implemented APIs

## Authentication

```http
POST /api/v1/auth/register

POST /api/v1/auth/login

GET /api/v1/auth/me
```

Status:

Implemented

Tests:

Passing

---

## Datasets

```http
POST /api/v1/datasets

GET /api/v1/datasets

GET /api/v1/datasets/{id}
```

Status:

Implemented

---

## Training Jobs

```http
POST /api/v1/training-jobs

GET /api/v1/training-jobs

GET /api/v1/training-jobs/{id}

POST /api/v1/training-jobs/{id}/cancel
```

Status:

Implemented

---

## Evaluations

```http
POST /api/v1/evaluations

GET /api/v1/evaluations

GET /api/v1/evaluations/{id}
```

Status:

Implemented

---

## Model Registry

```http
POST /api/v1/models

GET /api/v1/models

GET /api/v1/models/{id}

POST /api/v1/models/{id}/versions

POST /api/v1/models/versions/{version_id}/promote

POST /api/v1/models/versions/{version_id}/archive
```

Status:

Implemented

---

## Deployment Service

```http
POST /api/v1/deployments

GET /api/v1/deployments

GET /api/v1/deployments/{id}

POST /api/v1/deployments/{id}/activate

POST /api/v1/deployments/{id}/generate
```

Status:

Implemented

---

# Implemented Infrastructure

## Backend

FastAPI

## Database

PostgreSQL

## Migrations

Alembic

## Authentication

JWT

## Password Hashing

bcrypt

## Logging

Structured JSON Logs

## Testing

pytest

---

# Current Test Status

Total Tests:

363

Status:

363 Passed

0 Failed

---

# Pending Database Tables

Do not create unless current phase requires them.

```text
datasets
dataset_versions

training_jobs

models
model_versions

deployments

evaluations
```

---

# Current Phase Scope

Phase 7

Deployment Service

Allowed Work:

* Deployment model
* DeploymentRepository
* DeploymentService
* InferenceService
* Deployment API
* Alembic migration
* Tests

Not Allowed:

* Kubernetes
* Docker orchestration
* Ray
* vLLM
* Triton
* Text Generation Inference
* Autoscaling
* Load balancing
* Streaming responses
* Multi-GPU
* Background workers
* Celery
* Redis queues
* Canary deployments
* Traffic splitting
* A/B testing
* Rate limiting

---

# Files Likely Needed For Current Phase

Read only if necessary.

```text
app/models/user.py

app/repositories/base.py

app/repositories/user_repository.py

app/services/auth_service.py

06_dataset_service.md

17_architecture_decisions.md
```

Avoid scanning unrelated files.

---

# Known Technical Debt

## TD-001

updated_at relies on ORM onupdate.

No database trigger exists.

Status:

Accepted.

Priority:

Low.

---

# Next Expected Deliverable

Monitoring / Phase 8

Required:

* Prometheus metrics endpoint
* Grafana dashboards
* Health checks for all services
* Basic logging aggregation

Target:

TBD

---

# Instructions For AI Coding Agents

Before implementation:

1. Read this file.
2. Read only documents related to the current phase.
3. Read only code files required for the current task.
4. Do not redesign completed features.
5. Do not re-analyze the entire repository.
6. Do not scan unrelated directories.
7. Ask for clarification if documentation conflicts exist.

This file is authoritative for current project status.
Phase 2 Dataset Service ✅

Phase 2.1 Security Fixes ✅

Phase 3 Training Jobs ✅

Phase 4 QLoRA Training ✅

Phase 4.1-4.3 QLoRA Validation ✅

Phase 5 Evaluation Service ✅

Phase 5.1 Real Evaluation Validation ✅

Phase 6 Model Registry ✅

Phase 7 Deployment Service ✅

Current Tests:
363 Passing

Implemented Tables:

users
datasets
dataset_versions
training_jobs
evaluations
models
model_versions
deployments

Implemented Services:

AuthService
DatasetService
DatasetValidationService
LocalStorageService
TrainingService
EvaluationService
ModelRegistryService
DeploymentService
InferenceService

Implemented APIs:

Auth APIs
Dataset APIs
Dataset Version APIs
Training Job APIs
Evaluation APIs
Model Registry APIs
Deployment APIs
