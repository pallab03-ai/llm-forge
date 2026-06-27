# Phase 4.1 — QLoRA Training Engine Planning Report (Revised)

> **Document Version**: 2.0 (Revised)  
> **Date**: 2025-07-11  
> **Status**: Approved Architecture Decisions Applied  
> **Scope**: Planning only — no code generated

---

## Revision Log

| Version | Date       | Changes                                                                                                                                                                                                |
| ------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1.0     | 2025-07-10 | Initial Phase 4.1 planning report                                                                                                                                                                      |
| 2.0     | 2025-07-11 | R1: Gemma 3 1B IT model swap; R2: Simplified Colab workflow; R3: Heartbeat removal; R4: Simplified OOM handling; R5: No intermediate checkpoints; R6: Supported Model Registry; R7: Adapter validation |

---

## 1. Executive Summary

Phase 4 implements the QLoRA training engine for LLM Forge, enabling users to fine-tune language models on custom datasets using 4-bit quantized LoRA adapters.

**Target Model**: `google/gemma-3-1b-it` — a 1-billion parameter instruction-tuned model from Google's Gemma 3 family. This model is preferred for the Phase 4 MVP because:

1. **T4 VRAM headroom**: At ~1B parameters in 4-bit quantization (~0.6 GB), the model leaves ~14 GB of VRAM for activations, optimizer states, and batch processing — far more comfortable than a 2B+ model which would consume ~1.2 GB just for weights.
2. **Faster iteration**: Smaller model means faster training epochs, enabling quicker feedback loops during development and testing.
3. **Instruction-tuned baseline**: The `-it` suffix means the model already follows instructions, so fine-tuning improves rather than teaches instruction-following — producing better results with fewer epochs.
4. **Colab-friendly**: Fits comfortably within T4's 16 GB VRAM with generous headroom for batch sizes up to 16 and sequence lengths up to 2048 without OOM risk.
5. **Sufficient capability**: 1B parameters is enough to demonstrate the full QLoRA pipeline end-to-end while keeping resource requirements minimal.

**Training Method**: QLoRA (4-bit quantization + LoRA adapters) — the most memory-efficient fine-tuning approach for consumer GPUs.

**Execution Environment**: Google Colab (T4 GPU, 16 GB VRAM). The Phase 4 MVP uses a **manual user-driven Colab workflow**: the platform generates a training package (notebook + dataset), the user executes it in Colab, and uploads the resulting adapter artifacts back to the platform.

**Core Pipeline** (preserved from v1.0):

```
Dataset Loader → Tokenizer → QLoRA Setup → SFT Trainer → Adapter Save → Artifact Registration
```

**Key Design Principles**:

- **Simplicity over automation**: The MVP avoids distributed job polling, heartbeat monitoring, and automatic OOM recovery. These are deferred to future phases.
- **Fail clearly**: When things go wrong (OOM, validation failure), the system fails with an actionable recommendation rather than silently retrying.
- **Minimal state**: No intermediate checkpoints, no heartbeat tables, no job claiming. Only final artifacts matter.
- **Extensibility via registry**: The Supported Model Registry abstracts model-specific configuration, making it trivial to add future models without touching core training logic.

---

## 2. Training Runner Architecture

### Pipeline Overview

The `QLoRATrainingRunner` replaces `MockTrainingRunner` and executes the following pipeline:

```
┌──────────────────────────────────────────────────────────────────┐
│                    QLoRATrainingRunner                            │
│                                                                  │
│  1. Download Dataset    ──── MinIO                               │
│  2. Validate JSONL      ──── Alpaca format check                 │
│  3. Load Tokenizer      ──── HuggingFace Hub (gemma-3-1b-it)     │
│  4. QLoRA Setup         ──── BitsAndBytesConfig + LoraConfig     │
│  5. SFTTrainer          ──── Transformers Trainer                │
│  6. Save Adapter         ──── adapter_model.safetensors           │
│  7. Validate Artifacts  ──── 4-file existence check               │
│  8. Upload Artifacts    ──── MinIO                                │
│  9. Update Job Status   ──── PostgreSQL (COMPLETED or FAILED)    │
└──────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component          | Responsibility                                                       |
| ------------------ | -------------------------------------------------------------------- |
| Dataset Loader     | Download dataset from MinIO, parse JSONL, validate Alpaca format     |
| Tokenizer          | Load `google/gemma-3-1b-it` tokenizer, apply chat template, tokenize |
| QLoRA Setup        | Configure BitsAndBytesConfig (4-bit NF4) + LoraConfig (r=16)         |
| SFTTrainer         | Run supervised fine-tuning with `transformers.SFTTrainer`            |
| Adapter Save       | Save LoRA adapter weights + config + tokenizer to output directory   |
| Artifact Validator | Verify all 4 required artifact files exist before marking COMPLETED  |
| Artifact Uploader  | Upload validated artifacts to MinIO                                  |
| Job Updater        | Set job status to COMPLETED or FAILED in PostgreSQL                  |

### Status Transitions

```
QUEUED → RUNNING → COMPLETED
                  → FAILED
         → CANCELLED
