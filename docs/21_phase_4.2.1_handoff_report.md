# Phase 4.2.1 — Hardening Handoff Report

> **Date**: 2025-07-11  
> **Scope**: Targeted fixes to training-service source code and tests before Phase 4.3  
> **Status**: ✅ Complete — all 4 fixes applied, 135/135 tests passing

---

## 1. Changes Applied

### Fix 1 — Dataset Schema: `input` field → optional

| File | Change |
|------|--------|
| `backend/app/training/dataset_loader.py` | `REQUIRED_KEYS` changed from `{"instruction","input","output"}` → `{"instruction","output"}` |
| `backend/app/training/dataset_loader.py` | Added `OPTIONAL_KEYS: set[str] = {"input"}` |
| `backend/app/training/dataset_loader.py` | Updated `validate_alpaca_schema()` docstring |
| `backend/tests/test_training_module.py` | `test_validate_alpaca_schema_missing_input_not_allowed` → renamed to `test_validate_alpaca_schema_missing_input_allowed`, now asserts `errors == []` |
| `backend/tests/test_training_module.py` | `test_validate_alpaca_schema_missing_keys` → record uses `{"instruction": "A"}` (missing `output`), asserts `"output" in errors[0]` |
| `backend/tests/test_training_module.py` | NEW `test_validate_alpaca_schema_optional_keys_constant` — asserts `OPTIONAL_KEYS == {"input"}` |
| `backend/tests/test_training_module.py` | NEW `test_validate_alpaca_schema_required_keys_constant` — asserts `REQUIRED_KEYS == {"instruction", "output"}` |

**Rationale**: Alpaca-format datasets commonly omit the `input` field when the instruction is self-contained. Rejecting records without `input` was overly strict.

---

### Fix 2 — Metadata: Add LoRA hyperparameter keys to required set

| File | Change |
|------|--------|
| `backend/app/training/artifact_validator.py` | Added `"lora_r"`, `"lora_alpha"`, `"lora_dropout"` to `REQUIRED_METADATA_KEYS` (15 → 18 keys) |
| `backend/app/workers/qlora_training_runner.py` | Added `"lora_r"`, `"lora_alpha"`, `"lora_dropout"` to `_build_training_metadata()` output |
| `backend/tests/test_training_module.py` | `test_validate_training_metadata_all_15_keys_required` → renamed to `test_validate_training_metadata_all_18_keys_required`, asserts `== 18` |
| `backend/tests/test_training_module.py` | `test_validate_training_metadata_single_key_missing` — added lora keys to metadata dict |
| `backend/tests/test_training_module.py` | `test_metadata_contains_all_required_keys` — docstring updated (15 → 18) |
| `backend/tests/test_training_module.py` | `test_required_metadata_keys_count` — asserts `== 18` |
| `backend/tests/test_training_module.py` | `test_validate_training_metadata_valid` — added lora keys to metadata dict |
| `backend/tests/test_training_module.py` | `test_metadata_builder_and_validator_pipeline` — added lora keys to metadata dict |
| `backend/tests/test_training_module.py` | NEW `test_metadata_contains_lora_keys` — tests lora keys with custom values |
| `backend/tests/test_training_module.py` | NEW `test_metadata_lora_defaults` — tests default values (16, 32, 0.05) |

**Rationale**: Training metadata must capture the LoRA adapter configuration for reproducibility. Without `lora_r`, `lora_alpha`, and `lora_dropout`, a trained adapter cannot be meaningfully compared or reproduced.

---

### Fix 3 — Model Registry defaults

| File | Change |
|------|--------|
| *(none)* | Already correct — `recommended_seq_length: int = 2048` was present |

**Rationale**: Verified `ModelRegistry.recommended_seq_length` defaults to 2048, matching the validation plan. No code change needed.

---

### Fix 4 — Real Training Validation Plan document

| File | Change |
|------|--------|
| `docs/20_real_training_validation_plan.md` | Created — documents dataset size, training config, expected VRAM, expected runtime, expected artifacts, success/failure criteria, OOM recovery, 18-key metadata table, post-run validation checklist |

**Rationale**: Before running real training on Colab T4, the team needs a concrete validation plan with exact expected values and pass/fail criteria.

---

## 2. Test Results

```
============================= 135 passed in 0.86s =============================
```

