"""Artifact validator for QLoRA training outputs.

Validates that the training run produced all required artifacts:
    1. adapter_model.safetensors  — LoRA weight file
    2. adapter_config.json        — PEFT adapter configuration
    3. training_metadata.json     — Job metadata (versions, hyperparams)
    4. tokenizer/                 — Tokenizer files directory

Also validates that training_metadata.json contains all required fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Required files in the artifact directory
REQUIRED_ARTIFACT_FILES: list[str] = [
    "adapter_model.safetensors",
    "adapter_config.json",
    "training_metadata.json",
]

# Required directory
REQUIRED_ARTIFACT_DIRS: list[str] = [
    "tokenizer",
]

# Required keys in training_metadata.json
REQUIRED_METADATA_KEYS: list[str] = [
    "job_id",
    "base_model",
    "training_type",
    "dataset_rows",
    "epochs",
    "batch_size",
    "learning_rate",
    "lora_r",
    "lora_alpha",
    "lora_dropout",
    "seed",
    "torch_version",
    "transformers_version",
    "peft_version",
    "bitsandbytes_version",
    "python_version",
    "platform",
    "training_duration",
]


class ArtifactValidator:
    """Validate QLoRA training artifact directories."""

    @staticmethod
    def validate_artifact_dir(artifact_dir: str | Path) -> bool:
        """Validate that all required artifact files exist and are non-empty.

        Args:
            artifact_dir: Path to the artifact directory (e.g. artifacts/{job_id}/).

        Returns:
            True if all required files and directories exist and are non-empty.

        Raises:
            FileNotFoundError: If the artifact directory or any required file is missing.
            ValueError: If any required file is empty.
        """
        artifact_path = Path(artifact_dir)

        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact directory not found: {artifact_path}")

        # Check required files
        for filename in REQUIRED_ARTIFACT_FILES:
            filepath = artifact_path / filename
            if not filepath.exists():
                raise FileNotFoundError(f"Required artifact missing: {filepath}")
            if filepath.stat().st_size == 0:
                raise ValueError(f"Required artifact is empty: {filepath}")

        # Check required directories
        for dirname in REQUIRED_ARTIFACT_DIRS:
            dirpath = artifact_path / dirname
            if not dirpath.exists() or not dirpath.is_dir():
                raise FileNotFoundError(f"Required artifact directory missing: {dirpath}")
            # Directory must contain at least one file
            if not any(dirpath.iterdir()):
                raise ValueError(f"Required artifact directory is empty: {dirpath}")

        return True

    @staticmethod
    def validate_training_metadata(metadata_path: str | Path) -> bool:
        """Validate that training_metadata.json contains all required keys.

        Args:
            metadata_path: Path to the training_metadata.json file.

        Returns:
            True if all required keys are present.

        Raises:
            FileNotFoundError: If the metadata file does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
            ValueError: If any required key is missing.
        """
        filepath = Path(metadata_path)

        if not filepath.exists():
            raise FileNotFoundError(f"Metadata file not found: {filepath}")

        with filepath.open("r", encoding="utf-8") as f:
            metadata: dict[str, Any] = json.load(f)

        missing_keys = [key for key in REQUIRED_METADATA_KEYS if key not in metadata]
        if missing_keys:
            raise ValueError(
                f"Training metadata missing required keys: {', '.join(sorted(missing_keys))}"
            )

        return True
