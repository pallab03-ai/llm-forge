````md
# System Architecture

## High-Level Overview

LLM Forge is composed of six major layers:

1. Frontend Layer
2. API Layer
3. Data Layer
4. Training Layer
5. Evaluation Layer
6. Deployment Layer

---

## Architecture Diagram

```text
                    ┌──────────────────┐
                    │     Next.js      │
                    │     Frontend     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │     FastAPI      │
                    │   API Gateway    │
                    └────────┬─────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼

 ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
 │ PostgreSQL   │    │    Redis    │    │    MinIO     │
 │ Metadata DB  │    │ Job Queue   │    │ Object Store │
 └──────┬───────┘    └──────┬──────┘    └──────┬───────┘
        │                   │                  │
        ▼                   ▼                  ▼

                ┌──────────────────────┐
                │  Training Worker     │
                │  PEFT + TRL          │
                │  QLoRA + LoRA        │
                └──────────┬───────────┘
                           │
                           ▼

                ┌──────────────────────┐
                │       MLflow         │
                │ Experiment Tracking  │
                └──────────┬───────────┘
                           │
                           ▼

                ┌──────────────────────┐
                │ Evaluation Service   │
                └──────────┬───────────┘
                           │
                           ▼

                ┌──────────────────────┐
                │   Model Registry     │
                └──────────┬───────────┘
                           │
                           ▼

                ┌──────────────────────┐
                │ Inference Service    │
                │ FastAPI + vLLM       │
                └──────────────────────┘
````

---

## Frontend Layer

### Technology

* Next.js
* TypeScript
* Tailwind CSS
* ShadCN UI

### Responsibilities

* Dashboard
* Dataset Management
* Job Management
* Evaluation Visualization
* Deployment Management

---

## API Layer

### Technology

* FastAPI

### Responsibilities

* Authentication
* Dataset APIs
* Training APIs
* Evaluation APIs
* Deployment APIs

---

## Data Layer

### PostgreSQL

**Stores:**

* Users
* Datasets
* Jobs
* Evaluations
* Models

### MinIO

**Stores:**

* Uploaded Datasets
* Checkpoints
* LoRA Adapters
* Evaluation Artifacts

### Redis

**Stores:**

* Training Queue
* Background Jobs

---

## Training Layer

### Technology

* Transformers
* PEFT
* TRL
* Accelerate
* BitsAndBytes

### Supported Methods

* SFT (Supervised Fine-Tuning)
* LoRA (Low-Rank Adaptation)
* QLoRA (Quantized Low-Rank Adaptation)

### Training Flow

```text
Dataset
   ↓
Tokenization
   ↓
Formatting
   ↓
Trainer
   ↓
Checkpoint
   ↓
Evaluation
```

---

## Evaluation Layer

### Metrics

* ROUGE
* BERTScore
* Semantic Similarity

### Evaluation Pipeline

```text
Model
  ↓
Test Dataset
  ↓
Metric Computation
  ↓
Leaderboard
```

---

## Registry Layer

### Responsibilities

* Model Versioning
* Promotion
* Rollback
* Artifact Tracking

### Model Lifecycle

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

## Deployment Layer

### Technology

* FastAPI
* vLLM

### Endpoints

```http
POST /generate
POST /chat
GET  /health
```

---

## Observability

### Metrics

* GPU Usage
* Memory Usage
* Latency
* Error Rate
* Request Count

### Tools

* Prometheus
* Grafana

---

## Deployment Strategy

### Development

* Docker Compose

### Production

* Containerized Services

### Future

* Kubernetes Deployment

---

## Design Goals

* Modular
* Observable
* Reproducible
* Cost Efficient
* Production Ready

```
```
