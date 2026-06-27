# Training Service

## Purpose

The Training Service is the core component of LLM Forge.

It manages model fine-tuning, experiment execution, checkpoint management, resource tracking, and training orchestration.

---

# Supported Models

## Phase 1

* Mistral 7B Instruct
* Llama 3 8B
* Qwen 2.5 7B

---

# Supported Training Methods

## SFT

Supervised Fine-Tuning

---

## LoRA

Low-Rank Adaptation

---

## QLoRA

Quantized Low-Rank Adaptation

---

## PEFT

Parameter Efficient Fine-Tuning

---

# Training Architecture

```text
Dataset
    ↓
Formatter
    ↓
Tokenizer
    ↓
Data Collator
    ↓
Trainer
    ↓
Checkpoint
    ↓
Evaluation
    ↓
Registry
```

---

# Training Workflow

```text
Create Job
      ↓
Queue Job
      ↓
Allocate Worker
      ↓
Load Dataset
      ↓
Load Model
      ↓
Train
      ↓
Evaluate
      ↓
Save Artifacts
      ↓
Register Model
```

---

# Training Job Configuration

```json
{
  "model":"mistral-7b",
  "method":"qlora",
  "epochs":3,
  "learning_rate":0.0002,
  "batch_size":4,
  "gradient_accumulation_steps":4
}
```

---

# QLoRA Configuration

## Quantization

```python
load_in_4bit=True

bnb_4bit_quant_type="nf4"

bnb_4bit_use_double_quant=True

bnb_4bit_compute_dtype=torch.bfloat16
```

---

# LoRA Configuration

```python
r=16

lora_alpha=32

lora_dropout=0.05

bias="none"
```

---

# Target Modules

```python
[
 "q_proj",
 "k_proj",
 "v_proj",
 "o_proj"
]
```

---

# Trainer Configuration

```python
per_device_train_batch_size=4

gradient_accumulation_steps=4

num_train_epochs=3

learning_rate=2e-4

logging_steps=10

save_steps=100
```

---

# Checkpoint Strategy

Store:

```text
checkpoint-100

checkpoint-200

checkpoint-300
```

---

# Artifact Storage

```text
artifacts/

    model/

    tokenizer/

    adapter/

    logs/
```

---

# Resource Monitoring

Track:

* GPU Memory
* GPU Utilization
* CPU Usage
* Training Time

---

# MLflow Integration

Log:

```text
Parameters

Metrics

Artifacts

Checkpoints
```

---

# Training Metrics

## Core Metrics

* Training Loss
* Validation Loss
* Learning Rate

---

## Infrastructure Metrics

* GPU Memory
* Throughput
* Training Duration

---

# Failure Recovery

## Worker Crash

Resume From:

```text
Latest Checkpoint
```

---

## OOM Recovery

Actions:

* Reduce Batch Size
* Enable Gradient Checkpointing

---

# Training States

```text
Queued
 ↓
Running
 ↓
Evaluating
 ↓
Completed
```

Failure Path

```text
Running
 ↓
Failed
```

---

# Worker Architecture

```text
Redis Queue
      ↓
Training Worker
      ↓
GPU Runtime
      ↓
Artifact Storage
```

---

# Training APIs

## Create Job

```http
POST /jobs
```

---

## Job Status

```http
GET /jobs/{id}
```

---

## Cancel Job

```http
POST /jobs/{id}/cancel
```

---

# Future Features

* DPO
* RLHF
* Multi-GPU
* DeepSpeed
* FSDP
* Distributed Training

---

# Design Goals

* Reproducible
* GPU Efficient
* Fault Tolerant
* Observable
* Production Ready
