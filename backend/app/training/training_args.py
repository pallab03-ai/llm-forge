"""TRL/Transformers TrainingArguments factory for QLoRA fine-tuning.

Applies a narrower learning-rate range (1e-6 to 1e-3) than the shared
TrainingConfig model.
"""

from __future__ import annotations

from pathlib import Path

_LR_MIN = 1e-6
_LR_MAX = 1e-3
_LR_DEFAULT = 2e-4


class TrainingArgumentsFactory:
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
        from trl import SFTConfig

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
