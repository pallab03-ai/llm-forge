"""Evaluation service: run an adapter against a dataset and persist metrics.

Synchronous and simple (MVP). Heavy ML imports are lazy so the module
loads cleanly in test environments. Tests override
``_generate_predictions`` to stub out the inference seam.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

from app.models.evaluation import Evaluation, EvaluationStatus
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.evaluation import (
    EvaluationCreateRequest,
    EvaluationListResponse,
    EvaluationResponse,
)
from app.services import metrics as metrics_module


class EvaluationError(Exception):
    code = "EVALUATION_ERROR"
    http_status = 400


class EvaluationNotFoundError(EvaluationError):
    code = "EVALUATION_NOT_FOUND"
    http_status = 404

    def __init__(self, evaluation_id: UUID) -> None:
        self.evaluation_id = evaluation_id
        super().__init__(f"Evaluation not found: {evaluation_id}")


class EvaluationAccessDeniedError(EvaluationError):
    code = "EVALUATION_ACCESS_DENIED"
    http_status = 403

    def __init__(self, evaluation_id: UUID) -> None:
        self.evaluation_id = evaluation_id
        super().__init__(f"Access to evaluation {evaluation_id} is denied.")


class ModelNotFoundError(EvaluationError):
    code = "MODEL_NOT_FOUND"
    http_status = 404

    def __init__(self, model_id: UUID) -> None:
        self.model_id = model_id
        super().__init__(f"Trained model not found: {model_id}")


class ModelNotReadyError(EvaluationError):
    code = "MODEL_NOT_READY"
    http_status = 409

    def __init__(self, model_id: UUID) -> None:
        self.model_id = model_id
        super().__init__(
            f"Trained model {model_id} has no adapter artifact "
            "(training job not completed or no artifact_path)."
        )


class DatasetNotFoundError(EvaluationError):
    code = "DATASET_NOT_FOUND"
    http_status = 404

    def __init__(self, dataset_id: UUID) -> None:
        self.dataset_id = dataset_id
        super().__init__(f"Dataset not found or not accessible: {dataset_id}")


class DatasetVersionNotFoundError(EvaluationError):
    code = "DATASET_VERSION_NOT_FOUND"
    http_status = 404

    def __init__(self, version_id: UUID) -> None:
        self.version_id = version_id
        super().__init__(f"Dataset version not found: {version_id}")


class AdapterNotFoundError(EvaluationError):
    code = "ADAPTER_NOT_FOUND"
    http_status = 404

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Adapter artifact not found at path: {path}")


class MetricComputationError(EvaluationError):
    code = "METRIC_COMPUTATION_FAILED"
    http_status = 422

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Metric computation failed: {detail}")


class EvaluationService:
    def __init__(
        self,
        evaluation_repo: EvaluationRepository,
        training_job_repo: TrainingJobRepository,
        dataset_repo: DatasetRepository,
    ) -> None:
        self._evals = evaluation_repo
        self._jobs = training_job_repo
        self._datasets = dataset_repo

    async def create_evaluation(
        self,
        *,
        user_id: UUID,
        request: EvaluationCreateRequest,
    ) -> EvaluationResponse:
        job = await self._jobs.get_by_id(request.model_id)
        if job is None or job.user_id != user_id:
            raise ModelNotFoundError(request.model_id)
        if job.artifact_path is None:
            raise ModelNotReadyError(request.model_id)

        dataset = await self._datasets.get_by_id_and_owner(
            request.dataset_id, user_id
        )
        if dataset is None:
            raise DatasetNotFoundError(request.dataset_id)
        version_exists = any(
            v.id == request.dataset_version_id for v in dataset.versions
        )
        if not version_exists:
            raise DatasetVersionNotFoundError(request.dataset_version_id)

        evaluation = Evaluation(
            user_id=user_id,
            dataset_id=request.dataset_id,
            dataset_version_id=request.dataset_version_id,
            model_id=request.model_id,
            status=EvaluationStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        evaluation = await self._evals.create(evaluation)
        await self._evals.commit()

        try:
            metrics = await self._run_evaluation(
                evaluation_id=evaluation.id,
                artifact_path=job.artifact_path,
                dataset_version_id=request.dataset_version_id,
            )
        except Exception as exc:
            await self._evals.save_error(evaluation.id, str(exc))
            await self._evals.commit()
            # Re-raise domain errors as-is; wrap unknown errors.
            if isinstance(exc, EvaluationError):
                raise
            raise MetricComputationError(str(exc)) from exc

        await self._evals.save_metrics(evaluation.id, **metrics)
        await self._evals.update_status(
            evaluation.id,
            EvaluationStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
        )
        await self._evals.commit()

        refreshed = await self._evals.get_by_id(evaluation.id)
        assert refreshed is not None
        return EvaluationResponse.model_validate(refreshed)

    async def _run_evaluation(
        self,
        *,
        evaluation_id: UUID,
        artifact_path: str,
        dataset_version_id: UUID,
    ) -> dict[str, float | None]:
        if not os.path.isdir(artifact_path):
            raise AdapterNotFoundError(artifact_path)

        records = await self._load_dataset_records(dataset_version_id)
        if not records:
            raise MetricComputationError("dataset version has no records")

        inputs = [r.get("instruction", "") for r in records]
        references = [r.get("response", "") or r.get("output", "") for r in records]

        predictions = await self._generate_predictions(artifact_path, inputs)

        rouge = metrics_module.compute_rouge_l(predictions, references)
        bp, br, bf = metrics_module.compute_bertscore(predictions, references)
        sem = metrics_module.compute_semantic_similarity(predictions, references)

        return {
            "rouge_score": rouge,
            "bertscore_precision": bp,
            "bertscore_recall": br,
            "bertscore_f1": bf,
            "semantic_similarity": sem,
        }

    async def _load_dataset_records(
        self, dataset_version_id: UUID
    ) -> list[dict]:
        # Load the file path from the DatasetVersion row, then parse
        # by extension. No streaming — load all into memory (≤10k records).
        import csv
        import json as json_mod

        from app.models.dataset import DatasetVersion
        from sqlalchemy import select

        result = await self._evals.session.execute(
            select(DatasetVersion).where(DatasetVersion.id == dataset_version_id)
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise DatasetVersionNotFoundError(dataset_version_id)

        file_path = version.file_path
        if not os.path.exists(file_path):
            raise DatasetNotFoundError(dataset_version_id)

        # dataset.format lives on the parent; detect by extension here.
        ext = file_path.rsplit(".", 1)[-1].lower()
        records: list[dict] = []
        if ext == "jsonl":
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json_mod.loads(line))
        elif ext == "json":
            with open(file_path, encoding="utf-8") as f:
                data = json_mod.load(f)
                records = data if isinstance(data, list) else [data]
        else:  # csv and friends
            with open(file_path, encoding="utf-8", newline="") as f:
                records = list(csv.DictReader(f))
        return records

    async def _generate_predictions(
        self, artifact_path: str, inputs: list[str]
    ) -> list[str]:
        # Tokenizer lives in adapter_path/tokenizer/ (QLoRA training layout).
        # 4-bit NF4 quantization must match the training-time config or
        # the LoRA weights decode against the wrong base.
        from app.models.training_job import TrainingJob  # noqa: F401
        from sqlalchemy import select

        result = await self._evals.session.execute(
            select(TrainingJob).where(TrainingJob.artifact_path == artifact_path)
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise AdapterNotFoundError(artifact_path)

        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )
        from peft import PeftModel

        tokenizer_path = os.path.join(artifact_path, "tokenizer")
        if os.path.isdir(tokenizer_path):
            tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
        else:
            tokenizer = AutoTokenizer.from_pretrained(artifact_path)

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        base = AutoModelForCausalLM.from_pretrained(
            job.base_model,
            quantization_config=bnb_config,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        model = PeftModel.from_pretrained(base, artifact_path)
        model.eval()

        predictions: list[str] = []
        for inp in inputs:
            inputs_enc = tokenizer(inp, return_tensors="pt")
            inputs_enc = {k: v.to(model.device) for k, v in inputs_enc.items()}
            input_len = inputs_enc["input_ids"].shape[-1]
            with torch.no_grad():
                out = model.generate(
                    **inputs_enc,
                    max_new_tokens=128,
                    do_sample=False,
                )
            # Decode only the newly generated tokens, not the prompt.
            pred = tokenizer.decode(
                out[0][input_len:], skip_special_tokens=True
            )
            predictions.append(pred)
        return predictions

    async def get_evaluation(
        self, evaluation_id: UUID, *, user_id: UUID
    ) -> EvaluationResponse:
        ev = await self._evals.get_by_id(evaluation_id)
        if ev is None:
            raise EvaluationNotFoundError(evaluation_id)
        if ev.user_id != user_id:
            raise EvaluationAccessDeniedError(evaluation_id)
        return EvaluationResponse.model_validate(ev)

    async def list_evaluations(
        self,
        *,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> EvaluationListResponse:
        items = await self._evals.list_for_user(
            user_id, limit=limit, offset=offset
        )
        total = await self._evals.count_for_user(user_id)
        return EvaluationListResponse(
            items=[EvaluationResponse.model_validate(e) for e in items],
            total=total,
            limit=limit,
            offset=offset,
        )
