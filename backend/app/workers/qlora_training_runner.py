"""QLoRA training runner executed by RQ workers.

RQ workers run synchronously, so we create a sync SQLAlchemy engine
here rather than using the async one. CUDA OOM errors get a specific
message so users know what to change.
"""

from __future__ import annotations

import json
import logging
import platform
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
from app.training.training_args import TrainingArgumentsFactory

from datasets import Dataset as HFDataset
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTTrainer

import bitsandbytes
import peft
import torch
import transformers

logger = logging.getLogger(__name__)

_OOM_ERROR_MESSAGE = "CUDA Out Of Memory. Try: - batch_size=2 - max_seq_length=1024"

_sync_engine = None
_SyncSessionLocal: sessionmaker | None = None


def _get_sync_session() -> Session:
    global _sync_engine, _SyncSessionLocal
    if _sync_engine is None:
        _sync_engine = create_engine(settings.database_url_sync)
        _SyncSessionLocal = sessionmaker(bind=_sync_engine)
    return _SyncSessionLocal()


def _build_training_metadata(
    job: TrainingJob,
    dataset_rows: int,
    seed: int,
    training_duration: float | None = None,
) -> dict:
    config = job.configuration
    return {
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


def _save_training_metadata(metadata: dict, artifact_dir: Path) -> None:
    metadata_path = artifact_dir / "training_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    logger.info("Saved training_metadata.json", extra={"path": str(metadata_path)})


def _save_tokenizer(tokenizer, artifact_dir: Path) -> None:
    tokenizer_dir = artifact_dir / "tokenizer"
    tokenizer_dir.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(str(tokenizer_dir))
    logger.info("Saved tokenizer", extra={"path": str(tokenizer_dir)})


def _resolve_dataset_path(job: TrainingJob) -> Path:
    # Dataset Service layout:
    #   LOCAL_STORAGE_PATH/datasets/{dataset_id}/{version_id}/data.jsonl
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


_oom_indicators = (
    "CUDA out of memory",
    "OutOfMemoryError",
    "out of memory",
)


def qlora_training_runner(job_id: str) -> dict:
    session = _get_sync_session()
    try:
        try:
            job_uuid = UUID(job_id)
        except ValueError:
            raise ValueError(f"Invalid job_id (not a valid UUID): {job_id}")

        job = session.get(TrainingJob, job_uuid)
        if job is None:
            raise ValueError(f"Training job not found: {job_id}")

        logger.info(
            "Starting QLoRA training",
            extra={"job_id": job_id, "base_model": job.base_model},
        )

        job.status = TrainingJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        session.flush()

        model_config = get_model_config(job.base_model)
        config = job.configuration

        dataset_path = _resolve_dataset_path(job)
        hf_dataset = DatasetLoader.load_dataset(dataset_path)
        dataset_rows = len(hf_dataset)
        logger.info(
            "Loaded dataset",
            extra={"job_id": job_id, "dataset_rows": dataset_rows},
        )

        records = DatasetLoader.load_jsonl(dataset_path)
        formatted_texts = AlpacaFormatter.format_dataset(records)

        tokenizer = AutoTokenizer.from_pretrained(
            model_config.hf_model_id,
            trust_remote_code=True,
        )
        if model_config.special_tokens.get("pad_token"):
            tokenizer.pad_token = model_config.special_tokens["pad_token"]
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token_id = tokenizer.eos_token_id

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_config.hf_model_id,
            quantization_config=bnb_config,
            device_map="auto",
            attn_implementation=model_config.attn_implementation,
            trust_remote_code=True,
        )
        model = prepare_model_for_kbit_training(model)

        lora_config = LoraConfig(
            r=config.get("lora_r", 16),
            lora_alpha=config.get("lora_alpha", 32),
            lora_dropout=config.get("lora_dropout", 0.05),
            bias="none",
            task_type=TaskType.CAUSAL_LM,
            target_modules=model_config.lora_target_modules,
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

        artifact_dir = Path(settings.LOCAL_STORAGE_PATH) / "artifacts" / str(job.id)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        train_dataset = HFDataset.from_dict({"text": formatted_texts})

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

        logger.info("Starting training", extra={"job_id": job_id})
        training_start = datetime.now(timezone.utc)
        trainer.train()
        training_duration = (
            datetime.now(timezone.utc) - training_start
        ).total_seconds()

        trainer.model.save_pretrained(str(artifact_dir))
        _save_tokenizer(tokenizer, artifact_dir)
        logger.info(
            "Artifacts saved",
            extra={"job_id": job_id, "artifact_dir": str(artifact_dir)},
        )

        metadata = _build_training_metadata(job, dataset_rows, seed, training_duration)
        _save_training_metadata(metadata, artifact_dir)
        logger.info("Training metadata generated", extra={"job_id": job_id})

        ArtifactValidator.validate_artifact_dir(artifact_dir)
        ArtifactValidator.validate_training_metadata(
            artifact_dir / "training_metadata.json"
        )

        job.status = TrainingJobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.artifact_path = str(artifact_dir)
        session.flush()

        logger.info("Job completed successfully", extra={"job_id": job_id})

        return {
            "job_id": job_id,
            "status": "completed",
            "artifact_dir": str(artifact_dir),
            "dataset_rows": dataset_rows,
        }

    except RuntimeError as exc:
        # torch.cuda.OutOfMemoryError subclasses RuntimeError; detect
        # by message since the class isn't always picklable.
        error_msg = str(exc)
        is_oom = any(indicator in error_msg for indicator in _oom_indicators)

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
    # Best-effort: if this fails, log it. The job is already failed.
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
