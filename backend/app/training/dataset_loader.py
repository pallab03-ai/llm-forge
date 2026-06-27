"""Dataset loader for Alpaca-format JSONL files (instruction/output)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DatasetLoader:
    REQUIRED_KEYS: set[str] = {"instruction", "output"}

    @staticmethod
    def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset file not found: {file_path}")

        records: list[dict[str, Any]] = []
        with file_path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
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
        errors: list[str] = []
        for idx, record in enumerate(records):
            missing = cls.REQUIRED_KEYS - set(record.keys())
            if missing:
                errors.append(
                    f"Record {idx} missing required keys: {', '.join(sorted(missing))}"
                )
        return errors

    @classmethod
    def load_dataset(cls, path: str | Path) -> "datasets.Dataset":
        from datasets import Dataset as HFDataset

        records = cls.load_jsonl(path)
        errors = cls.validate_alpaca_schema(records)
        if errors:
            raise ValueError(
                f"Alpaca schema validation failed:\n" + "\n".join(errors)
            )
        return HFDataset.from_list(records)
