
# Model Registry Service

## Purpose

The Model Registry acts as the source of truth for all trained models.

It manages:

* Model Versions
* Lifecycle Stages
* Artifact Tracking
* Promotion Workflows
* Rollbacks

---

# Responsibilities

* Register Models
* Version Models
* Promote Models
* Archive Models
* Track Artifacts
* Manage Metadata

---

# Model Lifecycle

```text
Draft
  ↓
Staging
  ↓
Production
  ↓
Archived
```

---

# Registry Workflow

```text
Training Completed
       ↓
Register Model
       ↓
Store Metadata
       ↓
Store Artifacts
       ↓
Evaluate
       ↓
Promote
       ↓
Deploy
```

---

# Model Structure

Example:

```text
customer-support-model

    v1

    v2

    v3
```

---

# Versioning Rules

Every successful training run creates:

```text
New Model Version
```

Examples:

```text
v1.0.0

v1.1.0

v2.0.0
```

---

# Metadata

Stored Information:

```json
{
  "model_name":"customer-support",
  "version":"v2",
  "base_model":"mistral-7b",
  "training_method":"qlora",
  "created_by":"user_id"
}
```

---

# Artifact Tracking

Artifacts:

```text
adapter_model.bin

adapter_config.json

tokenizer

training_logs

evaluation_report
```

Storage:

```text
MinIO
```

---

# Promotion Workflow

## Draft → Staging

Requirements:

* Evaluation Passed
* Artifacts Available

---

## Staging → Production

Requirements:

* Approval
* Evaluation Thresholds Met

---

# Rollback Workflow

Example:

```text
Production v3
       ↓
Issue Detected
       ↓
Rollback
       ↓
Production v2
```

---

# Registry Database Fields

```text
Model ID

Version

Stage

Artifact Path

Created By

Created At

Metrics
```

---

# Registry APIs

## Register Model

```http
POST /models
```

---

## List Models

```http
GET /models
```

---

## Get Model Version

```http
GET /models/{id}
```

---

## Promote Model

```http
POST /models/{id}/promote
```

---

## Rollback Model

```http
POST /models/{id}/rollback
```

---

# Model States

```text
DRAFT

STAGING

PRODUCTION

ARCHIVED
```

---

# Governance Rules

* Production models cannot be deleted.
* Every promotion must be logged.
* Every rollback must be auditable.
* Every artifact must be versioned.

---

# Future Features

* Multi-Tenant Registry
* Approval Workflows
* Team Ownership
* Compliance Tracking
* Signed Artifacts

---

# Design Goals

* Reliable
* Auditable
* Reproducible
* Secure
* Enterprise Ready
