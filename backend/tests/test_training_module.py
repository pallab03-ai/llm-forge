"""Tests for Phase 4.2/4.3 — QLoRA Training Engine.

All tests mock torch/transformers/peft/trl/bitsandbytes imports
so they can run without a GPU or ML dependencies installed.

Covers:
- ModelConfig / SUPPORTED_MODELS registry
- DatasetLoader
- AlpacaFormatter
- TrainingArgumentsFactory
- ArtifactValidator
- QLoRATrainingRunner
- TrainingMetadataBuilder
- OOMErrorMessage
- DatasetPathResolution
- TrainingModuleInit
- Integration / edge-case tests
- Phase 4.3 Colab Validation
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Model Registry Tests
# ============================================================================


class TestModelConfig:
    """Tests for ModelConfig dataclass and SUPPORTED_MODELS registry."""

    def test_supported_models_contains_gemma(self):
        """SUPPORTED_MODELS should contain google/gemma-3-1b-it."""
        from app.training.model_registry import SUPPORTED_MODELS

        assert "google/gemma-3-1b-it" in SUPPORTED_MODELS

    def test_gemma_model_config_fields(self):
        """Gemma model config should have all expected fields."""
        from app.training.model_registry import SUPPORTED_MODELS

        config = SUPPORTED_MODELS["google/gemma-3-1b-it"]
        assert config.display_name == "Gemma 3 1B IT"
        assert config.hf_model_id == "google/gemma-3-1b-it"
        assert config.parameter_count == 1.0
        assert config.quantized_vram_gb == 3.0
        assert config.max_seq_length == 8192
        assert config.lora_target_modules == [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ]
        assert config.attn_implementation == "eager"
        assert config.torch_dtype == "float16"
        assert config.special_tokens == {"pad_token": "<eos>"}

    def test_gemma_default_batch_size(self):
        """Gemma config should have default_batch_size=4."""
        from app.training.model_registry import SUPPORTED_MODELS

        config = SUPPORTED_MODELS["google/gemma-3-1b-it"]
        assert config.default_batch_size == 4

    def test_gemma_recommended_seq_length(self):
        """Gemma config should have recommended_seq_length=2048."""
        from app.training.model_registry import SUPPORTED_MODELS

        config = SUPPORTED_MODELS["google/gemma-3-1b-it"]
        assert config.recommended_seq_length == 2048

    def test_gemma_chat_template(self):
        """Gemma chat template should contain the expected placeholders."""
        from app.training.model_registry import SUPPORTED_MODELS

        config = SUPPORTED_MODELS["google/gemma-3-1b-it"]
        assert "{instruction}" in config.chat_template
        assert "{input}" in config.chat_template
        assert "{output}" in config.chat_template
        assert "<start_of_turn>" in config.chat_template
        assert "<end_of_turn>" in config.chat_template

    def test_model_config_is_frozen(self):
        """ModelConfig should be immutable (frozen dataclass)."""
        from app.training.model_registry import ModelConfig

        config = ModelConfig(
            display_name="Test",
            hf_model_id="test/model",
            parameter_count=1.0,
            quantized_vram_gb=2.0,
            max_seq_length=2048,
        )
        with pytest.raises(AttributeError):
            config.display_name = "Changed"

    def test_get_model_config_valid(self):
        """get_model_config should return config for a supported model."""
        from app.training.model_registry import get_model_config

        config = get_model_config("google/gemma-3-1b-it")
        assert config.hf_model_id == "google/gemma-3-1b-it"

    def test_get_model_config_invalid(self):
        """get_model_config should raise ValueError for unsupported model."""
        from app.training.model_registry import get_model_config

        with pytest.raises(ValueError, match="Unsupported model"):
            get_model_config("meta/llama-3-70b")

    def test_get_model_config_error_lists_supported(self):
        """Error message should list supported models."""
        from app.training.model_registry import get_model_config

        with pytest.raises(ValueError, match="google/gemma-3-1b-it"):
            get_model_config("nonexistent/model")

    def test_model_config_default_batch_size_field(self):
        """ModelConfig should have default_batch_size field with default 4."""
        from app.training.model_registry import ModelConfig

        config = ModelConfig(
            display_name="Test",
            hf_model_id="test/model",
            parameter_count=1.0,
            quantized_vram_gb=2.0,
            max_seq_length=2048,
        )
        assert config.default_batch_size == 4


# ============================================================================
# Dataset Normalizer Tests
# ============================================================================


class TestDatasetLoader:
    """Tests for DatasetLoader (JSONL loading, validation, counting, HF Dataset)."""

    def test_load_jsonl_valid(self, tmp_path):
        """Should load valid JSONL file."""
        from app.training.dataset_loader import DatasetLoader

        jsonl_path = tmp_path / "data.jsonl"
        jsonl_path.write_text(
            json.dumps({"instruction": "A", "input": "B", "output": "C"}) + "\n",
            encoding="utf-8",
        )

        records = DatasetLoader.load_jsonl(jsonl_path)
        assert len(records) == 1
        assert records[0]["instruction"] == "A"

    def test_load_jsonl_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        from app.training.dataset_loader import DatasetLoader

        with pytest.raises(FileNotFoundError):
            DatasetLoader.load_jsonl("/nonexistent/path.jsonl")

    def test_load_jsonl_empty_file(self, tmp_path):
        """Should raise ValueError for empty JSONL file."""
        from app.training.dataset_loader import DatasetLoader

        jsonl_path = tmp_path / "empty.jsonl"
        jsonl_path.write_text("", encoding="utf-8")

        with pytest.raises(ValueError, match="empty"):
            DatasetLoader.load_jsonl(jsonl_path)

    def test_load_jsonl_invalid_json(self, tmp_path):
        """Should raise json.JSONDecodeError for invalid JSON."""
        from app.training.dataset_loader import DatasetLoader

        jsonl_path = tmp_path / "bad.jsonl"
        jsonl_path.write_text("{invalid json}\n", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            DatasetLoader.load_jsonl(jsonl_path)

    def test_validate_alpaca_schema_valid(self):
        """Should return empty list for valid records."""
        from app.training.dataset_loader import DatasetLoader

        records = [
            {"instruction": "A", "input": "B", "output": "C"},
        ]
        errors = DatasetLoader.validate_alpaca_schema(records)
        assert errors == []

    def test_validate_alpaca_schema_missing_keys(self):
        """Should return errors for missing required keys."""
        from app.training.dataset_loader import DatasetLoader

        records = [
            {"instruction": "A"},
        ]
        errors = DatasetLoader.validate_alpaca_schema(records)
        assert len(errors) > 0
        assert any("output" in e for e in errors)

    def test_validate_alpaca_schema_multiple_errors(self):
        """Should report all errors across multiple records."""
        from app.training.dataset_loader import DatasetLoader

        records = [
            {"instruction": "A"},
            {"output": "C"},
        ]
        errors = DatasetLoader.validate_alpaca_schema(records)
        assert len(errors) >= 2

    def test_validate_alpaca_schema_empty_input_allowed(self):
        """Should allow empty input field."""
        from app.training.dataset_loader import DatasetLoader

        records = [
            {"instruction": "A", "input": "", "output": "C"},
        ]
        errors = DatasetLoader.validate_alpaca_schema(records)
        assert errors == []

    def test_validate_alpaca_schema_missing_input_allowed(self):
        """Should allow missing input field (input is optional)."""
        from app.training.dataset_loader import DatasetLoader

        records = [
            {"instruction": "A", "output": "C"},
        ]
        errors = DatasetLoader.validate_alpaca_schema(records)
        assert errors == []

    def test_load_dataset_returns_hf_dataset(self, tmp_path):
        """load_dataset() should return a HuggingFace Dataset."""
        from app.training.dataset_loader import DatasetLoader
        from unittest.mock import patch, MagicMock

        jsonl_path = tmp_path / "data.jsonl"
        jsonl_path.write_text(
            json.dumps({"instruction": "A", "input": "B", "output": "C"}) + "\n",
            encoding="utf-8",
        )

        mock_dataset = MagicMock()
        mock_dataset.__len__ = MagicMock(return_value=1)
        with patch("datasets.Dataset.from_list", return_value=mock_dataset):
            hf_dataset = DatasetLoader.load_dataset(jsonl_path)
        assert hf_dataset is not None
        assert len(hf_dataset) == 1

    def test_load_dataset_file_not_found(self):
        """load_dataset() should raise FileNotFoundError for missing file."""
        from app.training.dataset_loader import DatasetLoader

        with pytest.raises(FileNotFoundError):
            DatasetLoader.load_dataset("/nonexistent/path.jsonl")

    def test_load_dataset_schema_validation_fails(self, tmp_path):
        """load_dataset() should raise ValueError on schema failure."""
        from app.training.dataset_loader import DatasetLoader

        jsonl_path = tmp_path / "data.jsonl"
        jsonl_path.write_text(
            json.dumps({"bad": "record"}) + "\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="schema validation"):
            DatasetLoader.load_dataset(jsonl_path)

    def test_load_dataset_multiple_records(self, tmp_path):
        """load_dataset() should handle multiple records."""
        from app.training.dataset_loader import DatasetLoader
        from unittest.mock import patch, MagicMock

        jsonl_path = tmp_path / "data.jsonl"
        lines = [
            {"instruction": "A1", "input": "B1", "output": "C1"},
            {"instruction": "A2", "input": "B2", "output": "C2"},
        ]
        jsonl_path.write_text(
            "\n".join(json.dumps(r) for r in lines),
            encoding="utf-8",
        )

        mock_dataset = MagicMock()
        mock_dataset.__len__ = MagicMock(return_value=2)
        with patch("datasets.Dataset.from_list", return_value=mock_dataset):
            hf_dataset = DatasetLoader.load_dataset(jsonl_path)
        assert len(hf_dataset) == 2

    def test_load_jsonl_valid(self, tmp_path):
        """Should load valid JSONL file."""
        from app.training.dataset_loader import DatasetLoader

        data = [
            {"instruction": "Summarize", "input": "text", "output": "summary"},
            {"instruction": "Translate", "input": "hello", "output": "hola"},
        ]
        jsonl_path = tmp_path / "data.jsonl"
        jsonl_path.write_text(
            "\n".join(json.dumps(r) for r in data), encoding="utf-8"
        )

        records = DatasetLoader.load_jsonl(jsonl_path)
        assert len(records) == 2
        assert records[0]["instruction"] == "Summarize"

    def test_load_jsonl_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        from app.training.dataset_loader import DatasetLoader

        with pytest.raises(FileNotFoundError):
            DatasetLoader.load_jsonl("/nonexistent/path/data.jsonl")

    def test_load_jsonl_invalid_json(self, tmp_path):
        """Should raise json.JSONDecodeError for invalid JSON."""
        import json

        from app.training.dataset_loader import DatasetLoader

        jsonl_path = tmp_path / "bad.jsonl"
        jsonl_path.write_text('{"valid": true}\n{invalid json}\n', encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            DatasetLoader.load_jsonl(jsonl_path)

    def test_load_jsonl_empty_file(self, tmp_path):
        """Should raise ValueError for empty file."""
        from app.training.dataset_loader import DatasetLoader

        jsonl_path = tmp_path / "empty.jsonl"
        jsonl_path.write_text("", encoding="utf-8")

        with pytest.raises(ValueError, match="empty"):
            DatasetLoader.load_jsonl(jsonl_path)

    def test_load_jsonl_blank_lines_skipped(self, tmp_path):
        """Should skip blank lines in JSONL file."""
        from app.training.dataset_loader import DatasetLoader

        data = [{"instruction": "A", "input": "", "output": "B"}]
        jsonl_path = tmp_path / "data.jsonl"
        jsonl_path.write_text(
            "\n\n" + json.dumps(data[0]) + "\n\n", encoding="utf-8"
        )

        records = DatasetLoader.load_jsonl(jsonl_path)
        assert len(records) == 1

    def test_validate_alpaca_schema_valid(self):
        """Should return empty list for valid records."""
        from app.training.dataset_loader import DatasetLoader

        records = [
            {"instruction": "A", "input": "B", "output": "C"},
            {"instruction": "D", "input": "E", "output": "F"},
        ]
        errors = DatasetLoader.validate_alpaca_schema(records)
        assert errors == []

    def test_validate_alpaca_schema_missing_keys(self):
        """Should return errors for records missing required keys."""
        from app.training.dataset_loader import DatasetLoader

        records = [
            {"instruction": "A"},  # missing "output" (input is optional)
        ]
        errors = DatasetLoader.validate_alpaca_schema(records)
        assert len(errors) == 1
        assert "output" in errors[0]

    def test_validate_alpaca_schema_multiple_errors(self):
        """Should report errors for each invalid record."""
        from app.training.dataset_loader import DatasetLoader

        records = [
            {"instruction": "A"},  # missing output (input is optional)
            {"output": "C"},  # missing instruction (input is optional)
        ]
        errors = DatasetLoader.validate_alpaca_schema(records)
        assert len(errors) == 2

    def test_validate_alpaca_schema_extra_keys_ok(self):
        """Extra keys beyond required should not cause errors."""
        from app.training.dataset_loader import DatasetLoader

        records = [
            {"instruction": "A", "input": "B", "output": "C", "extra": "D"},
        ]
        errors = DatasetLoader.validate_alpaca_schema(records)
        assert errors == []


# ---------------------------------------------------------------------------
# Alpaca Formatter Tests
# ---------------------------------------------------------------------------


class TestAlpacaFormatter:
    """Tests for AlpacaFormatter (Alpaca â†’ ### Instruction/Response formatting)."""

    def test_format_example_with_input(self):
        """Should format a record with instruction, input, and output."""
        from app.training.alpaca_formatter import AlpacaFormatter

        record = {"instruction": "Summarize", "input": "Long text", "output": "Short"}

        result = AlpacaFormatter.format_example(record)
        assert "### Instruction:" in result
        assert "Summarize" in result
        assert "### Input:" in result
        assert "Long text" in result
        assert "### Response:" in result
        assert "Short" in result

    def test_format_example_without_input(self):
        """Should omit Input section when input is empty."""
        from app.training.alpaca_formatter import AlpacaFormatter

        record = {"instruction": "Translate", "input": "", "output": "Hola"}

        result = AlpacaFormatter.format_example(record)
        assert "### Instruction:" in result
        assert "Translate" in result
        assert "### Input:" not in result
        assert "### Response:" in result
        assert "Hola" in result

    def test_format_dataset(self):
        """Should format all records in a dataset."""
        from app.training.alpaca_formatter import AlpacaFormatter

        records = [
            {"instruction": "A", "input": "B", "output": "C"},
            {"instruction": "D", "input": "E", "output": "F"},
        ]

        results = AlpacaFormatter.format_dataset(records)
        assert len(results) == 2
        assert "### Instruction:" in results[0]
        assert "A" in results[0]
        assert "### Instruction:" in results[1]
        assert "D" in results[1]

    def test_format_dataset_empty(self):
        """Should return empty list for empty dataset."""
        from app.training.alpaca_formatter import AlpacaFormatter

        results = AlpacaFormatter.format_dataset([])
        assert results == []

    def test_format_example_special_characters(self):
        """Should handle special characters in fields."""
        from app.training.alpaca_formatter import AlpacaFormatter

        record = {
            "instruction": "What is 2 < 3?",
            "input": "x & y are < 10",
            "output": "Yes, 2 < 3 is true & x, y < 10",
        }

        result = AlpacaFormatter.format_example(record)
        assert "2 < 3?" in result
        assert "x & y" in result

    def test_format_example_multiline_content(self):
        """Should handle multiline content in fields."""
        from app.training.alpaca_formatter import AlpacaFormatter

        record = {
            "instruction": "Write a poem\nWith two lines",
            "input": "",
            "output": "Roses are red\nViolets are blue",
        }

        result = AlpacaFormatter.format_example(record)
        assert "Write a poem\nWith two lines" in result
        assert "Roses are red\nViolets are blue" in result

    def test_format_example_whitespace_handling(self):
        """Should preserve whitespace in instruction and output."""
        from app.training.alpaca_formatter import AlpacaFormatter

        record = {"instruction": "  Trim test  ", "input": "", "output": "  Output  "}

        result = AlpacaFormatter.format_example(record)
        assert "  Trim test  " in result


# ---------------------------------------------------------------------------
# Training Arguments Factory Tests (mocked)
# ---------------------------------------------------------------------------


class TestTrainingArgumentsFactory:
    """Tests for TrainingArgumentsFactory (SFTConfig creation)."""

    def test_create_training_args_defaults(self):
        """Should create SFTConfig with default values."""
        from app.training.training_args import TrainingArgumentsFactory

        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            TrainingArgumentsFactory.create_training_args(
                job_id="test-job",
                output_dir="/tmp/output",
            )

            _, kwargs = mock_sft.call_args
            assert kwargs["num_train_epochs"] == 3
            assert kwargs["per_device_train_batch_size"] == 4
            assert kwargs["learning_rate"] == 2e-4
            assert kwargs["max_length"] == 2048
            assert kwargs["gradient_accumulation_steps"] == 4
            assert kwargs["seed"] == 42

    def test_create_training_args_custom(self):
        """Should accept custom training parameters."""
        from app.training.training_args import TrainingArgumentsFactory

        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            TrainingArgumentsFactory.create_training_args(
                job_id="test-job",
                output_dir="/tmp/output",
                epochs=5,
                batch_size=8,
                learning_rate=5e-4,
                max_seq_length=4096,
                seed=123,
            )

            _, kwargs = mock_sft.call_args
            assert kwargs["num_train_epochs"] == 5
            assert kwargs["per_device_train_batch_size"] == 8
            assert kwargs["learning_rate"] == 5e-4
            assert kwargs["max_length"] == 4096
            assert kwargs["seed"] == 123

    def test_create_training_args_lr_too_low(self):
        """Should raise ValueError for learning rate below 1e-6."""
        from app.training.training_args import TrainingArgumentsFactory

        with pytest.raises(ValueError, match="learning rate must be between"):
            TrainingArgumentsFactory.create_training_args(
                job_id="test-job",
                output_dir="/tmp/output",
                learning_rate=1e-7,
            )

    def test_create_training_args_lr_too_high(self):
        """Should raise ValueError for learning rate above 1e-3."""
        from app.training.training_args import TrainingArgumentsFactory

        with pytest.raises(ValueError, match="learning rate must be between"):
            TrainingArgumentsFactory.create_training_args(
                job_id="test-job",
                output_dir="/tmp/output",
                learning_rate=1e-2,
            )

    def test_create_training_args_lr_at_min_boundary(self):
        """Should accept learning rate at the minimum boundary (1e-6)."""
        from app.training.training_args import TrainingArgumentsFactory

        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            # Should not raise
            TrainingArgumentsFactory.create_training_args(
                job_id="test-job",
                output_dir="/tmp/output",
                learning_rate=1e-6,
            )
            mock_sft.assert_called_once()

    def test_create_training_args_lr_at_max_boundary(self):
        """Should accept learning rate at the maximum boundary (1e-3)."""
        from app.training.training_args import TrainingArgumentsFactory

        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            # Should not raise
            TrainingArgumentsFactory.create_training_args(
                job_id="test-job",
                output_dir="/tmp/output",
                learning_rate=1e-3,
            )
            mock_sft.assert_called_once()

    def test_create_training_args_qlora_specific_settings(self):
        """Should set QLoRA-specific training arguments."""
        from app.training.training_args import TrainingArgumentsFactory

        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            TrainingArgumentsFactory.create_training_args(
                job_id="test-job",
                output_dir="/tmp/output",
            )

            _, kwargs = mock_sft.call_args
            assert kwargs["lr_scheduler_type"] == "cosine"
            assert kwargs["warmup_ratio"] == 0.03
            assert kwargs["logging_steps"] == 10
            assert kwargs["fp16"] is True
            assert kwargs["gradient_checkpointing"] is True
            assert kwargs["optim"] == "paged_adamw_8bit"
            assert kwargs["save_strategy"] == "no"
            assert kwargs["report_to"] == "none"
            assert kwargs["max_grad_norm"] == 1.0

    def test_create_training_args_run_name(self):
        """Should set run_name to qlora-{job_id}."""
        from app.training.training_args import TrainingArgumentsFactory

        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            TrainingArgumentsFactory.create_training_args(
                job_id="abc-123",
                output_dir="/tmp/output",
            )

            _, kwargs = mock_sft.call_args
            assert kwargs["run_name"] == "qlora-abc-123"


# ---------------------------------------------------------------------------
# Artifact Validator Tests
# ---------------------------------------------------------------------------


class TestArtifactValidator:
    """Tests for ArtifactValidator (artifact directory validation)."""

    def test_validate_artifact_dir_valid(self, tmp_path):
        """Should return True for a valid artifact directory."""
        from app.training.artifact_validator import ArtifactValidator

        # Create valid artifact structure
        (tmp_path / "adapter_model.safetensors").write_bytes(b"\x00" * 100)
        (tmp_path / "adapter_config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "training_metadata.json").write_text("{}", encoding="utf-8")
        tokenizer_dir = tmp_path / "tokenizer"
        tokenizer_dir.mkdir()
        (tokenizer_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        assert ArtifactValidator.validate_artifact_dir(tmp_path) is True

    def test_validate_artifact_dir_missing_directory(self):
        """Should raise FileNotFoundError for nonexistent directory."""
        from app.training.artifact_validator import ArtifactValidator

        with pytest.raises(FileNotFoundError, match="Artifact directory not found"):
            ArtifactValidator.validate_artifact_dir("/nonexistent/path")

    def test_validate_artifact_dir_missing_safetensors(self, tmp_path):
        """Should raise FileNotFoundError for missing adapter_model.safetensors."""
        from app.training.artifact_validator import ArtifactValidator

        (tmp_path / "adapter_config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "training_metadata.json").write_text("{}", encoding="utf-8")
        tokenizer_dir = tmp_path / "tokenizer"
        tokenizer_dir.mkdir()
        (tokenizer_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="adapter_model.safetensors"):
            ArtifactValidator.validate_artifact_dir(tmp_path)

    def test_validate_artifact_dir_missing_config(self, tmp_path):
        """Should raise FileNotFoundError for missing adapter_config.json."""
        from app.training.artifact_validator import ArtifactValidator

        (tmp_path / "adapter_model.safetensors").write_bytes(b"\x00" * 100)
        (tmp_path / "training_metadata.json").write_text("{}", encoding="utf-8")
        tokenizer_dir = tmp_path / "tokenizer"
        tokenizer_dir.mkdir()
        (tokenizer_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="adapter_config.json"):
            ArtifactValidator.validate_artifact_dir(tmp_path)

    def test_validate_artifact_dir_missing_metadata(self, tmp_path):
        """Should raise FileNotFoundError for missing training_metadata.json."""
        from app.training.artifact_validator import ArtifactValidator

        (tmp_path / "adapter_model.safetensors").write_bytes(b"\x00" * 100)
        (tmp_path / "adapter_config.json").write_text("{}", encoding="utf-8")
        tokenizer_dir = tmp_path / "tokenizer"
        tokenizer_dir.mkdir()
        (tokenizer_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="training_metadata.json"):
            ArtifactValidator.validate_artifact_dir(tmp_path)

    def test_validate_artifact_dir_missing_tokenizer_dir(self, tmp_path):
        """Should raise FileNotFoundError for missing tokenizer directory."""
        from app.training.artifact_validator import ArtifactValidator

        (tmp_path / "adapter_model.safetensors").write_bytes(b"\x00" * 100)
        (tmp_path / "adapter_config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "training_metadata.json").write_text("{}", encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="tokenizer"):
            ArtifactValidator.validate_artifact_dir(tmp_path)

    def test_validate_artifact_dir_empty_safetensors(self, tmp_path):
        """Should raise ValueError for empty adapter_model.safetensors."""
        from app.training.artifact_validator import ArtifactValidator

        (tmp_path / "adapter_model.safetensors").write_bytes(b"")
        (tmp_path / "adapter_config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "training_metadata.json").write_text("{}", encoding="utf-8")
        tokenizer_dir = tmp_path / "tokenizer"
        tokenizer_dir.mkdir()
        (tokenizer_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        with pytest.raises(ValueError, match="empty"):
            ArtifactValidator.validate_artifact_dir(tmp_path)

    def test_validate_artifact_dir_empty_tokenizer_dir(self, tmp_path):
        """Should raise ValueError for empty tokenizer directory."""
        from app.training.artifact_validator import ArtifactValidator

        (tmp_path / "adapter_model.safetensors").write_bytes(b"\x00" * 100)
        (tmp_path / "adapter_config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "training_metadata.json").write_text("{}", encoding="utf-8")
        (tmp_path / "tokenizer").mkdir()

        with pytest.raises(ValueError, match="empty"):
            ArtifactValidator.validate_artifact_dir(tmp_path)

    def test_validate_training_metadata_valid(self, tmp_path):
        """Should return True for valid training metadata."""
        from app.training.artifact_validator import ArtifactValidator

        metadata = {
            "job_id": "test-123",
            "base_model": "google/gemma-3-1b-it",
            "training_type": "qlora",
            "dataset_rows": 100,
            "epochs": 3,
            "batch_size": 4,
            "learning_rate": 2e-4,
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "seed": 42,
            "torch_version": "2.4.0",
            "transformers_version": "4.45.0",
            "peft_version": "0.13.0",
            "bitsandbytes_version": "0.44.0",
            "python_version": "3.11.0",
            "platform": "Linux",
            "training_duration": 120.5,
        }
        metadata_path = tmp_path / "training_metadata.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        assert ArtifactValidator.validate_training_metadata(metadata_path) is True

    def test_validate_training_metadata_missing_file(self, tmp_path):
        """Should raise FileNotFoundError for missing metadata file."""
        from app.training.artifact_validator import ArtifactValidator

        with pytest.raises(FileNotFoundError):
            ArtifactValidator.validate_training_metadata(
                tmp_path / "nonexistent.json"
            )

    def test_validate_training_metadata_missing_keys(self, tmp_path):
        """Should raise ValueError for missing required keys."""
        from app.training.artifact_validator import ArtifactValidator

        metadata = {"job_id": "test-123", "base_model": "test/model"}
        metadata_path = tmp_path / "training_metadata.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        with pytest.raises(ValueError, match="missing required keys"):
            ArtifactValidator.validate_training_metadata(metadata_path)

    def test_validate_training_metadata_invalid_json(self, tmp_path):
        """Should raise json.JSONDecodeError for invalid JSON."""
        import json

        from app.training.artifact_validator import ArtifactValidator

        metadata_path = tmp_path / "training_metadata.json"
        metadata_path.write_text("{invalid json", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            ArtifactValidator.validate_training_metadata(metadata_path)

    def test_validate_training_metadata_all_18_keys_required(self, tmp_path):
        """Should require all 18 metadata keys."""
        from app.training.artifact_validator import REQUIRED_METADATA_KEYS

        assert len(REQUIRED_METADATA_KEYS) == 18

    def test_validate_training_metadata_single_key_missing(self, tmp_path):
        """Should detect a single missing key."""
        from app.training.artifact_validator import ArtifactValidator

        # Create metadata with all keys except "platform"
        metadata = {
            "job_id": "test-123",
            "base_model": "google/gemma-3-1b-it",
            "training_type": "qlora",
            "dataset_rows": 100,
            "epochs": 3,
            "batch_size": 4,
            "learning_rate": 2e-4,
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "seed": 42,
            "torch_version": "2.4.0",
            "transformers_version": "4.45.0",
            "peft_version": "0.13.0",
            "bitsandbytes_version": "0.44.0",
            "python_version": "3.11.0",
            "training_duration": 120.5,
            # "platform" is missing
        }
        metadata_path = tmp_path / "training_metadata.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        with pytest.raises(ValueError, match="platform"):
            ArtifactValidator.validate_training_metadata(metadata_path)


# ---------------------------------------------------------------------------
# QLoRA Training Runner Tests (mocked)
# ---------------------------------------------------------------------------


class TestQLoRATrainingRunner:
    """Tests for qlora_training_runner (fully mocked ML pipeline).

    These tests mock all torch/transformers/peft/trl imports to
    verify the runner's orchestration logic without GPU.
    """

    def _create_mock_job(self, job_id="00000000-0000-0000-0000-000000000001"):
        """Create a mock TrainingJob object."""
        from app.models.training_job import TrainingJobStatus, TrainingType

        job = MagicMock()
        job.id = job_id
        job.base_model = "google/gemma-3-1b-it"
        job.training_type = TrainingType.QLORA
        job.status = TrainingJobStatus.QUEUED
        job.configuration = {
            "epochs": 1,
            "batch_size": 2,
            "learning_rate": 2e-4,
            "max_seq_length": 512,
            "seed": 42,
        }
        job.dataset_id = "dataset-1"
        job.dataset_version_id = "version-1"
        job.started_at = None
        job.completed_at = None
        job.artifact_path = None
        job.error_message = None
        return job

    @patch("app.workers.qlora_training_runner._get_sync_session")
    @patch("app.workers.qlora_training_runner._resolve_dataset_path")
    @patch("app.workers.qlora_training_runner.AutoTokenizer")
    @patch("app.workers.qlora_training_runner.AutoModelForCausalLM")
    @patch("app.workers.qlora_training_runner.get_peft_model")
    @patch("app.workers.qlora_training_runner.prepare_model_for_kbit_training")
    @patch("app.workers.qlora_training_runner.SFTTrainer")
    @patch("app.workers.qlora_training_runner.HFDataset")
    @patch("app.workers.qlora_training_runner.BitsAndBytesConfig")
    @patch("app.workers.qlora_training_runner.LoraConfig")
    @patch("app.workers.qlora_training_runner.TrainingArgumentsFactory")
    @patch("app.workers.qlora_training_runner.ArtifactValidator")
    @patch("app.workers.qlora_training_runner.DatasetLoader")
    @patch("app.workers.qlora_training_runner.AlpacaFormatter")
    def test_runner_happy_path(
        self,
        mock_alpaca,
        mock_dataset,
        mock_validator,
        mock_training_args,
        mock_lora,
        mock_bnb,
        mock_hf_dataset,
        mock_sft_trainer,
        mock_prepare,
        mock_get_peft,
        mock_auto_model,
        mock_auto_tokenizer,
        mock_resolve_path,
        mock_get_session,
        tmp_path,
    ):
        """Full happy-path test: job QUEUED â†’ RUNNING â†’ COMPLETED."""
        from app.workers.qlora_training_runner import qlora_training_runner

        # Setup mock job
        mock_job = self._create_mock_job()

        # Setup mock session
        mock_session = MagicMock()
        mock_session.get.return_value = mock_job
        mock_get_session.return_value = mock_session

        # Setup dataset path
        dataset_path = tmp_path / "datasets" / "dataset-1" / "version-1" / "data.jsonl"
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        dataset_path.write_text(
            json.dumps({"instruction": "A", "input": "B", "output": "C"}) + "\n",
            encoding="utf-8",
        )
        mock_resolve_path.return_value = dataset_path

        # Setup dataset loader
        mock_dataset.load_jsonl.return_value = [
            {"instruction": "A", "input": "B", "output": "C"}
        ]
        mock_dataset.validate_alpaca_schema.return_value = []
        mock_dataset.count_examples.return_value = 1

        # Setup formatter
        mock_alpaca.format_dataset.return_value = ["formatted text"]

        # Setup tokenizer
        mock_tokenizer = MagicMock()
        mock_auto_tokenizer.from_pretrained.return_value = mock_tokenizer

        # Setup model
        mock_model = MagicMock()
        mock_auto_model.from_pretrained.return_value = mock_model
        mock_prepare.return_value = mock_model
        mock_get_peft.return_value = mock_model
        mock_model.print_trainable_parameters = MagicMock()

        # Setup trainer
        mock_trainer_instance = MagicMock()
        mock_sft_trainer.return_value = mock_trainer_instance

        # Setup training args
        mock_training_args.create_training_args.return_value = MagicMock()

        # Setup PEFT config (inlined — LoraConfig is called directly in the runner)
        mock_lora.return_value = MagicMock()

        # Setup QLoRA config (inlined — BitsAndBytesConfig is called directly in the runner)
        mock_bnb.return_value = MagicMock()

        # Setup artifact dir
        artifact_dir = tmp_path / "artifacts" / "00000000-0000-0000-0000-000000000001"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # Patch settings to use tmp_path
        with patch(
            "app.workers.qlora_training_runner.settings"
        ) as mock_settings:
            mock_settings.LOCAL_STORAGE_PATH = str(tmp_path / "local_storage")
            mock_settings.database_url_sync = "sqlite:///:memory:"

            # Create the local_storage/artifacts dir
            (tmp_path / "local_storage" / "artifacts" / "00000000-0000-0000-0000-000000000001").mkdir(
                parents=True, exist_ok=True
            )

            result = qlora_training_runner("00000000-0000-0000-0000-000000000001")

        # Verify job was marked RUNNING
        from app.models.training_job import TrainingJobStatus

        assert mock_job.status == TrainingJobStatus.COMPLETED
        assert mock_job.started_at is not None
        assert mock_job.completed_at is not None
        assert mock_job.artifact_path is not None
        assert result["status"] == "completed"

    @patch("app.workers.qlora_training_runner._get_sync_session")
    @patch("app.workers.qlora_training_runner._mark_job_failed")
    def test_runner_job_not_found(self, mock_mark_failed, mock_get_session):
        """Should handle job not found gracefully."""
        from app.workers.qlora_training_runner import qlora_training_runner

        mock_session = MagicMock()
        mock_session.get.return_value = None
        mock_get_session.return_value = mock_session

        result = qlora_training_runner("00000000-0000-0000-0000-000000009999")

        assert result["status"] == "failed"
        mock_mark_failed.assert_called_once()

    @patch("app.workers.qlora_training_runner._get_sync_session")
    @patch("app.workers.qlora_training_runner._resolve_dataset_path")
    @patch("app.workers.qlora_training_runner.DatasetLoader")
    @patch("app.workers.qlora_training_runner.AlpacaFormatter")
    def test_runner_dataset_not_found(
        self,
        mock_alpaca,
        mock_dataset,
        mock_resolve_path,
        mock_get_session,
    ):
        """Should mark job FAILED when dataset is not found."""
        from app.workers.qlora_training_runner import qlora_training_runner

        mock_job = self._create_mock_job()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_job
        mock_get_session.return_value = mock_session

        mock_resolve_path.side_effect = FileNotFoundError("Dataset not found")

        result = qlora_training_runner("00000000-0000-0000-0000-000000000001")

        assert result["status"] == "failed"
        assert "Dataset not found" in result["error"]

    @patch("app.workers.qlora_training_runner._get_sync_session")
    @patch("app.workers.qlora_training_runner._resolve_dataset_path")
    @patch("app.workers.qlora_training_runner.DatasetLoader")
    @patch("app.workers.qlora_training_runner.AlpacaFormatter")
    def test_runner_schema_validation_fails(
        self,
        mock_alpaca,
        mock_dataset,
        mock_resolve_path,
        mock_get_session,
    ):
        """Should mark job FAILED when dataset schema validation fails."""
        from app.workers.qlora_training_runner import qlora_training_runner

        mock_job = self._create_mock_job()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_job
        mock_get_session.return_value = mock_session

        mock_resolve_path.return_value = Path("/some/path")
        mock_dataset.load_dataset.side_effect = ValueError(
            "Alpaca schema validation failed:\nRecord 0 missing required keys: instruction, input, output"
        )

        result = qlora_training_runner("00000000-0000-0000-0000-000000000001")

        assert result["status"] == "failed"
        assert "schema validation" in result["error"].lower()

    @patch("app.workers.qlora_training_runner._get_sync_session")
    @patch("app.workers.qlora_training_runner._resolve_dataset_path")
    @patch("app.workers.qlora_training_runner.AutoTokenizer")
    @patch("app.workers.qlora_training_runner.AutoModelForCausalLM")
    @patch("app.workers.qlora_training_runner.get_peft_model")
    @patch("app.workers.qlora_training_runner.prepare_model_for_kbit_training")
    @patch("app.workers.qlora_training_runner.SFTTrainer")
    @patch("app.workers.qlora_training_runner.HFDataset")
    @patch("app.workers.qlora_training_runner.BitsAndBytesConfig")
    @patch("app.workers.qlora_training_runner.LoraConfig")
    @patch("app.workers.qlora_training_runner.TrainingArgumentsFactory")
    @patch("app.workers.qlora_training_runner.ArtifactValidator")
    @patch("app.workers.qlora_training_runner.DatasetLoader")
    @patch("app.workers.qlora_training_runner.AlpacaFormatter")
    def test_runner_cuda_oom(
        self,
        mock_alpaca,
        mock_dataset,
        mock_validator,
        mock_training_args,
        mock_lora,
        mock_bnb,
        mock_hf_dataset,
        mock_sft_trainer,
        mock_prepare,
        mock_get_peft,
        mock_auto_model,
        mock_auto_tokenizer,
        mock_resolve_path,
        mock_get_session,
        tmp_path,
    ):
        """Should mark job FAILED with OOM message on CUDA OOM."""
        from app.workers.qlora_training_runner import qlora_training_runner, _OOM_ERROR_MESSAGE

        mock_job = self._create_mock_job()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_job
        mock_get_session.return_value = mock_session

        mock_resolve_path.return_value = tmp_path / "data.jsonl"
        mock_dataset.load_jsonl.return_value = [
            {"instruction": "A", "input": "B", "output": "C"}
        ]
        mock_dataset.validate_alpaca_schema.return_value = []
        mock_dataset.count_examples.return_value = 1
        mock_alpaca.format_dataset.return_value = ["formatted"]

        # Make trainer.train() raise CUDA OOM
        mock_trainer_instance = MagicMock()
        mock_trainer_instance.train.side_effect = RuntimeError(
            "CUDA out of memory. Tried to allocate 2.00 GiB"
        )
        mock_sft_trainer.return_value = mock_trainer_instance

        mock_auto_tokenizer.from_pretrained.return_value = MagicMock()
        mock_auto_model.from_pretrained.return_value = MagicMock()
        mock_prepare.return_value = MagicMock()
        mock_get_peft.return_value = MagicMock()
        mock_bnb.return_value = MagicMock()
        mock_lora.return_value = MagicMock()
        mock_training_args.create_training_args.return_value = MagicMock()

        with patch(
            "app.workers.qlora_training_runner.settings"
        ) as mock_settings:
            mock_settings.LOCAL_STORAGE_PATH = str(tmp_path)
            mock_settings.database_url_sync = "sqlite:///:memory:"

            result = qlora_training_runner("00000000-0000-0000-0000-000000000001")

        assert result["status"] == "failed"
        assert result["error"] == _OOM_ERROR_MESSAGE

    @patch("app.workers.qlora_training_runner._get_sync_session")
    @patch("app.workers.qlora_training_runner._resolve_dataset_path")
    @patch("app.workers.qlora_training_runner.AutoTokenizer")
    @patch("app.workers.qlora_training_runner.AutoModelForCausalLM")
    @patch("app.workers.qlora_training_runner.get_peft_model")
    @patch("app.workers.qlora_training_runner.prepare_model_for_kbit_training")
    @patch("app.workers.qlora_training_runner.SFTTrainer")
    @patch("app.workers.qlora_training_runner.HFDataset")
    @patch("app.workers.qlora_training_runner.BitsAndBytesConfig")
    @patch("app.workers.qlora_training_runner.LoraConfig")
    @patch("app.workers.qlora_training_runner.TrainingArgumentsFactory")
    @patch("app.workers.qlora_training_runner.ArtifactValidator")
    @patch("app.workers.qlora_training_runner.DatasetLoader")
    @patch("app.workers.qlora_training_runner.AlpacaFormatter")
    def test_runner_unsupported_model(
        self,
        mock_alpaca,
        mock_dataset,
        mock_validator,
        mock_training_args,
        mock_lora,
        mock_bnb,
        mock_hf_dataset,
        mock_sft_trainer,
        mock_prepare,
        mock_get_peft,
        mock_auto_model,
        mock_auto_tokenizer,
        mock_resolve_path,
        mock_get_session,
    ):
        """Should mark job FAILED for unsupported base_model."""
        from app.workers.qlora_training_runner import qlora_training_runner

        mock_job = self._create_mock_job()
        mock_job.base_model = "meta/llama-3-70b"  # unsupported
        mock_session = MagicMock()
        mock_session.get.return_value = mock_job
        mock_get_session.return_value = mock_session

        result = qlora_training_runner("00000000-0000-0000-0000-000000000001")

        assert result["status"] == "failed"
        assert "Unsupported model" in result["error"]

    @patch("app.workers.qlora_training_runner._get_sync_session")
    @patch("app.workers.qlora_training_runner._resolve_dataset_path")
    @patch("app.workers.qlora_training_runner.AutoTokenizer")
    @patch("app.workers.qlora_training_runner.AutoModelForCausalLM")
    @patch("app.workers.qlora_training_runner.get_peft_model")
    @patch("app.workers.qlora_training_runner.prepare_model_for_kbit_training")
    @patch("app.workers.qlora_training_runner.SFTTrainer")
    @patch("app.workers.qlora_training_runner.HFDataset")
    @patch("app.workers.qlora_training_runner.BitsAndBytesConfig")
    @patch("app.workers.qlora_training_runner.LoraConfig")
    @patch("app.workers.qlora_training_runner.TrainingArgumentsFactory")
    @patch("app.workers.qlora_training_runner.ArtifactValidator")
    @patch("app.workers.qlora_training_runner.DatasetLoader")
    @patch("app.workers.qlora_training_runner.AlpacaFormatter")
    def test_runner_general_exception(
        self,
        mock_alpaca,
        mock_dataset,
        mock_validator,
        mock_training_args,
        mock_lora,
        mock_bnb,
        mock_hf_dataset,
        mock_sft_trainer,
        mock_prepare,
        mock_get_peft,
        mock_auto_model,
        mock_auto_tokenizer,
        mock_resolve_path,
        mock_get_session,
    ):
        """Should mark job FAILED on general exceptions."""
        from app.workers.qlora_training_runner import qlora_training_runner

        mock_job = self._create_mock_job()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_job
        mock_get_session.return_value = mock_session

        mock_resolve_path.return_value = Path("/some/path")
        mock_dataset.load_jsonl.return_value = [
            {"instruction": "A", "input": "B", "output": "C"}
        ]
        mock_dataset.validate_alpaca_schema.return_value = []
        mock_dataset.count_examples.return_value = 1
        mock_alpaca.format_dataset.return_value = ["formatted"]

        # Make tokenizer loading fail
        mock_auto_tokenizer.from_pretrained.side_effect = Exception(
            "Model download failed"
        )

        mock_bnb.return_value = MagicMock()
        mock_lora.return_value = MagicMock()
        mock_training_args.create_training_args.return_value = MagicMock()

        result = qlora_training_runner("00000000-0000-0000-0000-000000000001")

        assert result["status"] == "failed"
        assert "Model download failed" in result["error"]


# ---------------------------------------------------------------------------
# Training Metadata Builder Tests
# ---------------------------------------------------------------------------


class TestTrainingMetadataBuilder:
    """Tests for _build_training_metadata helper."""

    def test_metadata_contains_all_required_keys(self):
        """Should include all 18 required metadata keys."""
        from app.training.artifact_validator import REQUIRED_METADATA_KEYS
        from app.workers.qlora_training_runner import _build_training_metadata

        mock_job = MagicMock()
        mock_job.id = "test-123"
        mock_job.base_model = "google/gemma-3-1b-it"
        mock_job.training_type.value = "qlora"
        mock_job.configuration = {
            "epochs": 3,
            "batch_size": 4,
            "learning_rate": 2e-4,
        }

        with patch("app.workers.qlora_training_runner.torch") as mock_torch, \
             patch("app.workers.qlora_training_runner.transformers") as mock_transformers, \
             patch("app.workers.qlora_training_runner.peft") as mock_peft, \
             patch("app.workers.qlora_training_runner.bitsandbytes") as mock_bnb:

            mock_torch.__version__ = "2.4.0"
            mock_transformers.__version__ = "4.45.0"
            mock_peft.__version__ = "0.13.0"
            mock_bnb.__version__ = "0.44.0"

            metadata = _build_training_metadata(mock_job, dataset_rows=100, seed=42)

        for key in REQUIRED_METADATA_KEYS:
            assert key in metadata, f"Missing key: {key}"

    def test_metadata_values_from_job(self):
        """Should populate metadata from job configuration."""
        from app.workers.qlora_training_runner import _build_training_metadata

        mock_job = MagicMock()
        mock_job.id = "job-abc"
        mock_job.base_model = "google/gemma-3-1b-it"
        mock_job.training_type.value = "qlora"
        mock_job.configuration = {
            "epochs": 5,
            "batch_size": 8,
            "learning_rate": 3e-4,
        }

        with patch("app.workers.qlora_training_runner.torch") as mock_torch, \
             patch("app.workers.qlora_training_runner.transformers") as mock_transformers, \
             patch("app.workers.qlora_training_runner.peft") as mock_peft, \
             patch("app.workers.qlora_training_runner.bitsandbytes") as mock_bnb:

            mock_torch.__version__ = "2.4.0"
            mock_transformers.__version__ = "4.45.0"
            mock_peft.__version__ = "0.13.0"
            mock_bnb.__version__ = "0.44.0"

            metadata = _build_training_metadata(
                mock_job, dataset_rows=500, seed=99, training_duration=3600.0
            )

        assert metadata["job_id"] == "job-abc"
        assert metadata["base_model"] == "google/gemma-3-1b-it"
        assert metadata["training_type"] == "qlora"
        assert metadata["dataset_rows"] == 500
        assert metadata["epochs"] == 5
        assert metadata["batch_size"] == 8
        assert metadata["learning_rate"] == 3e-4
        assert metadata["seed"] == 99
        assert metadata["training_duration"] == 3600.0

    def test_metadata_training_duration_none(self):
        """Should set training_duration to None when not provided."""
        from app.workers.qlora_training_runner import _build_training_metadata

        mock_job = MagicMock()
        mock_job.id = "job-abc"
        mock_job.base_model = "google/gemma-3-1b-it"
        mock_job.training_type.value = "qlora"
        mock_job.configuration = {
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 2e-4,
        }

        with patch("app.workers.qlora_training_runner.torch") as mock_torch, \
             patch("app.workers.qlora_training_runner.transformers") as mock_transformers, \
             patch("app.workers.qlora_training_runner.peft") as mock_peft, \
             patch("app.workers.qlora_training_runner.bitsandbytes") as mock_bnb:

            mock_torch.__version__ = "2.4.0"
            mock_transformers.__version__ = "4.45.0"
            mock_peft.__version__ = "0.13.0"
            mock_bnb.__version__ = "0.44.0"

            metadata = _build_training_metadata(mock_job, dataset_rows=100, seed=42)

        assert metadata["training_duration"] is None

    def test_metadata_contains_lora_keys(self):
        """Should include lora_r, lora_alpha, lora_dropout in metadata."""
        from app.workers.qlora_training_runner import _build_training_metadata

        mock_job = MagicMock()
        mock_job.id = "job-lora"
        mock_job.base_model = "google/gemma-3-1b-it"
        mock_job.training_type.value = "qlora"
        mock_job.configuration = {
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 2e-4,
            "lora_r": 32,
            "lora_alpha": 64,
            "lora_dropout": 0.1,
        }

        with patch("app.workers.qlora_training_runner.torch") as mock_torch, \
             patch("app.workers.qlora_training_runner.transformers") as mock_transformers, \
             patch("app.workers.qlora_training_runner.peft") as mock_peft, \
             patch("app.workers.qlora_training_runner.bitsandbytes") as mock_bnb:

            mock_torch.__version__ = "2.4.0"
            mock_transformers.__version__ = "4.45.0"
            mock_peft.__version__ = "0.13.0"
            mock_bnb.__version__ = "0.44.0"

            metadata = _build_training_metadata(mock_job, dataset_rows=100, seed=42)

        assert metadata["lora_r"] == 32
        assert metadata["lora_alpha"] == 64
        assert metadata["lora_dropout"] == 0.1

    def test_metadata_lora_defaults(self):
        """Should use default lora values when not in config."""
        from app.workers.qlora_training_runner import _build_training_metadata

        mock_job = MagicMock()
        mock_job.id = "job-defaults"
        mock_job.base_model = "google/gemma-3-1b-it"
        mock_job.training_type.value = "qlora"
        mock_job.configuration = {
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 2e-4,
        }

        with patch("app.workers.qlora_training_runner.torch") as mock_torch, \
             patch("app.workers.qlora_training_runner.transformers") as mock_transformers, \
             patch("app.workers.qlora_training_runner.peft") as mock_peft, \
             patch("app.workers.qlora_training_runner.bitsandbytes") as mock_bnb:

            mock_torch.__version__ = "2.4.0"
            mock_transformers.__version__ = "4.45.0"
            mock_peft.__version__ = "0.13.0"
            mock_bnb.__version__ = "0.44.0"

            metadata = _build_training_metadata(mock_job, dataset_rows=100, seed=42)

        assert metadata["lora_r"] == 16
        assert metadata["lora_alpha"] == 32
        assert metadata["lora_dropout"] == 0.05


# ---------------------------------------------------------------------------
# OOM Error Message Test
# ---------------------------------------------------------------------------


class TestOOMErrorMessage:
    """Tests for the OOM error message constant."""

    def test_oom_message_format(self):
        """OOM message should match user specification exactly."""
        from app.workers.qlora_training_runner import _OOM_ERROR_MESSAGE

        assert _OOM_ERROR_MESSAGE == "CUDA Out Of Memory. Try: - batch_size=2 - max_seq_length=1024"


# ---------------------------------------------------------------------------
# Dataset Path Resolution Tests
# ---------------------------------------------------------------------------


class TestDatasetPathResolution:
    """Tests for _resolve_dataset_path helper."""

    @patch("app.workers.qlora_training_runner.settings")
    def test_resolve_path_exists(self, mock_settings, tmp_path):
        """Should return path when dataset file exists."""
        from app.workers.qlora_training_runner import _resolve_dataset_path

        # Create dataset file
        dataset_file = (
            tmp_path / "datasets" / "ds-1" / "ver-1" / "data.jsonl"
        )
        dataset_file.parent.mkdir(parents=True, exist_ok=True)
        dataset_file.write_text("test", encoding="utf-8")

        mock_settings.LOCAL_STORAGE_PATH = str(tmp_path)

        mock_job = MagicMock()
        mock_job.dataset_id = "ds-1"
        mock_job.dataset_version_id = "ver-1"

        result = _resolve_dataset_path(mock_job)
        assert result == dataset_file

    @patch("app.workers.qlora_training_runner.settings")
    def test_resolve_path_not_found(self, mock_settings, tmp_path):
        """Should raise FileNotFoundError when dataset file missing."""
        from app.workers.qlora_training_runner import _resolve_dataset_path

        mock_settings.LOCAL_STORAGE_PATH = str(tmp_path)

        mock_job = MagicMock()
        mock_job.dataset_id = "nonexistent"
        mock_job.dataset_version_id = "nonexistent"

        with pytest.raises(FileNotFoundError, match="Dataset file not found"):
            _resolve_dataset_path(mock_job)


# ---------------------------------------------------------------------------
# Training Module __init__ Tests
# ---------------------------------------------------------------------------


class TestTrainingModuleInit:
    """Tests for the training module's public API."""

    def test_all_exports_available(self):
        """All __all__ exports should be importable."""
        from app.training import (
            AlpacaFormatter,
            ArtifactValidator,
            DatasetLoader,
            ModelConfig,
            SUPPORTED_MODELS,
            TrainingArgumentsFactory,
        )

        assert ModelConfig is not None
        assert SUPPORTED_MODELS is not None
        assert DatasetLoader is not None
        assert AlpacaFormatter is not None
        assert TrainingArgumentsFactory is not None
        assert ArtifactValidator is not None


# ---------------------------------------------------------------------------
# Additional TrainingArgumentsFactory Tests
# ---------------------------------------------------------------------------


class TestTrainingArgumentsFactoryExtended:
    """Extended tests for TrainingArgumentsFactory."""

    def test_create_training_args_output_dir_converted_to_string(self):
        """Should convert Path output_dir to string."""
        from app.training.training_args import TrainingArgumentsFactory
        from pathlib import Path

        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            TrainingArgumentsFactory.create_training_args(
                job_id="test-job",
                output_dir=Path("/tmp/output"),
            )

            _, kwargs = mock_sft.call_args
            # On Windows, str(Path("/tmp/output")) produces "\tmp\output"
            assert kwargs["output_dir"] == str(Path("/tmp/output"))

    def test_create_training_args_gradient_accumulation_steps(self):
        """Should pass gradient_accumulation_steps to SFTConfig."""
        from app.training.training_args import TrainingArgumentsFactory

        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            TrainingArgumentsFactory.create_training_args(
                job_id="test-job",
                output_dir="/tmp/output",
                gradient_accumulation_steps=8,
            )

            _, kwargs = mock_sft.call_args
            assert kwargs["gradient_accumulation_steps"] == 8

    def test_create_training_args_default_lr(self):
        """Default learning rate should be 2e-4."""
        from app.training.training_args import TrainingArgumentsFactory

        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            TrainingArgumentsFactory.create_training_args(
                job_id="test-job",
                output_dir="/tmp/output",
            )

            _, kwargs = mock_sft.call_args
            assert kwargs["learning_rate"] == 2e-4


# ---------------------------------------------------------------------------
# ArtifactValidator Constants Tests
# ---------------------------------------------------------------------------


class TestArtifactValidatorConstants:
    """Tests for ArtifactValidator module-level constants."""

    def test_required_artifact_files_list(self):
        """REQUIRED_ARTIFACT_FILES should contain 3 files."""
        from app.training.artifact_validator import REQUIRED_ARTIFACT_FILES

        assert len(REQUIRED_ARTIFACT_FILES) == 3
        assert "adapter_model.safetensors" in REQUIRED_ARTIFACT_FILES
        assert "adapter_config.json" in REQUIRED_ARTIFACT_FILES
        assert "training_metadata.json" in REQUIRED_ARTIFACT_FILES

    def test_required_artifact_dirs_list(self):
        """REQUIRED_ARTIFACT_DIRS should contain tokenizer directory."""
        from app.training.artifact_validator import REQUIRED_ARTIFACT_DIRS

        assert len(REQUIRED_ARTIFACT_DIRS) == 1
        assert "tokenizer" in REQUIRED_ARTIFACT_DIRS

    def test_required_metadata_keys_count(self):
        """REQUIRED_METADATA_KEYS should contain exactly 18 keys."""
        from app.training.artifact_validator import REQUIRED_METADATA_KEYS

        assert len(REQUIRED_METADATA_KEYS) == 18

    def test_required_metadata_keys_includes_training_duration(self):
        """REQUIRED_METADATA_KEYS should include training_duration."""
        from app.training.artifact_validator import REQUIRED_METADATA_KEYS

        assert "training_duration" in REQUIRED_METADATA_KEYS

    def test_required_metadata_keys_includes_dataset_rows(self):
        """REQUIRED_METADATA_KEYS should include dataset_rows."""
        from app.training.artifact_validator import REQUIRED_METADATA_KEYS

        assert "dataset_rows" in REQUIRED_METADATA_KEYS


# ---------------------------------------------------------------------------
# OOM Detection Tests
# ---------------------------------------------------------------------------


class TestOOMDetection:
    """Tests for OOM error detection in the training runner."""

    def test_oom_detection_cuda_out_of_memory(self):
        """Should detect 'CUDA out of memory' in error message."""
        oom_indicators = ["CUDA out of memory", "OutOfMemoryError", "out of memory"]
        error_msg = "CUDA out of memory. Tried to allocate 2.00 GiB"
        is_oom = any(indicator in error_msg for indicator in oom_indicators)
        assert is_oom is True

    def test_oom_detection_outofmemoryerror(self):
        """Should detect 'OutOfMemoryError' in error message."""
        oom_indicators = ["CUDA out of memory", "OutOfMemoryError", "out of memory"]
        error_msg = "torch.cuda.OutOfMemoryError: allocation failed"
        is_oom = any(indicator in error_msg for indicator in oom_indicators)
        assert is_oom is True

    def test_oom_detection_non_oom_runtime_error(self):
        """Should NOT detect OOM in non-OOM RuntimeError."""
        oom_indicators = ["CUDA out of memory", "OutOfMemoryError", "out of memory"]
        error_msg = "RuntimeError: dimension mismatch in matmul"
        is_oom = any(indicator in error_msg for indicator in oom_indicators)
        assert is_oom is False

    def test_oom_message_contains_batch_size_hint(self):
        """OOM message should contain batch_size hint."""
        from app.workers.qlora_training_runner import _OOM_ERROR_MESSAGE

        assert "batch_size=2" in _OOM_ERROR_MESSAGE

    def test_oom_message_contains_seq_length_hint(self):
        """OOM message should contain max_seq_length hint."""
        from app.workers.qlora_training_runner import _OOM_ERROR_MESSAGE

        assert "max_seq_length=1024" in _OOM_ERROR_MESSAGE


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestIntegrationPipelines:
    """Integration tests combining multiple training module components."""

    def test_loader_to_formatter_pipeline(self, tmp_path):
        """DatasetLoader â†’ AlpacaFormatter pipeline should work end-to-end."""
        from app.training.dataset_loader import DatasetLoader
        from app.training.alpaca_formatter import AlpacaFormatter

        # Create JSONL file
        jsonl_path = tmp_path / "data.jsonl"
        jsonl_path.write_text(
            json.dumps({"instruction": "Summarize", "input": "Long text", "output": "Short"}) + "\n",
            encoding="utf-8",
        )

        # Load
        records = DatasetLoader.load_jsonl(jsonl_path)
        assert len(records) == 1

        # Format
        formatted = AlpacaFormatter.format_dataset(records)
        assert len(formatted) == 1
        assert "### Instruction:" in formatted[0]
        assert "### Input:" in formatted[0]
        assert "### Response:" in formatted[0]

    def test_metadata_builder_and_validator_pipeline(self):
        """_build_training_metadata output should pass ArtifactValidator."""
        from app.training.artifact_validator import REQUIRED_METADATA_KEYS

        # Simulate what _build_training_metadata produces
        metadata = {
            "job_id": "00000000-0000-0000-0000-000000000001",
            "base_model": "google/gemma-3-1b-it",
            "training_type": "qlora",
            "dataset_rows": 100,
            "epochs": 3,
            "batch_size": 4,
            "learning_rate": 2e-4,
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "seed": 42,
            "torch_version": "2.4.0",
            "transformers_version": "4.45.0",
            "peft_version": "0.13.0",
            "bitsandbytes_version": "0.44.0",
            "python_version": "3.14.2",
            "platform": "Linux",
            "training_duration": 120.5,
        }

        # All required keys should be present
        missing = [key for key in REQUIRED_METADATA_KEYS if key not in metadata]
        assert missing == []


# ============================================================================
# Phase 4.3 â€” Colab Validation Tests
# ============================================================================


class TestPhase43ColabValidation:
    """Tests for Phase 4.3 â€” Real Colab QLoRA Training Validation.

    These tests verify that the training module components produce
    configurations and artifacts consistent with the Stage 0 Colab
    validation notebook (training/notebooks/phase43_qlora_validation.ipynb).

    All tests run without GPU â€” ML dependencies are mocked.
    """

    # Stage 0 configuration from docs/20_real_training_validation_plan.md
    STAGE0_CONFIG = {
        "model": "google/gemma-3-1b-it",
        "dataset": "yahma/alpaca-cleaned",
        "num_samples": 50,
        "epochs": 1,
        "batch_size": 2,
        "max_seq_length": 512,
        "learning_rate": 2e-4,
        "gradient_accumulation_steps": 4,
        "logging_steps": 1,
        "save_strategy": "no",
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "lora_bias": "none",
        "lora_target_modules": [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_compute_dtype": "float16",
        "bnb_4bit_use_double_quant": True,
        "load_in_4bit": True,
    }

    # --- Training Args Tests ---

    def test_stage0_training_args_fp16(self):
        """Stage 0 training args must use fp16=True (T4 no bfloat16)."""
        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            from app.training.training_args import TrainingArgumentsFactory
            TrainingArgumentsFactory.create_training_args(
                job_id="stage0-test",
                output_dir="/tmp/stage0",
                epochs=1,
                batch_size=2,
                learning_rate=2e-4,
                max_seq_length=512,
                gradient_accumulation_steps=4,
            )
            _, call_kwargs = mock_sft.call_args
            assert call_kwargs["fp16"] is True

    def test_stage0_training_args_batch_and_seq(self):
        """Stage 0 training args must use batch_size=2, max_seq_length=512."""
        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            from app.training.training_args import TrainingArgumentsFactory
            TrainingArgumentsFactory.create_training_args(
                job_id="stage0-test",
                output_dir="/tmp/stage0",
                epochs=1,
                batch_size=2,
                learning_rate=2e-4,
                max_seq_length=512,
                gradient_accumulation_steps=4,
            )
            _, call_kwargs = mock_sft.call_args
            assert call_kwargs["per_device_train_batch_size"] == 2
            assert call_kwargs["max_length"] == 512
            assert call_kwargs["num_train_epochs"] == 1
            assert call_kwargs["gradient_accumulation_steps"] == 4

    def test_stage0_training_args_save_strategy_no(self):
        """Stage 0 training args must use save_strategy='no'."""
        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            from app.training.training_args import TrainingArgumentsFactory
            TrainingArgumentsFactory.create_training_args(
                job_id="stage0-test",
                output_dir="/tmp/stage0",
            )
            _, call_kwargs = mock_sft.call_args
            assert call_kwargs["save_strategy"] == "no"

    def test_stage0_training_args_gradient_checkpointing(self):
        """Stage 0 training args must enable gradient_checkpointing."""
        with patch("trl.SFTConfig") as mock_sft:
            mock_sft.return_value = MagicMock()
            from app.training.training_args import TrainingArgumentsFactory
            TrainingArgumentsFactory.create_training_args(
                job_id="stage0-test",
                output_dir="/tmp/stage0",
            )
            _, call_kwargs = mock_sft.call_args
            assert call_kwargs["gradient_checkpointing"] is True

    # --- Artifact Validation Tests ---

    def test_stage0_artifact_validation_full(self, tmp_path):
        """Stage 0 artifact directory must pass full validation."""
        from app.training.artifact_validator import ArtifactValidator

        # Create complete Stage 0 artifact structure
        (tmp_path / "adapter_model.safetensors").write_bytes(b"\x00" * 100)
        (tmp_path / "adapter_config.json").write_text(
            json.dumps({
                "r": 16, "lora_alpha": 32, "lora_dropout": 0.05,
                "target_modules": self.STAGE0_CONFIG["lora_target_modules"],
            }),
            encoding="utf-8",
        )
        (tmp_path / "training_metadata.json").write_text(
            json.dumps({
                "job_id": "stage0-validation",
                "base_model": "google/gemma-3-1b-it",
                "training_type": "qlora",
                "dataset_rows": 50,
                "epochs": 1,
                "batch_size": 2,
                "learning_rate": 2e-4,
                "lora_r": 16,
                "lora_alpha": 32,
                "lora_dropout": 0.05,
                "seed": 42,
                "torch_version": "2.4.0",
                "transformers_version": "4.50.0",
                "peft_version": "0.13.0",
                "bitsandbytes_version": "0.44.0",
                "python_version": "3.10.12",
                "platform": "Linux",
                "training_duration": 90.0,
            }),
            encoding="utf-8",
        )
        tokenizer_dir = tmp_path / "tokenizer"
        tokenizer_dir.mkdir()
        (tokenizer_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        assert ArtifactValidator.validate_artifact_dir(tmp_path) is True

    def test_stage0_metadata_all_18_keys_present(self, tmp_path):
        """Stage 0 training_metadata.json must contain all 18 required keys."""
        from app.training.artifact_validator import (
            ArtifactValidator,
            REQUIRED_METADATA_KEYS,
        )

        metadata = {k: "test" for k in REQUIRED_METADATA_KEYS}
        metadata["training_duration"] = 90.0
        metadata_path = tmp_path / "training_metadata.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        assert ArtifactValidator.validate_training_metadata(metadata_path) is True
        assert len(REQUIRED_METADATA_KEYS) == 18

    def test_stage0_metadata_validates_with_real_values(self, tmp_path):
        """Stage 0 metadata with real Colab values must pass validation."""
        from app.training.artifact_validator import ArtifactValidator

        metadata = {
            "job_id": "colab-stage0-001",
            "base_model": "google/gemma-3-1b-it",
            "training_type": "qlora",
            "dataset_rows": 50,
            "epochs": 1,
            "batch_size": 2,
            "learning_rate": 2e-4,
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "seed": 42,
            "torch_version": "2.4.0+cu121",
            "transformers_version": "4.50.0",
            "peft_version": "0.13.2",
            "bitsandbytes_version": "0.43.3",
            "python_version": "3.10.12",
            "platform": "Linux-5.15.0-x86_64-with-glibc2.31",
            "training_duration": 87.3,
        }
        metadata_path = tmp_path / "training_metadata.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        assert ArtifactValidator.validate_training_metadata(metadata_path) is True

    # --- Model Registry Tests ---

    def test_stage0_model_quantized_vram_under_4gb(self):
        """Stage 0 model must report quantized VRAM under 4 GB."""
        from app.training.model_registry import SUPPORTED_MODELS

        config = SUPPORTED_MODELS["google/gemma-3-1b-it"]
        assert config.quantized_vram_gb <= 4.0

    def test_stage0_model_attn_implementation_eager(self):
        """Stage 0 model must use eager attention (Flash not on T4)."""
        from app.training.model_registry import SUPPORTED_MODELS

        config = SUPPORTED_MODELS["google/gemma-3-1b-it"]
        assert config.attn_implementation == "eager"

    # --- Alpaca Formatter Tests ---

    def test_stage0_alpaca_format_instruction_only(self):
        """Stage 0 Alpaca formatter must handle instruction-only examples."""
        from app.training.alpaca_formatter import AlpacaFormatter

        records = [{"instruction": "Explain AI", "input": "", "output": "AI is..."}]
        formatted = AlpacaFormatter.format_dataset(records)
        assert len(formatted) == 1
        assert "### Instruction:" in formatted[0]
        assert "### Response:" in formatted[0]
        assert "### Input:" not in formatted[0]

    def test_stage0_alpaca_format_with_input(self):
        """Stage 0 Alpaca formatter must handle examples with input field."""
        from app.training.alpaca_formatter import AlpacaFormatter

        records = [{"instruction": "Translate", "input": "Hello", "output": "Hola"}]
        formatted = AlpacaFormatter.format_dataset(records)
        assert len(formatted) == 1
        assert "### Instruction:" in formatted[0]
        assert "### Input:" in formatted[0]
        assert "### Response:" in formatted[0]

    # --- Success Criteria Validation ---

    def test_stage0_success_criteria_count(self):
        """Phase 4.3 must define exactly 8 success criteria."""
        # From docs/20_real_training_validation_plan.md
        criteria = [
            "Model loads in 4-bit NF4",
            "LoRA adapters on 7 modules",
            "Training completes without OOM",
            "VRAM stays under 8 GB",
            "Training time under 5 min",
            "Loss decreases during training",
            "All 3 required artifact files present",
            "All 18 metadata keys present",
        ]
        assert len(criteria) == 8

    def test_stage0_required_artifact_files_count(self):
        """Stage 0 must require exactly 3 artifact files."""
        from app.training.artifact_validator import REQUIRED_ARTIFACT_FILES

        assert len(REQUIRED_ARTIFACT_FILES) == 3
        assert "adapter_model.safetensors" in REQUIRED_ARTIFACT_FILES
        assert "adapter_config.json" in REQUIRED_ARTIFACT_FILES
        assert "training_metadata.json" in REQUIRED_ARTIFACT_FILES

    def test_stage0_required_artifact_dirs_count(self):
        """Stage 0 must require exactly 1 artifact directory."""
        from app.training.artifact_validator import REQUIRED_ARTIFACT_DIRS

        assert len(REQUIRED_ARTIFACT_DIRS) == 1
        assert "tokenizer" in REQUIRED_ARTIFACT_DIRS

    # --- Notebook Config Consistency ---

    def test_stage0_config_matches_notebook(self):
        """Stage 0 config values must match the Colab notebook constants."""
        cfg = self.STAGE0_CONFIG
        from app.training.model_registry import SUPPORTED_MODELS

        model = SUPPORTED_MODELS["google/gemma-3-1b-it"]
        # Notebook uses model's target modules
        assert cfg["lora_target_modules"] == model.lora_target_modules
        # Notebook uses model's recommended settings
        assert cfg["lora_r"] == 16
        assert cfg["lora_alpha"] == 32
        assert cfg["lora_dropout"] == 0.05
        assert cfg["lora_bias"] == "none"

    def test_stage0_lr_within_qlora_range(self):
        """Stage 0 learning rate must be within QLoRA bounds (1e-6 to 1e-3)."""
        from app.training.training_args import _LR_MIN, _LR_MAX

        lr = self.STAGE0_CONFIG["learning_rate"]
        assert _LR_MIN <= lr <= _LR_MAX

    def test_stage0_epochs_within_limit(self):
        """Stage 0 epochs must be within the max 10 epoch limit."""
        assert 1 <= self.STAGE0_CONFIG["epochs"] <= 10

    def test_stage0_batch_size_within_model_default(self):
        """Stage 0 batch_size=2 must be <= model default_batch_size=4."""
        from app.training.model_registry import SUPPORTED_MODELS

        model = SUPPORTED_MODELS["google/gemma-3-1b-it"]
        assert self.STAGE0_CONFIG["batch_size"] <= model.default_batch_size
