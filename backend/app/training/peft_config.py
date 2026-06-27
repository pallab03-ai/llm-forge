"""PEFT / LoRA configuration factory.

Creates LoraConfig for QLoRA fine-tuning with the following defaults:
    - r=16
    - lora_alpha=32
    - lora_dropout=0.05
    - bias="none"
    - task_type="CAUSAL_LM"
    - target_modules from the model registry
"""

from __future__ import annotations

from app.training.model_registry import ModelConfig


class PEFTConfigFactory:
    """Factory for creating LoraConfig instances for QLoRA."""

    # Default LoRA hyperparameters
    DEFAULT_R = 16
    DEFAULT_ALPHA = 32
    DEFAULT_DROPOUT = 0.05
    DEFAULT_BIAS = "none"

    @classmethod
    def create_lora_config(
        cls,
        model_config: ModelConfig,
        r: int = DEFAULT_R,
        lora_alpha: int = DEFAULT_ALPHA,
        lora_dropout: float = DEFAULT_DROPOUT,
        bias: str = DEFAULT_BIAS,
    ):
        """Create a LoraConfig for the given model.

        Args:
            model_config: ModelConfig containing target_modules for LoRA.
            r: LoRA rank (dimension of the low-rank matrices).
            lora_alpha: LoRA scaling factor.
            lora_dropout: Dropout probability for LoRA layers.
            bias: Bias type for LoRA layers ("none", "all", "lora_only").

        Returns:
            LoraConfig configured for causal language modeling with
            the model's target modules.
        """
        from peft import LoraConfig, TaskType

        return LoraConfig(
            r=r,
            lora_alpha=lora_alpha,
            lora_dropout=lora_dropout,
            bias=bias,
            task_type=TaskType.CAUSAL_LM,
            target_modules=model_config.lora_target_modules,
        )
