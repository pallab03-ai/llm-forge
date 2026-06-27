"""Alpaca prompt formatter for instruction fine-tuning.

Converts Alpaca-format records (instruction, input, output) into
formatted strings using the standard Alpaca prompt format:

    ### Instruction:
    {instruction}

    ### Input:
    {input}

    ### Response:
    {output}

This is the text that gets tokenized and fed to the SFTTrainer.
"""

from __future__ import annotations

from typing import Any

from app.training.model_registry import ModelConfig


class AlpacaFormatter:
    """Format Alpaca records using the standard Alpaca prompt format."""

    @staticmethod
    def format_example(
        record: dict[str, Any],
        model_config: ModelConfig | None = None,
    ) -> str:
        """Format a single Alpaca record using ### Instruction / ### Response format.

        Args:
            record: Dict with at least 'instruction', 'input', 'output' keys.
            model_config: (Unused, kept for backward compatibility.)

        Returns:
            Formatted string ready for tokenization.

        Raises:
            KeyError: If the record is missing required keys.
        """
        instruction = record["instruction"]
        input_text = record.get("input", "")
        output = record["output"]

        if input_text:
            return (
                f"### Instruction:\n{instruction}\n\n"
                f"### Input:\n{input_text}\n\n"
                f"### Response:\n{output}"
            )
        else:
            return (
                f"### Instruction:\n{instruction}\n\n"
                f"### Response:\n{output}"
            )

    @classmethod
    def format_dataset(
        cls,
        records: list[dict[str, Any]],
        model_config: ModelConfig | None = None,
    ) -> list[str]:
        """Format all records in a dataset.

        Args:
            records: List of Alpaca-format record dicts.
            model_config: (Unused, kept for backward compatibility.)

        Returns:
            List of formatted strings, one per record.
        """
        return [cls.format_example(rec, model_config) for rec in records]
