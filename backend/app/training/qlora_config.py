"""QLoRA configuration factory.

Creates BitsAndBytesConfig for 4-bit NF4 quantization as required
by the QLoRA training pipeline.

Key settings (per user specification):
    - load_in_4bit=True
    - bnb_4bit_quant_type="nf4"
    - bnb_4bit_compute_dtype=torch.bfloat16
    - bnb_4bit_use_double_quant=True
"""

from __future__ import annotations


class QLoRAConfigFactory:
    """Factory for creating BitsAndBytesConfig instances for QLoRA."""

    @staticmethod
    def create_bnb_config():
        """Create a BitsAndBytesConfig for 4-bit NF4 QLoRA quantization.

        Returns:
            BitsAndBytesConfig with the following settings:
                - load_in_4bit=True
                - bnb_4bit_quant_type="nf4"
                - bnb_4bit_compute_dtype=torch.float16
                - bnb_4bit_use_double_quant=True
        """
        import torch
        from transformers import BitsAndBytesConfig

        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
