"""Artifact validator for QLoRA training outputs.

Required artifacts: adapter_model.safetensors, adapter_config.json,
training_metadata.json, and a tokenizer/ directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_ARTIFACT_FILES: list[str] = [
    "adapter_model.safetensors",
    "adapter_config.json",
    "training_metadata.json",
]

REQUIRED_ARTIFACT_DIRS: list[str] = [
    "tokenizer",
]

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
    @staticmethod
    def validate_artifact_dir(artifact_dir: str | Path) -> bool:
        artifact_path = Path(artifact_dir)

        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact directory not found: {artifact_path}")

        for filename in REQUIRED_ARTIFACT_FILES:
            filepath = artifact_path / filename
            if not filepath.exists():
                raise FileNotFoundError(f"Required artifact missing: {filepath}")
            if filepath.stat().st_size == 0:
                raise ValueError(f"Required artifact is empty: {filepath}")

        for dirname in REQUIRED_ARTIFACT_DIRS:
            dirpath = artifact_path / dirname
            if not dirpath.exists() or not dirpath.is_dir():
                raise FileNotFoundError(f"Required artifact directory missing: {dirpath}")
            if not any(dirpath.iterdir()):
                raise ValueError(f"Required artifact directory is empty: {dirpath}")

        return True

    @staticmethod
    def validate_training_metadata(metadata_path: str | Path) -> bool:
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