```

- **QUEUED → RUNNING**: User starts training (Colab notebook begins execution)
- **RUNNING → COMPLETED**: Training finished, artifacts validated and uploaded
- **RUNNING → FAILED**: Training error (OOM, validation failure, etc.)
- **QUEUED/RUNNING → CANCELLED**: User cancels the job

### Interface Contract

The `QLoRATrainingRunner` must implement:

```python
class QLoRATrainingRunner:
    async def run(self, job_id: str, config: TrainingConfig) -> None:
        """Execute the full QLoRA training pipeline.

        On success: job status = COMPLETED, artifacts uploaded to MinIO.
        On failure: job status = FAILED, error_message set with actionable recommendation.
        """
        ...
```

---

## 3. Dataset Format Specification

> **Preserved from v1.0 — no changes.**

### Alpaca JSONL Format

Each line in the dataset file is a JSON object with three fields:

```json
{"instruction": "Translate to French", "input": "Hello world", "output": "Bonjour le monde"}
{"instruction": "Summarize the text", "input": "Long text here...", "output": "Short summary"}
{"instruction": "Classify sentiment", "input": "I love this product!", "output": "Positive"}
```

| Field         | Type   | Required | Description                    |
| ------------- | ------ | -------- | ------------------------------ |
| `instruction` | string | Yes      | The task instruction           |
| `input`       | string | No       | Optional context or input text |
| `output`      | string | Yes      | The expected response          |

### Formatting Rules

1. One JSON object per line (JSONL format)
2. `instruction` and `output` must be non-empty strings
3. `input` may be empty string or omitted
4. Maximum dataset size: 1 GB / 10,000,000 records (per architecture decisions)
5. Encoding: UTF-8

### Prompt Template

For `google/gemma-3-1b-it`, the Alpaca format is converted to the model's chat template:

```
<start_of_turn>user
{instruction}
{input}<end_of_turn>
<start_of_turn>model
{output}<end_of_turn>
```

---

## 4. QLoRA Configuration

### BitsAndBytesConfig

```python
from transformers import BitsAndBytesConfig

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.float16,
)
```

| Parameter                   | Value            | Rationale                                                      |
| --------------------------- | ---------------- | -------------------------------------------------------------- |
| `load_in_4bit`              | `True`           | 4-bit quantization — reduces VRAM from ~2 GB (fp16) to ~0.6 GB |
| `bnb_4bit_quant_type`       | `"nf4"`          | NormalFloat4 — optimal distribution for weights                |
| `bnb_4bit_use_double_quant` | `True`           | Double quantization — saves ~0.1 GB additional                 |
| `bnb_4bit_compute_dtype`    | `torch.float16` | T4: FP16 (bfloat16 requires Ampere+/compute capability 8.0+)    |

### Model Loading

```python
from transformers import AutoModelForCausalLM

model = AutoModelForCausalLM.from_pretrained(
    "google/gemma-3-1b-it",
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.float16,
    attn_implementation="eager",  # T4 does not support Flash Attention 2
)
```

> **Note**: `attn_implementation="eager"` is required because T4 (compute capability 7.5) does not support Flash Attention 2, which requires compute capability ≥ 8.0.

### VRAM Budget for Gemma 3 1B IT on T4

```
T4 GPU: 16 GB VRAM
├── Model weights (4-bit NF4):     0.6 GB  ██
├── Quantization constants:       0.15 GB ▏
├── LoRA adapters (fp16):          0.02 GB ▏
├── Activations (grad_ckpt):       2.5 GB  ████████
├── Optimizer (8-bit paged):       0.5 GB  ███
├── CUDA context + overhead:       1.0 GB  ███
├── ─────────────────────────────────────
├── TOTAL:                         ~4.8 GB
└── HEADROOM:                      ~11.2 GB  ████████████████████████████████████████
```

**Comparison with Gemma 2B** (previous design):

| Resource        | Gemma 2B (4-bit) | Gemma 3 1B IT (4-bit) | Savings |
| --------------- | ---------------- | --------------------- | ------- |
| Model weights   | ~1.2 GB          | ~0.6 GB               | 50%     |
| Total estimated | ~7.0 GB          | ~4.8 GB               | 31%     |
| Headroom        | ~9.0 GB          | ~11.2 GB              | +24%    |

The additional 2.2 GB of headroom allows:

- Larger batch sizes (up to 16 vs. 8 for Gemma 2B)
- Longer sequence lengths (up to 4096 vs. 2048 for Gemma 2B)
- More room for dataset processing without OOM risk

---

## 5. PEFT Configuration

### LoraConfig

```python
from peft import LoraConfig, TaskType

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
)
```

| Parameter        | Value                                   | Rationale                                                    |
| ---------------- | --------------------------------------- | ------------------------------------------------------------ |
| `r`              | `16`                                    | Rank 16 — good balance of expressiveness vs. parameters      |
| `lora_alpha`     | `32`                                    | 2× rank — standard scaling, stable training                  |
| `lora_dropout`   | `0.05`                                  | Light regularization — prevents overfitting                  |
| `bias`           | `"none"`                                | No bias training — standard for LoRA                         |
| `task_type`      | `CAUSAL_LM`                             | Causal language modeling task                                |
| `target_modules` | `["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"]` | Attention + MLP projection layers — broader coverage for fine-tuning |

### Target Modules for Gemma 3 1B IT

The `google/gemma-3-1b-it` model uses the same attention projection naming convention as the Gemma family:

- `q_proj` — Query projection (attention)
- `k_proj` — Key projection (attention)
- `v_proj` — Value projection (attention)
- `o_proj` — Output projection (attention)
- `gate_proj` — Gate projection (MLP)
- `up_proj` — Up projection (MLP)
- `down_proj` — Down projection (MLP)

> **Note**: Including MLP projection layers (`gate_proj`, `up_proj`, `down_proj`) alongside attention projections significantly increases the number of trainable parameters and improves fine-tuning quality, especially for domain adaptation tasks. This 7-module configuration is the default in the Supported Model Registry.

> **Note**: These module names are confirmed for the Gemma 3 architecture. The Supported Model Registry (Section 9) manages these mappings to avoid hardcoding in the training runner.

### Trainable Parameters

| Metric                 | Value   |
| ---------------------- | ------- |
| Total model parameters | ~1B     |
| Trainable (LoRA)       | ~5.4M   |
| Trainable percentage   | ~0.54%  |
| Adapter size (fp16)    | ~22 MB  |

> **Note**: With 7 target modules (4 attention + 3 MLP), trainable parameters are approximately double the 4-module configuration. Each LoRA adapter adds 2 × r × (input_dim + output_dim) parameters per module. For rank 16 with hidden_size=2304 and intermediate_size=9216, the 7-module config yields ~5.4M trainable parameters (~0.54% of total).

---

## 6. Training Configuration

### TrainingArguments

```python
from transformers import TrainingArguments

