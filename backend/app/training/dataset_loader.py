"""Dataset loader for Alpaca-format JSONL files.

Loads JSONL files produced by the Dataset Service, validates that
each record conforms to the Alpaca schema (instruction, input, output),
and provides basic counting utilities.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DatasetLoader:
    """Load and validate Alpaca-format JSONL datasets."""

    REQUIRED_KEYS: set[str] = {"instruction", "output"}
    OPTIONAL_KEYS: set[str] = {"input"}

    @staticmethod
    def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
        """Load a JSONL file and return a list of record dicts.

        Args:
            path: Path to the JSONL file (string or Path).

        Returns:
            List of dicts, each with at least instruction/input/output keys.

        Raises:
            FileNotFoundError: If the file does not exist.
            json.JSONDecodeError: If any line is not valid JSON.
            ValueError: If the file is empty.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset file not found: {file_path}")

        records: list[dict[str, Any]] = []
        with file_path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue  # skip blank lines
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise json.JSONDecodeError(
                        f"Invalid JSON on line {line_num}: {exc.msg}",
                        exc.doc,
                        exc.pos,
                    ) from exc
                records.append(record)

        if not records:
            raise ValueError(f"Dataset file is empty: {file_path}")

        return records

    @classmethod
    def validate_alpaca_schema(cls, records: list[dict[str, Any]]) -> list[str]:
        """Validate that all records contain the required Alpaca keys.

        Required keys: instruction, output.
        Optional keys: input (defaults to empty string if absent).

        Args:
            records: List of record dicts to validate.

        Returns:
            List of error messages (empty if all records are valid).
        """
        errors: list[str] = []
        for idx, record in enumerate(records):
            missing = cls.REQUIRED_KEYS - set(record.keys())
            if missing:
                errors.append(
                    f"Record {idx} missing required keys: {', '.join(sorted(missing))}"
                )
        return errors

    @staticmethod
    def count_examples(records: list[dict[str, Any]]) -> int:
        """Return the number of examples in the record list.

        Args:
            records: List of record dicts.

        Returns:
            Integer count of examples.
        """
        return len(records)

    @classmethod
    def load_dataset(cls, path: str | Path) -> "datasets.Dataset":
        """Load a JSONL file and return a HuggingFace Dataset.

        This is the preferred entry point for the training pipeline,
        which expects an HF Dataset object for SFTTrainer.

        Args:
            path: Path to the JSONL file (string or Path).

        Returns:
            A HuggingFace ``datasets.Dataset`` object with
            instruction/input/output columns.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is empty or records fail schema validation.
        """
        from datasets import Dataset as HFDataset

        records = cls.load_jsonl(path)
        errors = cls.validate_alpaca_schema(records)
        if errors:
            raise ValueError(
                f"Alpaca schema validation failed:\n" + "\n".join(errors)
            )
        return HFDataset.from_list(records)
