"""Alpaca prompt formatter.

Each record is rendered as::

    ### Instruction:
    {instruction}

    ### Input:
    {input}    (optional)

    ### Response:
    {output}
"""

from __future__ import annotations

from typing import Any


class AlpacaFormatter:
    @staticmethod
    def format_example(record: dict[str, Any]) -> str:
        instruction = record["instruction"]
        input_text = record.get("input", "")
        output = record["output"]

        if input_text:
            return (
                f"### Instruction:\n{instruction}\n\n"
                f"### Input:\n{input_text}\n\n"
                f"### Response:\n{output}"
            )
        return (
            f"### Instruction:\n{instruction}\n\n"
            f"### Response:\n{output}"
        )

    @classmethod
    def format_dataset(cls, records: list[dict[str, Any]]) -> list[str]:
        return [cls.format_example(rec) for rec in records]