training_args = TrainingArguments(
    output_dir=f"/tmp/qlora_training/{job_id}",
    num_train_epochs=config.epochs,              # 1-10 (from TrainingConfig)
    per_device_train_batch_size=config.batch_size,  # 1-64 (from TrainingConfig)
    gradient_accumulation_steps=4,
    learning_rate=config.learning_rate,          # 1e-7 to 1.0 (from TrainingConfig)
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    logging_steps=10,
    save_strategy="no",                         # No intermediate checkpoints (R5)
    save_total_limit=1,                         # Only final save
    fp16=True,                                  # T4: FP16 (bfloat16 requires Ampere+)
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},
    max_grad_norm=1.0,
    optim="paged_adamw_8bit",
    report_to="none",
    remove_unused_columns=False,
    max_seq_length=config.max_seq_length,       # 64-8192 (from TrainingConfig)
)
```

### Key Changes from v1.0

| Setting            | v1.0 Value | v2.0 Value  | Reason (R5)                                                                                |
| ------------------ | ---------- | ----------- | ------------------------------------------------------------------------------------------ |
| `save_strategy`    | `"steps"`  | `"no"`      | No intermediate checkpoints — reduced storage, reduced complexity, reduced failure surface |
| `save_steps`       | `100`      | _(removed)_ | Not applicable with `save_strategy="no"`                                                   |
| `save_total_limit` | `3`        | `1`         | Only the final adapter save matters                                                        |

### Why No Intermediate Checkpoints (R5)

1. **Reduced storage**: Each checkpoint for Gemma 2B was ~2.5 GB. Even for Gemma 3 1B (~1 GB each), 3 checkpoints = 3 GB of unnecessary disk usage on Colab's limited storage.
2. **Reduced complexity**: No need to manage checkpoint cleanup, select best checkpoint, or handle checkpoint corruption.
3. **Reduced failure surface**: Checkpoint saving can fail (disk full, permission errors, interrupted writes). Removing intermediate saves eliminates this failure mode.
4. **MVP simplicity**: For the MVP, if training fails, the user simply re-runs the Colab notebook. Automatic resume from checkpoints is not needed.

### Config Mapping: TrainingConfig → TrainingArguments

| TrainingConfig Field | TrainingArguments Field       | Mapping              |
| -------------------- | ----------------------------- | -------------------- |
| `epochs`             | `num_train_epochs`            | Direct (1-10)        |
| `batch_size`         | `per_device_train_batch_size` | Direct (1-64)        |
| `learning_rate`      | `learning_rate`               | Direct (1e-7 to 1.0) |
| `max_seq_length`     | `max_seq_length`              | Direct (64-8192)     |

### OOM Cross-Field Guard

Preserved from existing `TrainingConfig`:

```python
if config.batch_size * config.max_seq_length > 262144:
    raise ValueError("batch_size * max_seq_length must be ≤ 262144 to prevent OOM")
