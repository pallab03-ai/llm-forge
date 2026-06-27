# Product Requirements Document (PRD)

## Product Name

**LLM Forge** — A production-grade LLMOps platform for fine-tuning, evaluating, and deploying language models.

---

## Document Version

**Version:** 3.0  
**Status:** Hardened MVP Requirements (Decoupled Workflows, Local Artifact Storage, Optimized Dataset Limits)  
**Last Updated:** 2025-07-11

---

## MVP Scope

The MVP supports the following capabilities:

- Dataset Upload, Validation & Versioning
- QLoRA Training (single method, single model)
- Training Job Queue & Lifecycle Management
- Training Artifact Management & Validation
- Training Reproducibility (full metadata capture)
- Experiment Tracking
- Model Evaluation (ROUGE + BERTScore)
- Model Registry
- Inference Deployment
- Observability & Monitoring

---

## User Roles

### Admin

Administrators have full access to all platform resources and management features.

### User

Users can manage their own datasets, training jobs, evaluations, deployments, and models.

---

## Functional Requirements

### Dataset Management

#### User Story

As a user, I want to upload datasets so that I can use them for model training.

#### Requirements

- Upload datasets in CSV format
- Upload datasets in JSON format
- Upload datasets in JSONL format (primary training format: Alpaca schema)
- Store dataset metadata
- Automatically create dataset versions
- Track dataset ownership and creation date
- Maximum dataset size: 250 MB / 1,000,000 records (optimized for Gemma 3 1B IT + QLoRA + Colab T4)
- Soft delete support for datasets

---

### Dataset Validation

#### User Story

As a user, I want my dataset validated before training begins to ensure data quality.

#### Validation Rules

- Detect missing values
- Detect duplicate records
- Detect empty prompts
- Detect empty responses
- Detect excessively long samples
- Validate dataset schema consistency

---

### Training

#### User Story

As a user, I want to fine-tune a language model using QLoRA so that I can adapt it to my specific task.

#### Requirements

- **MVP Training Method: QLoRA Only**
  - 4-bit NF4 quantization with double quantization
  - LoRA adapter-based fine-tuning (not full fine-tuning)
  - Gradient checkpointing enabled by default
  - SFT (Supervised Fine-Tuning) via QLoRA
- **Future (Post-MVP):** SFT with full LoRA, RLHF/DPO/PPO

#### QLoRA Configuration (MVP Defaults)

| Parameter              | Value                                                         |
| ---------------------- | ------------------------------------------------------------- |
| Quantization           | 4-bit NF4                                                     |
| Double Quantization    | Enabled                                                       |
| Compute Dtype          | bfloat16                                                      |
| LoRA Rank (r)          | 16                                                            |
| LoRA Alpha             | 32                                                            |
| LoRA Dropout           | 0.05                                                          |
| Target Modules         | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| Task Type              | CAUSAL_LM                                                     |
| Gradient Checkpointing | Enabled                                                       |
| Max Epochs             | 10                                                            |
| Max Duration           | 24 hours                                                      |
| Max Concurrent Jobs    | 1                                                             |

#### Supported Models (MVP)

| Model         | HuggingFace ID         | Parameters | Context | Use Case                                  |
| ------------- | ---------------------- | ---------- | ------- | ----------------------------------------- |
| Gemma 3 1B IT | `google/gemma-3-1b-it` | 1B         | 32K     | Instruction-following, Q&A, summarization |

**Future Models (Post-MVP):** `google/gemma-3-4b-it`, `meta-llama/Llama-3.2-1B`, `meta-llama/Llama-3.2-3B`, `mistralai/Mistral-7B-v0.3`

#### Training Constraints

- Maximum 10 epochs per training job
- Maximum 24-hour training duration
- Maximum 1 concurrent training job
- Automatic OOM detection and graceful failure
- Training job timeout with status transition to FAILED

#### Training Inputs

- Base Model (google/gemma-3-1b-it)
- Dataset Version
- Training Method (QLoRA)
- Number of Epochs (max 10)
- Learning Rate
- Batch Size

#### Training Outputs

