"""Training arguments factory for QLoRA fine-tuning.

Creates TRL/Transformers TrainingArguments with QLoRA-specific defaults.
Applies narrower learning-rate validation (1e-6 to 1e-3) than the
shared TrainingConfig model (1e-7 to 1.0) per user specification.
"""

from __future__ import annotations

from pathlib import Path

# Narrower learning-rate bounds for QLoRA (user specification)
_LR_MIN = 1e-6
_LR_MAX = 1e-3
_LR_DEFAULT = 2e-4


class TrainingArgumentsFactory:
    """Factory for creating SFTConfig (TrainingArguments) for QLoRA."""

    @staticmethod
    def create_training_args(
        job_id: str,
        output_dir: str | Path,
        epochs: int = 3,
        batch_size: int = 4,
        learning_rate: float = _LR_DEFAULT,
        max_seq_length: int = 2048,
        gradient_accumulation_steps: int = 4,
        seed: int = 42,
    ):
        """Create SFTConfig for QLoRA training.

        Args:
            job_id: Training job ID (used in run name).
            output_dir: Directory for saving artifacts.
            epochs: Number of training epochs (1-10).
            batch_size: Per-device batch size (1-64).
            learning_rate: Peak learning rate (1e-6 to 1e-3).
            max_seq_length: Maximum sequence length (64-8192).
            gradient_accumulation_steps: Gradient accumulation steps.
            seed: Random seed for reproducibility.

        Returns:
            SFTConfig with QLoRA-optimized defaults.

        Raises:
            ValueError: If learning_rate is outside the QLoRA range.
        """
        from trl import SFTConfig

        # Validate narrower QLoRA learning-rate bounds
        if not (_LR_MIN <= learning_rate <= _LR_MAX):
            raise ValueError(
                f"QLoRA learning rate must be between {_LR_MIN} and {_LR_MAX}, "
                f"got {learning_rate}"
            )

        return SFTConfig(
            output_dir=str(output_dir),
            run_name=f"qlora-{job_id}",
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            learning_rate=learning_rate,
            max_length=max_seq_length,
            gradient_accumulation_steps=gradient_accumulation_steps,
            lr_scheduler_type="cosine",
            warmup_ratio=0.03,
            logging_steps=10,
            fp16=True,
            gradient_checkpointing=True,
            optim="paged_adamw_8bit",
            save_strategy="no",
            report_to="none",
            seed=seed,
            max_grad_norm=1.0,
        )
