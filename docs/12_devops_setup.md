# DevOps Setup

## Purpose

This document defines the infrastructure, deployment, CI/CD, containerization, and environment management strategy for LLM Forge.

---

# Development Environment

## Local Stack

```text
Frontend
Backend
PostgreSQL
Redis
MinIO
MLflow
```

---

# Docker Architecture

```text
docker-compose.yml

frontend

backend

postgres

redis

minio

mlflow
```

---

# Environment Variables

## Backend

```env
DATABASE_URL=

REDIS_URL=

MINIO_ENDPOINT=

MINIO_ACCESS_KEY=

MINIO_SECRET_KEY=

JWT_SECRET=

MLFLOW_TRACKING_URI=
```

---

## Frontend

```env
NEXT_PUBLIC_API_URL=
```

---

# Docker Services

## Frontend

Port:

```text
3000
```

---

## Backend

Port:

```text
8000
```

---

## PostgreSQL

Port:

```text
5432
```

---

## Redis

Port:

```text
6379
```

---

## MinIO

Port:

```text
9000
```

---

## MLflow

Port:

```text
5000
```

---

# CI/CD Pipeline

## GitHub Workflow

```text
Push
 ↓
Lint
 ↓
Test
 ↓
Build
 ↓
Docker Image
 ↓
Deploy
```

---

# Automated Checks

## Backend

* Ruff
* Black
* Pytest
* MyPy

---

## Frontend

* ESLint
* TypeScript Check
* Build Validation

---

# Deployment Environments

## Development

Purpose:

```text
Feature Development
```

---

## Staging

Purpose:

```text
Testing
```

---

## Production

Purpose:

```text
Live System
```

---

# Secret Management

Never store:

* API Keys
* Passwords
* JWT Secrets

Inside source code.

Use:

```text
Environment Variables
```

---

# Backup Strategy

## PostgreSQL

Daily Backup

---

## MinIO

Weekly Backup

---

# Disaster Recovery

Recovery Targets:

```text
Database < 30 Minutes

Artifacts < 1 Hour
```

---

# Future Infrastructure

* Kubernetes
* ArgoCD
* Terraform
* AWS Deployment
* GCP Deployment

---

# Design Goals

* Automated
* Reproducible
* Secure
* Scalable