- Training Metrics
- LoRA Adapter Artifacts
- Training Logs
- Training Metadata (reproducibility)

---

### Training Infrastructure

#### User Story

As a user, I want my training jobs to be queued, tracked, and managed through a complete lifecycle so that I can monitor progress and handle failures gracefully.

#### Requirements

- **Job Queue System:** Redis + RQ (Redis Queue) for asynchronous job processing
- **Job States:** QUEUED → RUNNING → COMPLETED / FAILED / CANCELLED
- **Job Lifecycle:**
  1. User submits training request via API
  2. Job is enqueued with QUEUED status
  3. RQ worker picks up job, transitions to RUNNING
  4. Training pipeline executes (9-step pipeline, see below)
  5. On success: COMPLETED with artifact paths
  6. On failure: FAILED with error details and traceback
  7. User can CANCEL a QUEUED or RUNNING job
- **9-Step Training Pipeline:**
  1. Validate dataset and configuration
  2. Load and quantize base model (NF4 + double quant)
  3. Apply QLoRA configuration
  4. Apply LoRA adapter configuration
  5. Execute training loop
  6. Save LoRA adapter artifacts
  7. Generate reproducibility metadata
  8. Validate artifacts (4-file check)
  9. Mark training job as COMPLETED
- **Note:** Evaluation, Model Registry, and Deployment are **separate workflows** — they are NOT part of the training pipeline. Training success = job completes + valid artifacts + reproducibility metadata.
- **Worker Configuration:** 1 RQ worker process (MVP)
- **Job Persistence:** Job status and metadata stored in PostgreSQL
- **Failure Handling:** Automatic OOM detection, timeout handling, error traceback capture

---

### Artifact Management

#### User Story

As a user, I want training artifacts to be automatically saved, validated, and stored so that I can reliably deploy my fine-tuned model.

#### Requirements

- **Required Artifacts (4-file validation):**
  1. `adapter_model.safetensors` — LoRA adapter weights
  2. `adapter_config.json` — PEFT/LoRA configuration
  3. `tokenizer/` — Tokenizer files (tokenizer.json, tokenizer_config.json, special_tokens_map.json, added_tokens.json)
  4. `training_metadata.json` — Full training metadata for reproducibility
- **Artifact Validation:** All 4 artifact groups must be present and valid before marking job as COMPLETED
- **Storage Backend:** Local Filesystem
- **Storage Path:** `artifacts/{job_id}/`
- **Artifact Integrity:** Validate file sizes, JSON parse checks, safetensors header validation
- **Future Infrastructure (Post-MVP):** MinIO / S3-compatible object storage, presigned URLs for artifact upload/download

---

### Training Reproducibility

#### User Story

As a user, I want complete training metadata captured so that I can reproduce any training run and understand exactly how a model was created.

#### Requirements

- **Captured Metadata:**
  - Random seed value
  - Python version
  - Library versions: `torch`, `transformers`, `peft`, `bitsandbytes`, `trl`, `accelerate`, `datasets`
  - Full QLoRA configuration (quantization, LoRA params)
  - Training hyperparameters (epochs, batch size, learning rate, etc.)
  - Dataset version and row count
  - Base model identifier and revision
  - Training duration and GPU info
  - Final loss and metrics
- **Metadata Format:** JSON stored as `training_metadata.json`
- **Example Metadata Structure:**

  ```json
  {
    "seed": 42,
    "versions": {
      "python": "3.14.2",
      "torch": "2.7.1",
      "transformers": "4.52.4",
      "peft": "0.15.2",
      "bitsandbytes": "0.46.0",
      "trl": "0.19.0",
      "accelerate": "1.7.0",
      "datasets": "3.6.0"
    },
    "base_model": "google/gemma-3-1b-it",
    "dataset_version": "v1",
    "dataset_rows": 5000,
    "quantization_config": {
      "load_in_4bit": true,
      "bnb_4bit_quant_type": "nf4",
      "bnb_4bit_use_double_quant": true,
      "bnb_4bit_compute_dtype": "bfloat16"
    },
    "lora_config": {
      "r": 16,
      "lora_alpha": 32,
      "lora_dropout": 0.05,
      "target_modules": [
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj"
      ],
      "task_type": "CAUSAL_LM"
    },
    "training_args": {
      "num_train_epochs": 3,
      "per_device_train_batch_size": 4,
      "gradient_accumulation_steps": 4,
      "learning_rate": 0.0002,
      "warmup_steps": 100,
      "max_grad_norm": 1.0,
      "logging_steps": 10,
      "save_strategy": "no",
      "bf16": true,
      "gradient_checkpointing": true
    },
    "training_results": {
      "total_steps": 375,
      "training_loss": 1.234,
      "train_runtime": 1234.5,
      "train_samples_per_second": 4.87
    }
  }
  ```

