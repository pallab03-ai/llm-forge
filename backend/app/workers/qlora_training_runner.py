"""QLoRA training runner for Phase 4.2.

This is a **synchronous** function executed by RQ workers.
RQ workers run in a separate process and cannot use async SQLAlchemy,
so we create a sync engine / session here (same pattern as mock_training_runner).

11-step pipeline:
1. Load job from database
2. Mark job as RUNNING (with started_at timestamp)
3. Load dataset (JSONL → HF Dataset)
4. Format dataset (Alpaca → ### Instruction / ### Response)
5. Load tokenizer
6. QLoRA setup (4-bit model + LoRA adapters)
7. Create SFTTrainer
8. Execute training
9. Save artifacts (adapter + tokenizer)
10. Generate metadata (training_metadata.json)
11. Validate artifacts

If anything goes wrong, the job is marked as FAILED with an
actionable error_message. CUDA OOM errors get a specific message.
"""

from __future__ import annotations

import json
import logging
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.training_job import TrainingJob, TrainingJobStatus
from app.training.alpaca_formatter import AlpacaFormatter
from app.training.artifact_validator import ArtifactValidator
from app.training.dataset_loader import DatasetLoader
from app.training.model_registry import get_model_config
from app.training.peft_config import PEFTConfigFactory
from app.training.qlora_config import QLoRAConfigFactory
from app.training.training_args import TrainingArgumentsFactory

from datasets import Dataset as HFDataset
from peft import get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTTrainer

import bitsandbytes
import peft
import torch
import transformers

logger = logging.getLogger(__name__)

# OOM error message per user specification
_OOM_ERROR_MESSAGE = "CUDA Out Of Memory. Try: - batch_size=2 - max_seq_length=1024"


# ---------------------------------------------------------------------------
# Sync database setup (RQ workers are synchronous)
# ---------------------------------------------------------------------------

_sync_engine = None
_SyncSessionLocal: sessionmaker | None = None


def _get_sync_session() -> Session:
    """Return a synchronous SQLAlchemy session.

    Uses ``settings.database_url_sync`` (psycopg2-style) because RQ
    workers are synchronous and cannot use asyncpg.
    """
    global _sync_engine, _SyncSessionLocal
    if _sync_engine is None:
        _sync_engine = create_engine(settings.database_url_sync)
        _SyncSessionLocal = sessionmaker(bind=_sync_engine)
    return _SyncSessionLocal()


# ---------------------------------------------------------------------------
# Training metadata generation
# ---------------------------------------------------------------------------


def _build_training_metadata(
    job: TrainingJob,
    dataset_rows: int,
    seed: int,
    training_duration: float | None = None,
) -> dict:
    """Build the training_metadata.json content.

    Includes all required fields per user specification:
    job_id, base_model, training_type, dataset_rows, epochs,
    batch_size, learning_rate, seed, torch_version,
    transformers_version, peft_version, bitsandbytes_version,
    python_version, platform, training_duration.
    """
    config = job.configuration  # dict with epochs, batch_size, etc.

    metadata = {
        "job_id": str(job.id),
        "base_model": job.base_model,
        "training_type": job.training_type.value,
        "dataset_rows": dataset_rows,
        "epochs": config.get("epochs", 3),
        "batch_size": config.get("batch_size", 4),
        "learning_rate": config.get("learning_rate", 2e-4),
        "lora_r": config.get("lora_r", 16),
        "lora_alpha": config.get("lora_alpha", 32),
        "lora_dropout": config.get("lora_dropout", 0.05),
        "seed": seed,
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "peft_version": peft.__version__,
        "bitsandbytes_version": bitsandbytes.__version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "training_duration": training_duration,
    }
    return metadata


# ---------------------------------------------------------------------------
# Artifact creation helpers
# ---------------------------------------------------------------------------


def _save_training_metadata(metadata: dict, artifact_dir: Path) -> None:
    """Write training_metadata.json to the artifact directory."""
    metadata_path = artifact_dir / "training_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    logger.info("Saved training_metadata.json", extra={"path": str(metadata_path)})