- **Total tests**: 135
- **Passed**: 135
- **Failed**: 0
- **Duration**: 0.86s
- **Test file**: `backend/tests/test_training_module.py`

### New tests added in this phase (6):

| Test | Purpose |
|------|---------|
| `test_validate_alpaca_schema_optional_keys_constant` | Verifies `OPTIONAL_KEYS == {"input"}` |
| `test_validate_alpaca_schema_required_keys_constant` | Verifies `REQUIRED_KEYS == {"instruction", "output"}` |
| `test_validate_alpaca_schema_missing_input_allowed` | Records without `input` pass validation |
| `test_validate_training_metadata_all_18_keys_required` | 18 keys now required (was 15) |
| `test_metadata_contains_lora_keys` | Custom lora values appear in metadata |
| `test_metadata_lora_defaults` | Default lora values (16, 32, 0.05) |

---

## 3. Source Modules Status

| Module | Path | Status |
|--------|------|--------|
| DatasetLoader | `backend/app/training/dataset_loader.py` | ✅ Modified (Fix 1) |
| ArtifactValidator | `backend/app/training/artifact_validator.py` | ✅ Modified (Fix 2) |
| QLoRATrainingRunner | `backend/app/workers/qlora_training_runner.py` | ✅ Modified (Fix 2) |
| ModelRegistry | `backend/app/training/model_registry.py` | ✅ No change needed (Fix 3) |
| DatasetNormalizer | `backend/app/training/dataset_normalizer.py` | ✅ Unchanged |
| AlpacaFormatter | `backend/app/training/alpaca_formatter.py` | ✅ Unchanged |
| QLoRAConfigFactory | `backend/app/training/qlora_config_factory.py` | ✅ Unchanged |
| PEFTConfigFactory | `backend/app/training/peft_config_factory.py` | ✅ Unchanged |
| TrainingArgumentsFactory | `backend/app/training/training_arguments_factory.py` | ✅ Unchanged |
| OOMDetector | `backend/app/training/oom_detector.py` | ✅ Unchanged |
| Training `__init__` | `backend/app/training/__init__.py` | ✅ Unchanged |

---

## 4. Required Metadata Keys (18)

| # | Key | Example Value |
|---|-----|---------------|
| 1 | `job_id` | `"abc-123"` |
| 2 | `base_model` | `"google/gemma-3-1b-it"` |
| 3 | `training_type` | `"qlora"` |
| 4 | `dataset_rows` | `100` |
| 5 | `epochs` | `3` |
| 6 | `batch_size` | `4` |
| 7 | `learning_rate` | `2e-4` |
| 8 | **`lora_r`** 🆕 | `16` |
| 9 | **`lora_alpha`** 🆕 | `32` |
| 10 | **`lora_dropout`** 🆕 | `0.05` |
| 11 | `seed` | `42` |
| 12 | `torch_version` | `"2.4.0"` |
| 13 | `transformers_version` | `"4.45.0"` |
| 14 | `peft_version` | `"0.13.0"` |
| 15 | `bitsandbytes_version` | `"0.44.0"` |
| 16 | `python_version` | `"3.14.2"` |
| 17 | `platform` | `"Linux"` |
| 18 | `training_duration` | `120.5` |

---

## 5. Known Risks & Open Items

| Risk | Severity | Mitigation |
|------|----------|------------|
| ML libraries are mocked in tests — real training not yet validated | High | `docs/20_real_training_validation_plan.md` defines Colab T4 validation steps |
| `DatasetLoader` only validates Alpaca format — no ShareGPT/ChatML support | Low | Out of scope for Phase 4.2; track for future |
| `ArtifactValidator` does not validate value types/ranges for metadata | Low | Key presence check is sufficient for Phase 4.2 |
| RQ worker not integration-tested with real Redis | Medium | Unit tests cover all code paths; integration test deferred to Phase 4.3 |

---

## 6. Phase 4.3 Readiness Checklist

- [x] All 4 hardening fixes applied
- [x] All 135 tests passing
- [x] No regressions in existing tests
- [x] New constants (`OPTIONAL_KEYS`, 3 lora metadata keys) tested
- [x] Real training validation plan documented
- [x] Handoff report generated

**Phase 4.2.1 is complete. The codebase is ready for Phase 4.3.**