---

### Experiment Tracking

#### User Story

As a user, I want visibility into training performance and experiment history.

#### Metrics

- Training Loss
- Validation Loss
- Learning Rate
- GPU Memory Usage
- Training Duration
- Throughput

---

### Evaluation

#### User Story

As a user, I want to evaluate and compare trained models.

#### Evaluation Metrics (MVP)

- **ROUGE** — ROUGE-1, ROUGE-2, ROUGE-L for n-gram overlap assessment
- **BERTScore** — Semantic similarity using contextual embeddings

**Future (Post-MVP):** Semantic Similarity (sentence-transformers), RAGAS, LLM-as-Judge

#### Evaluation Requirements

- ROUGE and BERTScore are **required** for all evaluation runs
- Evaluation is a **separate workflow** from training — it is NOT required for training completion
- Users may evaluate models at any time after training completes
- Evaluation reports include per-metric scores and aggregate summaries
- **Future (Post-MVP):** Automated quality gates for production promotion

#### Evaluation Outputs

- Evaluation Reports
- Model Comparison Results
- Leaderboards
- Performance Summaries

---

### Model Registry

#### User Story

As a user, I want to manage model versions throughout their lifecycle.

#### Model States

- Draft
- Staging
- Production
- Archived

#### Registry Features

- Model Versioning
- Artifact Tracking
- Promotion Workflow (user-initiated, not automated)
- Rollback Support
- **Note:** Model Registry is a **separate workflow** from training — training completion does NOT depend on registry registration. Users explicitly register models after training completes.

---

### Deployment

#### User Story

As a user, I want to deploy trained models as inference endpoints.

#### Deployment Configuration (MVP)

- **Inference Engine:** Transformers + PEFT (single-instance)
- **Max Input Tokens:** 4096
- **Max Output Tokens:** 1024
- **Default Temperature:** 0.7
- **Deployment Type:** Single-instance (no auto-scaling in MVP)

#### Deployment Output

Inference API Endpoint

Example:

```http
POST /generate
```

#### Deployment Features

- Endpoint Creation
- Endpoint Management
- Health Monitoring
- Version-Based Deployment

---

### Monitoring

#### User Story

As a user, I want to monitor deployed models and API performance.

#### Observability Stack (MVP)

- **Metrics:** Prometheus + Grafana dashboards
- **Logging:** Structured JSON logging
- **Alerting:** Grafana alert rules for critical thresholds

#### Metrics

- Request Count
- Latency
- Error Rate
- Token Usage
- Throughput
- Resource Utilization
- Training Job Queue Depth
- Training Job Duration

---

## Non-Functional Requirements

### Reliability

- API Availability: **99%**
- Training Job Success Rate: **95%+**
- Job Queue Reliability: Jobs must not be lost on worker restart (RQ persistence)

### Scalability

- Support 1 concurrent training job (MVP)
- Support multiple deployed inference endpoints
- Scale horizontally in future releases

### Security

- JWT Authentication (24-hour token expiry)
- Password Hashing (bcrypt)
- Role-Based Access Control (RBAC)
- Secure API Access
- Audit Logging
- Rate Limiting: 100 requests/minute per user
- **No refresh tokens in MVP**

### Performance

- Inference Response Time: **< 2 Seconds**
- Fast Dataset Upload and Validation
- Efficient GPU Resource Utilization
- API Response Envelope: `{ success, data }` or `{ success, error }`