```

---

## 7. Artifact Design

### Artifact Layout

> **Preserved from v1.0 — no changes to layout.**

```
artifacts/{job_id}/
├── adapter_model.safetensors    # LoRA adapter weights
├── adapter_config.json          # LoRA configuration (r, alpha, modules, etc.)
├── tokenizer/                   # Tokenizer files (copied from base model)
│   ├── tokenizer.json
│   ├── tokenizer_config.json
│   ├── special_tokens_map.json
│   └── tokenizer.model          # SentencePiece model file for Gemma 3
└── training_metadata.json       # Training run metadata
```

### training_metadata.json

```json
{
  "job_id": "uuid",
  "base_model": "google/gemma-3-1b-it",
  "training_type": "qlora",
  "configuration": {
    "epochs": 3,
    "batch_size": 4,
    "learning_rate": 0.0002,
    "max_seq_length": 2048
  },
  "lora_config": {
    "r": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.05,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
  },
  "quantization_config": {
    "load_in_4bit": true,
    "bnb_4bit_quant_type": "nf4",
    "bnb_4bit_use_double_quant": true,
    "bnb_4bit_compute_dtype": "float16"
  },
  "training_stats": {
    "total_steps": 150,
    "final_loss": 0.85,
    "train_runtime_seconds": 120.5,
    "train_samples_per_second": 8.3
  },
  "created_at": "2025-07-11T12:00:00Z"
}
```

### Artifact Storage

- **Primary**: MinIO (S3-compatible object storage)
- **Path convention**: `artifacts/{job_id}/`
- **Never store artifacts in PostgreSQL** (per architecture decisions)

---

## 8. Failure Handling

### Simplified OOM Handling (R4)

When a CUDA Out Of Memory error occurs during training:

1. **Catch** the `torch.cuda.OutOfMemoryError` exception
2. **Set job status** to `FAILED`
3. **Store actionable recommendation** in `error_message`

**Example error messages**:

| Scenario                  | `error_message`                                                                         |
| ------------------------- | --------------------------------------------------------------------------------------- |
| OOM during forward pass   | `"CUDA Out Of Memory. Reduce batch_size or max_seq_length."`                            |
| OOM during optimizer step | `"CUDA Out Of Memory. Reduce batch_size to 2 or enable gradient_checkpointing."`        |
| OOM during model loading  | `"CUDA Out Of Memory during model loading. Model may be too large for available VRAM."` |

**What we do NOT do** (removed from v1.0):

- ❌ Automatic batch size reduction
- ❌ Automatic retry with smaller batch
- ❌ Automatic resume from checkpoint
- ❌ Gradient accumulation adjustment

**Rationale**: Automatic OOM recovery adds significant complexity (state management, retry logic, partial progress tracking) for marginal benefit in an MVP. The user can read the error message, adjust their configuration, and re-submit. This is the correct trade-off for Phase 4.

### Other Failure Modes

| Failure Mode                | Handling                                                                  |
| --------------------------- | ------------------------------------------------------------------------- |
| Dataset download failure    | FAILED + `"Failed to download dataset: {detail}"`                         |
| Invalid JSONL format        | FAILED + `"Invalid dataset format: line {n} is not valid JSON"`           |
| Missing required fields     | FAILED + `"Missing required field 'instruction' on line {n}"`             |
| Model download failure      | FAILED + `"Failed to download model google/gemma-3-1b-it: {detail}"`      |
| Tokenizer loading failure   | FAILED + `"Failed to load tokenizer: {detail}"`                           |
| Training loss NaN           | FAILED + `"Training produced NaN loss. Reduce learning_rate."`            |
| Disk full during save       | FAILED + `"Disk full. Cannot save adapter artifacts."`                    |
| Artifact validation failure | FAILED + `"Artifact validation failed: {missing_files}"` (see Section 10) |
| Upload to MinIO failure     | FAILED + `"Failed to upload artifacts: {detail}"`                         |

### No Heartbeat Architecture (R3)

> **Note**: The heartbeat architecture (heartbeat table, heartbeat endpoint, heartbeat monitoring, heartbeat timeout logic) from v1.0 has been **removed** and **deferred to a future distributed execution phase**. The heartbeat mechanism was designed to detect Colab notebook disconnects in a polling/claiming architecture. Since the Phase 4 MVP uses a manual user-driven Colab workflow (R2), there is no remote worker to monitor. If the user's Colab notebook disconnects, the training simply stops — the job remains in RUNNING status until the user re-executes or cancels it. Heartbeat monitoring will be reconsidered when distributed remote workers are introduced in a future phase.

---

## 9. Supported Model Registry (R6)

### Purpose

The Supported Model Registry abstracts model-specific configuration away from the training runner. This provides:

1. **Single source of truth**: Model names, LoRA target modules, and special configurations live in one place.
2. **Easy extensibility**: Adding a new model requires only a registry entry — no training runner changes.
3. **Validation**: The API can reject unsupported models before training begins.
4. **Future-proofing**: When Phase 4.2+ adds more models, the registry pattern is already established.

### SUPPORTED_MODELS Dictionary

```python
SUPPORTED_MODELS: dict[str, ModelConfig] = {
    "google/gemma-3-1b-it": ModelConfig(
        display_name="Gemma 3 1B IT",
        hf_model_id="google/gemma-3-1b-it",
        parameter_count="1B",
        quantized_vram_gb=0.6,
        max_seq_length=8192,
        lora_target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        attn_implementation="eager",          # T4: no Flash Attention 2
        torch_dtype="float16",
        chat_template="gemma",                # Template key for prompt formatting
        special_tokens={
            "bos_token": "<bos>",
            "eos_token": "<eos>",
            "pad_token": "<pad>",
        },
    ),
}
```

### ModelConfig Data Class

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelConfig:
    display_name: str
    hf_model_id: str
    parameter_count: str
    quantized_vram_gb: float
    max_seq_length: int
    lora_target_modules: list[str]
    attn_implementation: str
    torch_dtype: str
    chat_template: str
    special_tokens: dict[str, str]
```

