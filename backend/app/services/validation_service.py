"""Dataset validation: schema, duplicate detection, basic stats.

Duplicate detection is within-file only.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.models.dataset import DatasetFormat, DatasetType


@dataclass
class ValidationResult:
    is_valid: bool = True
    record_count: int = 0
    duplicate_count: int = 0
    errors: list[str] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)

    def add_error(self, error: str) -> None:
        self.is_valid = False
        self.errors.append(error)


MAX_FILE_SIZE_BYTES = 1_073_741_824  # 1 GB
MAX_RECORDS = 10_000_000  # 10 million


class ValidationService:
    _REQUIRED_COLUMNS: dict[DatasetType, set[str]] = {
        DatasetType.INSTRUCTION_TUNING: {"instruction", "response"},
        DatasetType.CHAT: {"messages"},
        DatasetType.QA: {"question", "answer"},
    }

    async def validate(
        self,
        file_path: Path,
        format: DatasetFormat,
        dataset_type: DatasetType,
    ) -> ValidationResult:
        result = ValidationResult()

        if not file_path.exists():
            result.add_error(f"File not found: {file_path}")
            return result

        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            result.add_error(
                f"File size {file_size} bytes exceeds maximum "
                f"{MAX_FILE_SIZE_BYTES} bytes (1 GB)."
            )
            return result

        if file_size == 0:
            result.add_error("File is empty.")
            return result

        try:
            if format == DatasetFormat.CSV:
                records = self._parse_csv(file_path)
            elif format == DatasetFormat.JSON:
                records = self._parse_json(file_path)
            elif format == DatasetFormat.JSONL:
                records = self._parse_jsonl(file_path)
            else:
                result.add_error(f"Unsupported format: {format}")
                return result
        except Exception as exc:
            result.add_error(f"Failed to parse file: {exc}")
            return result

        if not records:
            result.add_error("No records found in file.")
            return result

        if len(records) > MAX_RECORDS:
            result.add_error(
                f"Record count {len(records)} exceeds maximum "
                f"{MAX_RECORDS} (10 million)."
            )
            return result

        result.record_count = len(records)

        required = self._REQUIRED_COLUMNS.get(dataset_type, set())
        if required:
            schema_errors = self._validate_schema(records, required)
            result.errors.extend(schema_errors)

        result.duplicate_count = self._count_duplicates(records)
        result.statistics = self._compute_statistics(records, dataset_type)

        result.is_valid = len(result.errors) == 0
        return result

    def _parse_csv(self, file_path: Path) -> list[dict]:
        records: list[dict] = []
        with file_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                records.append(dict(row))
        return records

    def _parse_json(self, file_path: Path) -> list[dict]:
        with file_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError("JSON file must contain a top-level array.")
        return data

    def _parse_jsonl(self, file_path: Path) -> list[dict]:
        records: list[dict] = []
        with file_path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON on line {line_no}: {exc}"
                    ) from exc
        return records

    def _validate_schema(
        self, records: list[dict], required_columns: set[str]
    ) -> list[str]:
        errors: list[str] = []
        for idx, record in enumerate(records):
            missing = required_columns - set(record.keys())
            if missing:
                errors.append(
                    f"Record {idx}: missing required field(s): "
                    f"{', '.join(sorted(missing))}"
                )
        return errors

    def _count_duplicates(self, records: list[dict]) -> int:
        seen: set[str] = set()
        duplicates = 0
        for record in records:
            # Sorted JSON for stable hashing.
            key = json.dumps(record, sort_keys=True, ensure_ascii=False)
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)
        return duplicates

    def _compute_statistics(
        self, records: list[dict], dataset_type: DatasetType
    ) -> dict:
        stats: dict = {
            "total_records": len(records),
        }

        if dataset_type == DatasetType.INSTRUCTION_TUNING:
            stats["avg_instruction_length"] = self._avg_field_length(
                records, "instruction"
            )
            stats["avg_response_length"] = self._avg_field_length(
                records, "response"
            )
        elif dataset_type == DatasetType.QA:
            stats["avg_question_length"] = self._avg_field_length(
                records, "question"
            )
            stats["avg_answer_length"] = self._avg_field_length(
                records, "answer"
            )
        elif dataset_type == DatasetType.CHAT:
            stats["avg_messages_count"] = self._avg_messages_count(records)

        return stats

    def _avg_field_length(
        self, records: list[dict], field: str
    ) -> float:
        lengths = [
            len(str(record.get(field, ""))) for record in records
        ]
        if not lengths:
            return 0.0
        return round(sum(lengths) / len(lengths), 2)

    def _avg_messages_count(self, records: list[dict]) -> float:
        counts = []
        for record in records:
            messages = record.get("messages", [])
            if isinstance(messages, list):
                counts.append(len(messages))
            else:
                counts.append(0)
        if not counts:
            return 0.0
        return round(sum(counts) / len(counts), 2)