### Maintainability

- Modular Architecture
- Microservice-Ready Design
- Clear API Contracts
- Automated Testing Support
- Test Coverage: **70%+**
- Structured JSON Logging

---

## MVP Exclusions

The following features and capabilities are **explicitly excluded** from the MVP scope and planned for future releases:

### Training Methods

- SFT with full LoRA (MVP uses QLoRA only)
- RLHF (Reinforcement Learning from Human Feedback)
- DPO (Direct Preference Optimization)
- PPO (Proximal Policy Optimization)

### Infrastructure

- Kubernetes orchestration
- Ray distributed training
- vLLM inference engine
- Multi-GPU training
- Auto-scaling deployment
- Cloud deployment templates

### Evaluation

- RAGAS (Retrieval Augmented Generation Assessment)
- LLM-as-Judge evaluation
- Semantic Similarity (sentence-transformers)

### Models

- `google/gemma-3-4b-it`
- `meta-llama/Llama-3.2-1B`
- `meta-llama/Llama-3.2-3B`
- `mistralai/Mistral-7B-v0.3`

### Other

- Refresh tokens (JWT only, 24-hour expiry)
- Team workspaces / organization management
- Human feedback collection
- Auto model selection
- Agent fine-tuning
- Cost tracking
- Usage analytics

---

## Success Criteria

### Dataset Management

- Dataset Upload Success Rate > 99%

### Training

- Training Job Success Rate > 95%
- Job Queue Reliability: Zero lost jobs on worker restart
- Artifact Validation: 100% of completed jobs produce valid 4-file artifact sets
- Reproducibility: 100% of completed jobs include full `training_metadata.json`

### Evaluation

- Evaluation Completion Rate > 99%
- ROUGE + BERTScore computed for all evaluation runs

### Deployment

- Model Deployment Time < 2 Minutes

### Inference

- Average Response Latency < 2 Seconds

---

## Architecture Alignment

The MVP consists of **separate, decoupled workflows**. Training success does NOT require evaluation, registry registration, or deployment.

### Training Workflow (Primary)

```
Dataset → Validation → Training Infrastructure → QLoRA Engine → Artifact Management → Training Completed
```

### Separate Workflows (Post-Training)

```
Training Completed → Evaluation (optional, separate workflow)
Training Completed → Model Registry (user-initiated, separate workflow)
Model Registry → Deployment (user-initiated, separate workflow)
Deployment → Monitoring (continuous)
```

### Workflow Detail

1. **Dataset** — User uploads dataset (CSV/JSON/JSONL), stored with versioning
2. **Validation** — Schema, quality, and size checks (250MB/1M record limits)
3. **Training Infrastructure** — Job queued via Redis+RQ, lifecycle managed (QUEUED→RUNNING→COMPLETED/FAILED/CANCELLED)
4. **QLoRA Engine** — 4-bit NF4 quantization + LoRA adapters on google/gemma-3-1b-it
5. **Artifact Management** — 4-file validation (adapter_model.safetensors, adapter_config.json, tokenizer/, training_metadata.json), stored on local filesystem at `artifacts/{job_id}/`
6. **Training Completed** — Job completes with valid artifacts + reproducibility metadata
7. **Evaluation** — Separate workflow: ROUGE + BERTScore (NOT required for training completion)
8. **Model Registry** — Separate workflow: user explicitly registers models (NOT automatic after training)
9. **Deployment** — Separate workflow: user deploys registered models as inference endpoints
10. **Monitoring** — Prometheus + Grafana dashboards for API and model metrics

### MVP Scope Clarification

**Training success** = job completes + valid artifacts + reproducibility metadata. Training success does **NOT** require:

- Evaluation to be run
- Model to be registered in the registry
- Model to be deployed

These are separate, user-initiated workflows that happen after training completes.

---

## Version

**Version:** 3.0  
**Status:** Hardened MVP Requirements (Decoupled Workflows, Local Artifact Storage, Optimized Dataset Limits)  
**Last Updated:** 2025-07-11