### How Future Models Are Added

To add a new model (e.g., `meta-llama/Llama-3.2-1B-Instruct`):

1. Add a new entry to `SUPPORTED_MODELS`
2. Specify the model's LoRA target modules (may differ from Gemma)
3. Set `attn_implementation` based on GPU compatibility
4. Define the `chat_template` key for prompt formatting
5. No changes to `QLoRATrainingRunner` — it reads from the registry

### LoRA Target Module Management

Different models use different naming conventions for attention projection layers:

| Model Family | Target Modules                         |
| ------------ | -------------------------------------- |
| Gemma 3      | `q_proj`, `k_proj`, `v_proj`, `o_proj` |
| Llama 3      | `q_proj`, `k_proj`, `v_proj`, `o_proj` |
| Mistral      | `q_proj`, `k_proj`, `v_proj`, `o_proj` |
| Qwen 2       | `q_proj`, `k_proj`, `v_proj`, `o_proj` |

> Most modern transformer models use the same naming convention. However, the registry ensures that if a model uses different names (e.g., `query`, `key`, `value`), the training runner doesn't need modification.

### API Validation

When a user creates a training job with `base_model="google/gemma-3-1b-it"`:

1. Look up `base_model` in `SUPPORTED_MODELS`
2. If not found → reject with `422 Unprocessable Entity: "Unsupported model: {base_model}. Supported models: {list(SUPPORTED_MODELS.keys())}"`
3. If found → proceed with job creation

---

## 10. Artifact Validation (R7)

### Validation Before COMPLETED

Before marking a training job as `COMPLETED`, the system must validate that all required artifact files exist in the output directory:

| File                        | Required | Validation                                   |
| --------------------------- | -------- | -------------------------------------------- |
| `adapter_model.safetensors` | ✅       | File exists and size > 0                     |
| `adapter_config.json`       | ✅       | File exists, valid JSON, contains `"r"` key  |
| `tokenizer/tokenizer.json`  | ✅       | File exists and size > 0                     |
| `training_metadata.json`    | ✅       | File exists, valid JSON, contains `"job_id"` |

### Validation Flow

```
Training Complete
       │
       ▼
┌──────────────────────┐
│  Check 4 files exist │
│  + non-zero size      │
└──────────┬───────────┘
           │
     ┌─────┴─────┐
     │           │
  All exist   Missing files
     │           │
     ▼           ▼
  COMPLETED    FAILED
  Upload to    error_message =
  MinIO        "Artifact validation failed:
                missing [adapter_config.json]"
               Do NOT register
               artifacts in MinIO
```

### Validation Implementation

```python
REQUIRED_ARTIFACT_FILES = [
    "adapter_model.safetensors",
    "adapter_config.json",
    "tokenizer/tokenizer.json",
    "training_metadata.json",
]

def validate_artifacts(output_dir: Path) -> tuple[bool, list[str]]:
    """Validate all required artifact files exist and are non-empty.

    Returns:
        (is_valid, missing_files) — if is_valid is False,
        missing_files contains the list of missing/empty files.
    """
    missing = []
    for file_path in REQUIRED_ARTIFACT_FILES:
        full_path = output_dir / file_path
        if not full_path.exists() or full_path.stat().st_size == 0:
            missing.append(file_path)
    return (len(missing) == 0, missing)
```

### On Validation Failure

- Job status → `FAILED`
- `error_message` → `"Artifact validation failed: missing [{missing_files}]"`
- Artifacts are **NOT** uploaded to MinIO
- Artifacts are **NOT** registered in the model registry
- The user must fix the issue and re-run training

---

## 11. Google Colab Integration (R2)

### Simplified Colab Workflow

The Phase 4 MVP uses a **manual user-driven workflow**. There is no job polling, no job claiming, no remote worker architecture, and no distributed execution.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Phase 4 MVP Colab Workflow                      │
│                                                                     │
│  1. User creates training job via API                               │
│     → Job status: QUEUED                                            │
│                                                                     │
│  2. Platform generates training package                              │
│     → Colab notebook (.ipynb) with embedded:                        │
│       - Dataset download URL (presigned, from MinIO)                 │
│       - Training configuration (epochs, batch_size, etc.)           │
│       - Model name (google/gemma-3-1b-it)                          │
│       - Artifact upload URL (presigned, to MinIO)                    │
│       - Job ID for status updates                                   │
│     → Job status: QUEUED (awaiting user execution)                  │
│                                                                     │
│  3. User opens generated Colab notebook                             │
│     → Notebook is self-contained — no API polling needed            │
│                                                                     │
│  4. User executes training manually in Colab                        │
│     → Job status: RUNNING (set by notebook at start)                │
│     → QLoRA training pipeline executes                              │
│     → On success: artifacts uploaded, job → COMPLETED               │
│     → On failure: job → FAILED with error message                   │
│                                                                     │
│  5. Adapter artifacts uploaded back to platform                      │
│     → Via presigned URL to MinIO                                    │
│     → Job status: COMPLETED                                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Colab Notebook Structure

The generated notebook contains these cells:

| Cell | Content                                                                                                |
| ---- | ------------------------------------------------------------------------------------------------------ |
| 1    | Install dependencies (`transformers`, `peft`, `bitsandbytes`, `accelerate`, `datasets`, `safetensors`) |
| 2    | Authenticate with platform (API key or JWT)                                                            |
| 3    | Set job status to RUNNING (`PATCH /training-jobs/{id}`)                                                |
| 4    | Download dataset from presigned URL                                                                    |
| 5    | Validate dataset format (Alpaca JSONL)                                                                 |
| 6    | Load model + tokenizer (`google/gemma-3-1b-it`)                                                        |
| 7    | Configure QLoRA (BitsAndBytes + LoRA)                                                                  |
| 8    | Run SFTTrainer                                                                                         |
| 9    | Validate artifacts (4-file check)                                                                      |
| 10   | Upload artifacts to MinIO via presigned URL                                                            |
| 11   | Set job status to COMPLETED (`PATCH /training-jobs/{id}`)                                              |

### API Endpoints Needed

Only existing endpoints + minimal additions:

| Endpoint                           | Purpose                                      | Status   |
| ---------------------------------- | -------------------------------------------- | -------- |
| `POST /training-jobs`              | Create training job                          | Existing |
| `GET /training-jobs/{id}`          | Get job status                               | Existing |
| `PATCH /training-jobs/{id}/status` | Update job status (RUNNING/COMPLETED/FAILED) | **New**  |
| `GET /training-jobs/{id}/package`  | Download generated Colab notebook            | **New**  |
| `DELETE /training-jobs/{id}`       | Cancel job                                   | Existing |

### What Was Removed (R2 + R3)

| Removed Item                         | Reason                                                               |
| ------------------------------------ | -------------------------------------------------------------------- |
| `POST /training-jobs/next`           | No job polling/claiming — user explicitly starts their own job       |
| `POST /training-jobs/{id}/start`     | No remote worker — notebook sets status directly                     |
| `POST /training-jobs/{id}/heartbeat` | No heartbeat monitoring — manual workflow, no disconnect detection   |
| `POST /training-jobs/{id}/complete`  | Replaced by `PATCH /training-jobs/{id}/status` — simpler API surface |
| `POST /training-jobs/{id}/fail`      | Replaced by `PATCH /training-jobs/{id}/status` — simpler API surface |
| Heartbeat table                      | No heartbeat monitoring needed in manual workflow                    |
| Heartbeat timeout background task    | No remote workers to monitor                                         |
| `SELECT FOR UPDATE SKIP LOCKED`      | No concurrent job claiming — one job per user, manual start          |

---

## 12. Security Review

### Threat Model

| Threat                         | Mitigation                                                              |
| ------------------------------ | ----------------------------------------------------------------------- |
| Malicious dataset upload       | File size limit (1 GB), record count limit (10M), format validation     |
| Model supply chain attack      | HuggingFace Hub provides SHA256 hashes — verify on download (Phase 4.4) |
| Artifact tampering             | MinIO server-side encryption, presigned URLs with expiry                |
| Colab notebook credential leak | Presigned URLs (no long-lived credentials in notebook)                  |
| Unauthorized job access        | Job ownership check — user can only access their own jobs               |

### Dataset Security

- Upload size limit: 1 GB
- Format validation: JSONL with required fields
- Content scanning: Not in MVP (deferred to Phase 4.4)

### Colab Security

- **No long-lived credentials**: Presigned URLs with 24-hour expiry
- **No API keys in notebook**: Use short-lived JWT tokens
- **No MinIO credentials**: Upload via presigned URL only

### Artifact Security

- Artifacts stored in MinIO (not PostgreSQL)
- Presigned URLs for download (time-limited)
- Job ownership enforced on all artifact access

---

## 13. Risks