def _save_tokenizer(tokenizer, artifact_dir: Path) -> None:
    """Save tokenizer files to the artifact directory."""
    tokenizer_dir = artifact_dir / "tokenizer"
    tokenizer_dir.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(str(tokenizer_dir))
    logger.info("Saved tokenizer", extra={"path": str(tokenizer_dir)})


# ---------------------------------------------------------------------------
# Dataset path resolution
# ---------------------------------------------------------------------------


def _resolve_dataset_path(job: TrainingJob) -> Path:
    """Resolve the dataset JSONL file path from the job's dataset_version_id.

    The Dataset Service stores files under:
        LOCAL_STORAGE_PATH / datasets / {dataset_id} / {version_id} / data.jsonl

    Returns:
        Path to the JSONL dataset file.

    Raises:
        FileNotFoundError: If the dataset file does not exist.
    """
    dataset_path = (
        Path(settings.LOCAL_STORAGE_PATH)
        / "datasets"
        / str(job.dataset_id)
        / str(job.dataset_version_id)
        / "data.jsonl"
    )
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")
    return dataset_path


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def qlora_training_runner(job_id: str) -> dict:
    """Execute a QLoRA training job.

    Called by RQ with the job UUID as a string.

    Returns a dict summary for RQ result storage.
    """
    session = _get_sync_session()
    try:
        # ── Step 0: Validate job_id is a valid UUID ────────────────────
        try:
            job_uuid = UUID(job_id)
        except ValueError:
            raise ValueError(f"Invalid job_id (not a valid UUID): {job_id}")

        # ── Step 1: Load job ───────────────────────────────────────────
        job = session.get(TrainingJob, job_uuid)
        if job is None:
            raise ValueError(f"Training job not found: {job_id}")

        logger.info(
            "Starting QLoRA training",
            extra={"job_id": job_id, "base_model": job.base_model},
        )

        # ── Step 2: Mark RUNNING ────────────────────────────────────────
        job.status = TrainingJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        session.flush()

        # Resolve model config
        model_config = get_model_config(job.base_model)
        config = job.configuration  # dict: epochs, batch_size, learning_rate, max_seq_length

        # ── Step 3: Load dataset ───────────────────────────────────────
        dataset_path = _resolve_dataset_path(job)
        hf_dataset = DatasetLoader.load_dataset(dataset_path)

        dataset_rows = len(hf_dataset)
        logger.info(
            "Loaded dataset",
            extra={"job_id": job_id, "dataset_rows": dataset_rows},
        )

        # ── Step 4: Format dataset ─────────────────────────────────────
        records = DatasetLoader.load_jsonl(dataset_path)
        formatted_texts = AlpacaFormatter.format_dataset(records)

        # ── Step 5: Load tokenizer ─────────────────────────────────────
        tokenizer = AutoTokenizer.from_pretrained(
            model_config.hf_model_id,
            trust_remote_code=True,
        )
        # Set pad token if specified in model config
        if model_config.special_tokens.get("pad_token"):
            tokenizer.pad_token = model_config.special_tokens["pad_token"]
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token_id = tokenizer.eos_token_id

        # ── Step 6: QLoRA setup ────────────────────────────────────────
        bnb_config = QLoRAConfigFactory.create_bnb_config()

        model = AutoModelForCausalLM.from_pretrained(
            model_config.hf_model_id,
            quantization_config=bnb_config,
            device_map="auto",
            attn_implementation=model_config.attn_implementation,
            trust_remote_code=True,
        )

        # Prepare model for k-bit training
        model = prepare_model_for_kbit_training(model)

        # Apply LoRA adapters
        lora_config = PEFTConfigFactory.create_lora_config(model_config)
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

        # ── Step 7: Create SFTTrainer ──────────────────────────────────

        # Prepare artifact directory
        artifact_dir = Path(settings.LOCAL_STORAGE_PATH) / "artifacts" / str(job.id)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # Create HuggingFace Dataset from formatted texts
        train_dataset = HFDataset.from_dict({"text": formatted_texts})

        # Build training arguments
        seed = config.get("seed", 42)
        training_args = TrainingArgumentsFactory.create_training_args(
            job_id=job_id,
            output_dir=str(artifact_dir),
            epochs=config.get("epochs", 3),
            batch_size=config.get("batch_size", 4),
            learning_rate=config.get("learning_rate", 2e-4),
            max_seq_length=config.get("max_seq_length", 2048),
            seed=seed,
        )

        trainer = SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            processing_class=tokenizer,
        )

        # ── Step 8: Execute training ──────────────────────────────────
        logger.info("Starting training", extra={"job_id": job_id})
        training_start = datetime.now(timezone.utc)
        trainer.train()
        training_end = datetime.now(timezone.utc)
        training_duration = (training_end - training_start).total_seconds()

        # ── Step 9: Save artifacts ─────────────────────────────────────
        # Save adapter weights and config
        trainer.model.save_pretrained(str(artifact_dir))

        # Save tokenizer
        _save_tokenizer(tokenizer, artifact_dir)

        logger.info(
            "Artifacts saved",
            extra={"job_id": job_id, "artifact_dir": str(artifact_dir)},
        )

        # ── Step 10: Generate metadata ─────────────────────────────────
        metadata = _build_training_metadata(job, dataset_rows, seed, training_duration)
        _save_training_metadata(metadata, artifact_dir)

        logger.info(
            "Training metadata generated",
            extra={"job_id": job_id},
        )

        # ── Step 11: Validate artifacts ────────────────────────────────
        ArtifactValidator.validate_artifact_dir(artifact_dir)
        ArtifactValidator.validate_training_metadata(
            artifact_dir / "training_metadata.json"
        )

        # ── Step 12: Mark COMPLETED ────────────────────────────────────
        job.status = TrainingJobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.artifact_path = str(artifact_dir)
        session.flush()

        logger.info(
            "Job completed successfully",
            extra={"job_id": job_id},
        )

        return {
            "job_id": job_id,
            "status": "completed",
            "artifact_dir": str(artifact_dir),
            "dataset_rows": dataset_rows,
        }

    except RuntimeError as exc:
        # Handle CUDA OOM specifically — torch.cuda.OutOfMemoryError
        # is a subclass of RuntimeError, so catching RuntimeError covers it.
        # We detect OOM by checking the error message string.
        oom_indicators = [
            "CUDA out of memory",
            "OutOfMemoryError",
            "out of memory",
        ]
        error_msg = str(exc)
        is_oom = any(indicator in error_msg for indicator in oom_indicators)

        if is_oom:
            logger.error(
                "CUDA OOM during training",
                extra={"job_id": job_id},
                exc_info=True,
            )
            _mark_job_failed(session, job_id, _OOM_ERROR_MESSAGE)
            return {"job_id": job_id, "status": "failed", "error": _OOM_ERROR_MESSAGE}
        else:
            logger.error(
                "Runtime error during training",
                extra={"job_id": job_id},
                exc_info=True,
            )
            _mark_job_failed(session, job_id, error_msg)
            return {"job_id": job_id, "status": "failed", "error": error_msg}

    except Exception as exc:
        logger.error(
            "Training job failed",
            extra={"job_id": job_id},
            exc_info=True,
        )
        _mark_job_failed(session, job_id, str(exc))
        return {"job_id": job_id, "status": "failed", "error": str(exc)}

    finally:
        session.close()


def _mark_job_failed(session: Session, job_id: str, error_message: str) -> None:
    """Mark a training job as FAILED with an error message.

    This is a best-effort operation — if the database update fails,
    we log the error but don't raise (the job is already failed).
    """
    try:
        job = session.get(TrainingJob, UUID(job_id))
        if job is not None:
            job.status = TrainingJobStatus.FAILED
            job.error_message = error_message
            job.completed_at = datetime.now(timezone.utc)
            session.flush()
    except Exception:
        logger.error(
            "Failed to mark job as FAILED in database",
            extra={"job_id": job_id, "error_message": error_message},
            exc_info=True,
        )
