# Real Training Validation Plan

## Purpose

This document defines the exact configuration, dataset, and success criteria for the **first real QLoRA fine-tuning run** of `google/gemma-3-1b-it` on Google Colab T4 (16 GB VRAM).

> **Scope**: This is a validation plan only. It does NOT execute training, does NOT create Colab notebooks, and does NOT implement new features. It documents what the first real run should look like so a developer can execute it manually.

---

# 1. Target Environment

| Property | Value |
|---|---|
| Platform | Google Colab (Free Tier) |
| GPU | NVIDIA T4 (16 GB VRAM) |
| Python | 3.10+ |
| CUDA | 12.x (Colab default) |

---

# 2. Model

| Property | Value |
|---|---|
| Base Model | `google/gemma-3-1b-it` |
| Parameter Count | ~1 B |
| Quantization | 4-bit NF4 (via BitsAndBytes) |
| Compute Dtype | `torch.float16` |
| Double Quantization | Enabled |

---

# 3. QLoRA Configuration

| Hyperparameter | Value | Source |
|---|---|---|
| `lora_r` | 16 | `qlora_training_runner.py` default |
| `lora_alpha` | 32 | `qlora_training_runner.py` default |
| `lora_dropout` | 0.05 | `qlora_training_runner.py` default |
| `bias` | `"none"` | `docs/07_training_service.md` |
| Target Modules | `["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]` | `model_registry.py` |

---

# 4. Training Configuration

| Hyperparameter | Value | Source |
|---|---|---|
| `epochs` | 3 | `qlora_training_runner.py` default |
| `batch_size` | 4 | `model_registry.py` default |
| `learning_rate` | 2e-4 | `qlora_training_runner.py` default |
| `gradient_accumulation_steps` | 4 | `docs/07_training_service.md` |
| `max_seq_length` | 2048 | `model_registry.py` recommended |
| `logging_steps` | 10 | `docs/07_training_service.md` |
| `seed` | 42 | Standard reproducibility |

---

# 5. Dataset Requirements

## 5.1 Format

Alpaca-format JSON with **required** keys:

- `instruction` (string) — the task description
- `output` (string) — the expected response

And **optional** key:

- `input` (string) — additional context (defaults to `""`)

This matches `DatasetLoader.REQUIRED_KEYS = {"instruction", "output"}` and `DatasetLoader.OPTIONAL_KEYS = {"input"}`.

## 5.2 Size

| Property | Value | Rationale |
|---|---|---|
| Minimum rows | 50 | Enough to verify pipeline end-to-end |
| Recommended rows | 200–500 | Sufficient for meaningful loss convergence on 1B model |
| Maximum rows | 2 000 | Fits in T4 memory at seq_length=2048 with batch_size=4 |

## 5.3 Example Record

```json
{
  "instruction": "Classify the sentiment of the following review.",
  "input": "The product exceeded my expectations!",
  "output": "Positive"
}
```

---

# 6. Expected VRAM Usage

| Component | Estimated VRAM |
|---|---|
| Base model (4-bit NF4) | ~0.7 GB |
| LoRA adapters (r=16) | ~0.05 GB |
| Optimizer states (8-bit AdamW) | ~0.3 GB |
| Activations (batch=4, seq=2048) | ~4–6 GB |
| Gradients + overhead | ~2–3 GB |
| **Total estimated** | **~7–10 GB** |

> T4 has 16 GB VRAM. The configuration above should fit comfortably with ~6–9 GB headroom.

---

# 7. Expected Runtime

| Dataset Size | Estimated Time (T4) |
|---|---|
| 50 rows, 3 epochs | ~2–5 min |
| 200 rows, 3 epochs | ~8–15 min |
| 500 rows, 3 epochs | ~20–40 min |
| 2 000 rows, 3 epochs | ~1.5–3 hr |

> Estimates assume `max_seq_length=2048` and `gradient_accumulation_steps=4`. Actual time depends on average sequence length.

---

# 8. Expected Artifacts

After a successful run, the following artifacts should be produced:

```
artifacts/
├── adapter/
│   ├── adapter_config.json      # LoRA adapter configuration
│   ├── adapter_model.safetensors # LoRA weights
│   └── tokenizer.json           # Tokenizer files
├── logs/
│   └── training_log.jsonl       # Step-by-step loss log
└── metadata.json                # 18-key metadata (see §9)
```

---

# 9. Metadata Validation

The `metadata.json` must contain all **18 required keys** as defined in `artifact_validator.py`:

| # | Key | Expected Value |
|---|---|---|
| 1 | `job_id` | UUID from training job |
| 2 | `base_model` | `"google/gemma-3-1b-it"` |
| 3 | `training_type` | `"qlora"` |
| 4 | `dataset_rows` | Integer (e.g. 200) |
| 5 | `epochs` | `3` |
| 6 | `batch_size` | `4` |
| 7 | `learning_rate` | `0.0002` |
| 8 | `lora_r` | `16` |
| 9 | `lora_alpha` | `32` |
| 10 | `lora_dropout` | `0.05` |
| 11 | `seed` | `42` |
| 12 | `max_seq_length` | `2048` |
| 13 | `quantization` | `"4-bit-nf4"` |
| 14 | `torch_version` | e.g. `"2.4.0"` |
| 15 | `transformers_version` | e.g. `"4.50.0"` (≥4.50.0 required for Gemma 3) |
| 16 | `peft_version` | e.g. `"0.13.0"` |
| 17 | `bitsandbytes_version` | e.g. `"0.44.0"` |
| 18 | `training_duration` | Float (seconds) or `null` |

---

# 10. Success Criteria

A training run is considered **successful** if ALL of the following are met:

| # | Criterion | Verification |
|---|---|---|
| 1 | Training completes without OOM error | No `torch.cuda.OutOfMemoryError` raised |
| 2 | Training loss decreases over epochs | Final epoch loss < first epoch loss |
| 3 | Adapter weights file exists | `adapter_model.safetensors` is non-empty |
| 4 | Adapter config is valid JSON | `adapter_config.json` parses and contains `r`, `lora_alpha`, `target_modules` |
| 5 | Metadata contains all 18 required keys | `ArtifactValidator.validate_training_metadata()` returns no errors |
| 6 | Metadata lora keys match config | `lora_r=16`, `lora_alpha=32`, `lora_dropout=0.05` |
| 7 | Tokenizer files are saved | `tokenizer.json` and related files exist |
| 8 | Training log has entries | `training_log.jsonl` has ≥1 line per `logging_steps` interval |

---

# 11. Failure Criteria

A training run is considered **failed** if ANY of the following occur:

| # | Criterion | Action |
|---|---|---|
| 1 | OOM error | Reduce `batch_size` to 2, reduce `max_seq_length` to 1024, retry |
| 2 | Loss is NaN or Inf | Reduce `learning_rate` to 1e-4, retry |
| 3 | Loss does not decrease | Check dataset quality; increase `epochs` or `learning_rate` |
| 4 | Adapter file missing or empty | Check disk space; verify `save_strategy` and output directory permissions |
| 5 | Metadata validation fails | Check `_build_training_metadata()` output; add missing keys |

---

# 12. OOM Recovery Procedure

If the T4 runs out of memory, apply these steps in order:

1. **Reduce batch size**: `batch_size=4` → `batch_size=2`
2. **Reduce sequence length**: `max_seq_length=2048` → `max_seq_length=1024`
3. **Increase gradient accumulation**: `gradient_accumulation_steps=4` → `gradient_accumulation_steps=8` (to maintain effective batch size)
4. **Disable double quantization**: `bnb_4bit_use_double_quant=False` (minor VRAM savings)

> The OOM error message in `qlora_training_runner.py` already suggests: `"CUDA Out Of Memory. Try: - batch_size=2 - max_seq_length=1024"`

---

# 13. Post-Run Validation Checklist

After the training run completes:

- [ ] Verify `adapter_model.safetensors` file size > 0 bytes
- [ ] Load adapter with `PeftModel.from_pretrained()` — should not raise
- [ ] Run a single inference with the merged model — should produce coherent output
- [ ] Validate `metadata.json` with `ArtifactValidator.validate_training_metadata()`
- [ ] Validate `metadata.json` with `ArtifactValidator.validate_training_artifacts()`
- [ ] Compare training loss curve: should show monotonic decrease (with noise)
- [ ] Record actual VRAM usage and runtime for future reference
- [ ] Update this document with actual observed values

---

# 14. Stage 0 Smoke Test

Before committing to a full training run (§4–§5), execute a **Stage 0 smoke test** to validate the entire pipeline end-to-end with minimal resources.

## 14.1 Purpose

The smoke test verifies that every component of the QLoRA pipeline works correctly on the target hardware before investing time in a full training run. It catches configuration errors, dependency issues, and hardware incompatibilities early.

## 14.2 Configuration

| Hyperparameter | Value | Rationale |
|---|---|---|
| `epochs` | 1 | Minimum — just verify pipeline runs |
| `batch_size` | 2 | Conservative for T4 safety |
| `learning_rate` | 2e-4 | Same as full run — no need to change |
| `max_seq_length` | 512 | Reduced from 2048 — minimizes memory/time |
| `gradient_accumulation_steps` | 4 | Same as full run |
| `logging_steps` | 1 | Log every step for visibility |
| Dataset size | 50 examples | Minimum viable dataset |
| `save_strategy` | `"no"` | No checkpoint saving — smoke test only |

## 14.3 Expected Results

| Metric | Expected Value |
|---|---|
| Peak VRAM | ~2–3 GB |
| Runtime | ~1–2 minutes |
| Training steps | ~25 (50 examples ÷ batch_size 2 ÷ 1 epoch) |
| Loss behavior | Should not be NaN/Inf; may not converge in 1 epoch |

## 14.4 Success Criteria

| # | Criterion | Verification |
|---|---|---|
| 1 | No import errors | All packages load without error |
| 2 | Model loads with 4-bit quantization | `BitsAndBytesConfig` applied, no dtype errors |
| 3 | LoRA adapter attaches correctly | `print(model.print_trainable_parameters())` shows ~5.4M trainable |
| 4 | Training completes without OOM | No `torch.cuda.OutOfMemoryError` |
| 5 | Loss is finite | No NaN or Inf values in loss |
| 6 | Adapter saves successfully | `adapter_model.safetensors` created and non-empty |

## 14.5 Failure Response

| Failure | Action |
|---|---|
| Import error | `pip install <missing_package>` |
| Dtype error (bfloat16) | Verify `torch_dtype=float16` in config |
| OOM at batch_size=2 | Reduce `max_seq_length` to 256 |
| NaN loss | Reduce `learning_rate` to 1e-4 |

---

# 15. Dependencies to Install on Colab

```bash
pip install torch transformers peft trl bitsandbytes accelerate datasets safetensors
```

> Version pinning is not required for the validation run, but record the installed versions for metadata.

---

# 15. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| OOM on T4 | Low (1B model fits easily) | Medium | Recovery procedure in §12 |
| Dataset format mismatch | Low (validated by `DatasetLoader`) | Low | Use `validate_alpaca_schema()` before training |
| NaN loss | Low (lr=2e-4 is conservative) | Medium | Reduce learning rate |
| Colab timeout (12 hr) | Very Low (1B model, small dataset) | Low | Use ≤2000 rows |
| Adapter merge failure | Low | Medium | Test with `PeftModel.from_pretrained()` |

---

# 16. Relationship to Phase 4.3

This validation plan is a **prerequisite** for Phase 4.3 (Colab Integration). Phase 4.3 will:

1. Create a Colab notebook that automates the steps described here
2. Add Colab-specific setup cells (auth, drive mount, pip installs)
3. Add result-upload logic (push artifacts to MinIO or Google Drive)
4. Add progress-callback integration (report step-level metrics back to the API)

This plan does NOT implement any of the above. It only documents what the first manual run should look like.