| ID  | Risk                                                   | Likelihood | Impact | Mitigation                                                                                          |
| --- | ------------------------------------------------------ | ---------- | ------ | --------------------------------------------------------------------------------------------------- |
| R1  | Gemma 3 1B IT target module names differ from expected | Low        | High   | Supported Model Registry (Section 9) manages module names; validate at model load time              |
| R2  | HuggingFace Hub downtime blocks model download         | Low        | High   | Retry with exponential backoff (3 attempts); clear error message on failure                         |
| R3  | Colab T4 availability varies by region/time            | Medium     | Medium | User can retry; no automatic resource allocation needed                                             |
| R4  | Presigned URL expiry before training completes         | Low        | Medium | Set expiry to 24 hours (matches max training duration); document limitation                         |
| R5  | Large datasets cause OOM during tokenization           | Medium     | High   | Stream tokenization (don't load full dataset into memory); OOM guard on batch_size × max_seq_length |
| R6  | Training produces NaN loss                             | Low        | Medium | Detect NaN → FAILED with "Reduce learning_rate" recommendation                                      |
| R7  | Adapter validation fails (corrupt save)                | Low        | High   | Validation catches issue → FAILED; user re-runs (no checkpoint to resume from)                      |
| R8  | `bitsandbytes` compatibility issues on Colab T4        | Low        | High   | Pin `bitsandbytes>=0.43.0`; test on Colab before Phase 4.2 completion                               |
| R9  | Gemma 3 1B IT gated access requires HF token           | Medium     | High   | Document HF token setup in Colab notebook; add `huggingface_hub` login step                         |
| R10 | User abandons Colab notebook (job stuck RUNNING)       | Medium     | Low    | User can cancel via API; no heartbeat needed for MVP                                                |

### Risks Removed from v1.0

| v1.0 Risk                           | Why Removed                                                     |
| ----------------------------------- | --------------------------------------------------------------- |
| R1: Gemma 2B module names           | Replaced by R1 for Gemma 3 1B IT; registry manages this         |
| R4: Colab disconnect detection      | Heartbeat removed (R3); manual workflow, user cancels if needed |
| R7: OOM auto-reduction failure      | Auto-reduction removed (R4); simple FAIL + recommendation       |
| R10: Race condition in job claiming | Job claiming removed (R2); manual user-driven workflow          |

---

## 14. Estimated GPU Usage

### Gemma 3 1B IT QLoRA on T4 — Resource Estimates

| Configuration                      | VRAM Used | VRAM Headroom | Training Time (3 epochs, 1K samples) |
| ---------------------------------- | --------- | ------------- | ------------------------------------ |
| batch_size=2, max_seq_length=512   | ~2.5 GB   | ~13.5 GB      | ~5 minutes                           |
| batch_size=4, max_seq_length=1024  | ~3.5 GB   | ~12.5 GB      | ~10 minutes                          |
| batch_size=8, max_seq_length=2048  | ~5.5 GB   | ~10.5 GB      | ~20 minutes                          |
| batch_size=16, max_seq_length=2048 | ~8.0 GB   | ~8.0 GB       | ~15 minutes                          |
| batch_size=4, max_seq_length=4096  | ~6.0 GB   | ~10.0 GB      | ~25 minutes                          |

### Disk Usage

| Item                            | Size        |
| ------------------------------- | ----------- |
| Model download (fp16)           | ~2.0 GB     |
| Model in memory (4-bit)         | ~0.6 GB     |
| Adapter artifacts               | ~10 MB      |
| Tokenizer files                 | ~5 MB       |
| Dataset (1K samples)            | ~1 MB       |
| **Total disk (no checkpoints)** | **~2.1 GB** |

> **Comparison with v1.0**: v1.0 estimated ~2.5 GB per checkpoint × 3 = ~7.5 GB for checkpoints alone. With `save_strategy="no"` (R5), total disk usage drops from ~9.6 GB to ~2.1 GB — a **78% reduction**.

### Colab Free Tier Limits

| Resource         | Limit    | Our Usage (max config) |
| ---------------- | -------- | ---------------------- |
| GPU RAM          | 16 GB    | ~8 GB (50%)            |
| Disk             | ~70 GB   | ~2.1 GB (3%)           |
| Session duration | 12 hours | Well within limit      |
| RAM              | ~12 GB   | ~4 GB (33%)            |

---

## 15. Recommended Implementation Scope

### Phase 4.2 — Core Training Engine

**Goal**: Implement the QLoRA training runner that can execute training locally (no Colab yet).

| Step   | Task                                                                            | Depends On  |
| ------ | ------------------------------------------------------------------------------- | ----------- |
| 4.2.1  | Create `ModelConfig` dataclass and `SUPPORTED_MODELS` registry                  | —           |
| 4.2.2  | Add model validation to training job creation (reject unsupported models)       | 4.2.1       |
| 4.2.3  | Implement `QLoRATrainingRunner.run()` — full pipeline (download → train → save) | 4.2.1       |
| 4.2.4  | Implement artifact validation (4-file check before COMPLETED)                   | 4.2.3       |
| 4.2.5  | Implement simplified OOM handling (catch → FAILED + actionable message)         | 4.2.3       |
| 4.2.6  | Implement artifact upload to MinIO                                              | 4.2.3       |
| 4.2.7  | Replace `MockTrainingRunner` with `QLoRATrainingRunner` in `TrainingService`    | 4.2.3–4.2.6 |
| 4.2.8  | Add `PATCH /training-jobs/{id}/status` endpoint                                 | 4.2.7       |
| 4.2.9  | Write unit tests for `QLoRATrainingRunner` (mock HuggingFace, mock MinIO)       | 4.2.3–4.2.6 |
| 4.2.10 | Write integration test: full pipeline with small dataset on CPU                 | 4.2.9       |

### Phase 4.3 — Colab Integration

**Goal**: Generate Colab notebooks and enable user-driven remote training.

| Step  | Task                                                                                | Depends On |
| ----- | ----------------------------------------------------------------------------------- | ---------- |
| 4.3.1 | Implement Colab notebook generator (Jupyter notebook template with embedded config) | 4.2        |
| 4.3.2 | Add `GET /training-jobs/{id}/package` endpoint (download generated notebook)        | 4.3.1      |
| 4.3.3 | Add presigned URL generation for dataset download and artifact upload               | 4.3.1      |
| 4.3.4 | Create Colab notebook template with all 11 cells (install → upload → complete)      | 4.3.1      |
| 4.3.5 | Test full end-to-end flow on Colab T4                                               | 4.3.4      |
| 4.3.6 | Add HF token handling for gated models (e.g., Gemma 3 requires approval)            | 4.3.4      |

### Phase 4.4 — Hardening & Polish

**Goal**: Make the training engine production-ready.

| Step  | Task                                                                                          | Depends On  |
| ----- | --------------------------------------------------------------------------------------------- | ----------- |
| 4.4.1 | Add presigned URL artifact upload (remove any remaining MinIO credentials from Colab)         | 4.3         |
| 4.4.2 | Add dataset content validation (empty strings, NaN detection)                                 | 4.2         |
| 4.4.3 | Add model SHA256 verification after download                                                  | 4.2         |
| 4.4.4 | Add training progress WebSocket endpoint (real-time updates)                                  | 4.3         |
| 4.4.5 | Add ChatML dataset format support                                                             | 4.2         |
| 4.4.6 | Add configurable LoRA rank/alpha to TrainingConfig                                            | 4.2         |
| 4.4.7 | Load testing with concurrent job submissions                                                  | 4.3         |
| 4.4.8 | Update all docs (00_project_context.md, 07_training_service.md, 17_architecture_decisions.md) | 4.4.1–4.4.7 |

---

## Appendix A: Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LLM Forge Backend                            │
│                                                                     │
│  ┌──────────────┐   ┌──────────────────┐   ┌────────────────────┐  │
│  │  FastAPI      │   │  TrainingService  │   │  TrainingJobRepo   │  │
│  │  Routes       │──→│  (orchestrator)   │──→│  (PostgreSQL)      │  │
│  └──────────────┘   └────────┬─────────┘   └────────────────────┘  │
│                              │                                      │
│                     ┌────────▼─────────┐                            │
│                     │  QueueService     │                            │
│                     │  (Redis/RQ)      │                            │
│                     └────────┬─────────┘                            │
│                              │ enqueue(job_id)                     │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  QLoRATrainingRunner │
                    │  (replaces Mock)     │
                    │                      │
                    │  1. Download Dataset │──── MinIO
                    │  2. Validate JSONL   │
                    │  3. Load Tokenizer   │──── HuggingFace Hub
                    │  4. QLoRA + PEFT     │──── BitsAndBytes + PEFT
                    │  5. SFTTrainer       │──── Transformers
                    │  6. Save Adapter     │
                    │  7. Validate Artifacts│─── 4-file check
                    │  8. Upload Artifacts │──── MinIO
                    │  9. Update Job       │──── PostgreSQL
                    └──────────────────────┘
```

## Appendix B: Colab Execution Flow (Simplified)

```
┌─────────────────────────────────────────────────────────┐
│                   Colab Notebook                         │
│                                                          │
│  ┌─────────────┐    ┌────────────────────────────────┐ │
│  │  Install     │───→│  Set Job RUNNING               │ │
│  │  Dependencies│    │  PATCH /training-jobs/{id}     │ │
│  └─────────────┘    └──────────────┬─────────────────┘ │
│                                     │                   │
│                         ┌───────────▼──────────────┐   │
│                         │  Download Dataset         │   │
│                         │  (presigned URL → MinIO)  │   │
│                         └───────────┬──────────────┘   │
│                                     │                   │
│                         ┌───────────▼──────────────┐   │
│                         │  Validate JSONL           │   │
│                         └───────────┬──────────────┘   │
│                                     │                   │
│                         ┌───────────▼──────────────┐   │
│                         │  QLoRA Training          │   │
│                         │  (Gemma 3 1B IT + LoRA)  │   │
│                         │                          │   │
│                         │  No heartbeat needed —   │   │
│                         │  manual user-driven      │   │
│                         └───────────┬──────────────┘   │
│                                     │                   │
│                         ┌───────────▼──────────────┐   │
│                         │  Validate Artifacts       │   │
│                         │  (4-file check)           │   │
│                         └───────────┬──────────────┘   │
│                                     │                   │
│                         ┌───────────▼──────────────┐   │
│                         │  Upload Adapter           │   │
│                         │  (presigned URL → MinIO)  │   │
│                         └───────────┬──────────────┘   │
│                                     │                   │
│                         ┌───────────▼──────────────┐   │
│                         │  Set Job COMPLETED        │   │
│                         │  PATCH /training-jobs/{id}│   │
│                         └──────────────────────────┘   │
│                                                         │
│  On any error:                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Set Job FAILED                                    │  │
│  │  PATCH /training-jobs/{id}                         │  │
│  │  { "status": "failed", "error_message": "..." }   │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Appendix C: VRAM Budget Visualization

```
T4 GPU: 16 GB VRAM
├── Model weights (4-bit):     0.6 GB  ██
├── Quantization constants:    0.15 GB ▏
├── LoRA adapters (fp16):      0.02 GB ▏
├── Activations (grad_ckpt):   2.5 GB  ████████
├── Optimizer (8-bit paged):   0.5 GB  ███
├── CUDA context + overhead:   1.0 GB  ███
├── ─────────────────────────────────────
├── TOTAL:                     ~4.8 GB
└── HEADROOM:                  ~11.2 GB  ████████████████████████████████████████
```

---

\_End of Phase 4.1 Planning Report (v2.0 — Revised). No code was generated. This document serves as the blueprint for Phase 4.2 (core engine), Phase 4.3 (Colab integration), and Phase 4.4 (hardening).
