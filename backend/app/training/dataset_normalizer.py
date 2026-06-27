"""Dataset normalizer for converting various formats to Alpaca JSONL.

Normalizes CSV and JSON datasets into the Alpaca-format JSONL that
the QLoRA training engine consumes. Supported input formats:

- JSONL (pass-through with validation)
- JSON (array of objects → JSONL)
- CSV (column-mapped → JSONL)

All outputs conform to the Alpaca schema:
    {"instruction": str, "input": str, "output": str}
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from app.training.dataset_loader import DatasetLoader


class DatasetNormalizer:
    """Normalize datasets from various formats into Alpaca JSONL."""

    # CSV column name aliases for each Alpaca field
    INSTRUCTION_ALIASES: list[str] = ["instruction", "prompt", "question", "task", "query"]
    INPUT_ALIASES: list[str] = ["input", "context", "input_text", "background"]
    OUTPUT_ALIASES: list[str] = ["output", "response", "answer", "target", "completion"]

    @classmethod
    def normalize(cls, path: str | Path) -> list[dict[str, Any]]:
        """Auto-detect format and normalize to Alpaca JSONL records.

        Detects the file format from the extension:
            .jsonl → load and validate
            .json  → parse array, convert to records
            .csv   → column-map, convert to records

        Args:
            path: Path to the dataset file.

        Returns:
            List of dicts, each with instruction/input/output keys.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file format is unsupported or data is invalid.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset file not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix == ".jsonl":
            return cls._normalize_jsonl(file_path)
        elif suffix == ".json":
            return cls._normalize_json(file_path)
        elif suffix == ".csv":
            return cls._normalize_csv(file_path)
        else:
            raise ValueError(
                f"Unsupported dataset format: '{suffix}'. "
                "Supported formats: .jsonl, .json, .csv"
            )

    @classmethod
    def _normalize_jsonl(cls, path: Path) -> list[dict[str, Any]]:
        """Load and validate a JSONL file (pass-through with validation).

        Args:
            path: Path to the JSONL file.

        Returns:
            List of validated Alpaca-format records.

        Raises:
            ValueError: If any record fails Alpaca schema validation.
        """
        records = DatasetLoader.load_jsonl(path)
        errors = DatasetLoader.validate_alpaca_schema(records)
        if errors:
            raise ValueError(
                f"Alpaca schema validation failed:\n" + "\n".join(errors)
            )
        return records

    @classmethod
    def _normalize_json(cls, path: Path) -> list[dict[str, Any]]:
        """Load a JSON file (array of objects) and convert to Alpaca records.

        The JSON file must contain an array of objects. Each object
        is mapped to Alpaca format using column alias resolution.

        Args:
            path: Path to the JSON file.

        Returns:
            List of Alpaca-format records.

        Raises:
            ValueError: If the file is not a JSON array or mapping fails.
        """
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError(
                f"JSON file must contain an array at the top level, got {type(data).__name__}"
            )

        if len(data) == 0:
            raise ValueError(f"JSON array is empty: {path}")

        records = cls._map_records(data)
        errors = DatasetLoader.validate_alpaca_schema(records)
        if errors:
            raise ValueError(
                f"Alpaca schema validation failed after mapping:\n" + "\n".join(errors)
            )
        return records

    @classmethod
    def _normalize_csv(cls, path: Path) -> list[dict[str, Any]]:
        """Load a CSV file and column-map to Alpaca records.

        CSV columns are mapped to Alpaca fields using alias resolution.
        The first row must be a header row with column names.

        Args:
            path: Path to the CSV file.

        Returns:
            List of Alpaca-format records.

        Raises:
            ValueError: If column mapping fails or data is invalid.
        """
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ValueError(f"CSV file has no header row: {path}")

            rows = list(reader)

        if len(rows) == 0:
            raise ValueError(f"CSV file has no data rows: {path}")

        records = cls._map_records(rows)
        errors = DatasetLoader.validate_alpaca_schema(records)
        if errors:
            raise ValueError(
                f"Alpaca schema validation failed after mapping:\n" + "\n".join(errors)
            )
        return records

    @classmethod
    def _map_records(cls, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map record keys to Alpaca format using alias resolution.

        For each record, finds the best-matching column name for each
        Alpaca field (instruction, input, output) using the defined aliases.

        Args:
            records: List of dicts with potentially non-standard keys.

        Returns:
            List of dicts with standardized instruction/input/output keys.

        Raises:
            ValueError: If required fields (instruction, output) cannot be mapped.
        """
        if not records:
            return []

        # Resolve column mappings from the first record's keys
        available_keys = set(records[0].keys())
        instruction_key = cls._resolve_alias(available_keys, cls.INSTRUCTION_ALIASES, "instruction")
        input_key = cls._resolve_alias(available_keys, cls.INPUT_ALIASES, "input", required=False)
        output_key = cls._resolve_alias(available_keys, cls.OUTPUT_ALIASES, "output")

        mapped: list[dict[str, Any]] = []
        for record in records:
            mapped.append({
                "instruction": str(record.get(instruction_key, "")),
                "input": str(record.get(input_key, "")) if input_key else "",
                "output": str(record.get(output_key, "")),
            })
        return mapped

    @staticmethod
    def _resolve_alias(
        available_keys: set[str],
        aliases: list[str],
        field_name: str,
        required: bool = True,
    ) -> str | None:
        """Find the best matching column name from available keys.

        Checks aliases in priority order (first match wins).

        Args:
            available_keys: Set of available column names.
            aliases: List of alias names to check, in priority order.
            field_name: Name of the Alpaca field (for error messages).
            required: If True, raises ValueError when no alias matches.

        Returns:
            The matched key name, or None if not required and not found.

        Raises:
            ValueError: If required=True and no alias matches.
        """
        for alias in aliases:
            if alias in available_keys:
                return alias
        if required:
            raise ValueError(
                f"Cannot map '{field_name}' field. "
                f"Expected one of: {', '.join(aliases)}. "
                f"Available columns: {', '.join(sorted(available_keys))}"
            )
        return None
